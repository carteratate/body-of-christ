# RAG Pipeline V3 — Topic Embeddings, Cross-Encoder, Weighted RRF

## Overview

V3 replaces Sonnet reranking ($0.111/search, 86% of per-query LLM cost) with a zero-cost BGE cross-encoder, adds per-topic embeddings in a dedicated Qdrant collection, and introduces weighted RRF to surface topic-only discoveries. Annotation is generated at ingest time by Opus 4.8 for maximum enrichment quality. Net effect: better retrieval quality at lower per-query cost, paid for by a one-time ingest enrichment investment.

**Key changes vs V2:**

| | V2 (current) | V3 |
|---|---|---|
| Reranking | Sonnet 4.6 ($0.111/search) | BGE-reranker-v2-m3 ($0/search) |
| Enrichment model | Haiku 4.5 | Opus 4.8 |
| Enrichment output | Single annotation text | Topics array + rich annotation |
| Topic embeddings | None | Dedicated `topics` Qdrant collection |
| RRF weighting | Uniform | Topic strategy 1.5× weighted |
| Dedup | None | Combined: position + cosine + per-title cap |
| `expand_query` | Haiku call at query time | Removed — annotation FTS replaces it |
| Estimated cost/query | ~$0.10 | ~$0.04 |

---

## Phase 0: Ingest-Time Enrichment (One-Time, Opus 4.8)

One Opus 4.8 call per chunk producing topics-first JSON:

```json
{
  "topics": [
    "Christ's real presence in the Eucharist",
    "transubstantiation as Aristotelian change",
    "accidents without subject in sacramental theology"
  ],
  "annotation": "Aquinas defends Christ's real presence in the Eucharist through the lens of Aristotelian metaphysics, arguing that transubstantiation involves a change of substance while accidents (appearance, taste, texture) persist without an underlying subject. This applies hylomorphic principles to sacramental theology, addressing the philosophical problem of how bread and wine can become the Body and Blood of Christ while retaining their sensible qualities..."
}
```

### Design constraints

1. **Topics first** — the prompt generates the focused topic phrases before writing the annotation, so the model's attention is primed on the specific angles
2. **Annotation must cover all topics** — every topic phrase must appear (in meaning, not verbatim) in the annotation text, ensuring cross-encoder coherence: when a topic search surfaces a chunk, the annotation the cross-encoder reads will contain that theme
3. **Topics are short, focused phrases** — 3-8 per chunk, each a precise theological concept or question that someone might search for; NOT broad categories
4. **Annotation is rich but NOT embedded** — used only for FTS (`search_vector` tsvector) and cross-encoder input; embedding it would cause dilution (broad text → averaged embedding matching nothing strongly)

### Storage

- `chunks.annotation` (jsonb, existing column) — stores the full `{"topics": [...], "annotation": "..."}` object
- Topic phrases embedded individually into a new Qdrant collection `topics` (one point per topic, payload includes `chunk_id`, `collection`, `document_id`)
- `search_vector` tsvector rebuilt from annotation text (replaces current content-only tsvector)

### Cost estimate (Opus 4.8 — validated)

Corpus: **54,027 chunks** across 10 collections.

| Collection | Chunks | Avg Content (chars) | Est. Input Tokens | Est. Output Tokens |
|---|---|---|---|---|
| summa | 26,750 | 501 | 325 | 175 |
| church-fathers | 9,242 | 2,401 | 800 | 350 |
| encyclicals | 6,110 | 1,180 | 495 | 300 |
| bible | 3,262 | 1,466 | 567 | 300 |
| apostolic-exhortations | 3,024 | 1,315 | 529 | 300 |
| councils | 2,173 | 974 | 444 | 250 |
| canon-law | 1,747 | 401 | 300 | 180 |
| catechism | 800 | 1,564 | 591 | 300 |
| papal-documents | 485 | 1,732 | 633 | 350 |
| medieval | 434 | 2,331 | 783 | 350 |

*Input tokens = ~200 (system prompt) + content_chars / 4. Output tokens = topics array + rich annotation.*

**Totals:**
- Input: ~25M tokens × $5.00/1M = **$125**
- Output: ~13M tokens × $25.00/1M = **$325**
- **Total enrichment cost: ~$450** (one-time)

*For reference, Haiku 4.5 would cost ~$90 for the same job ($25 input + $65 output). Opus costs ~5× more but produces significantly higher quality topic decomposition and richer annotations — this is the foundation the entire retrieval pipeline builds on.*

**Embedding the topics** (OpenAI `text-embedding-3-large`):
- ~54,027 chunks × ~5 topics avg = ~270K topic embeddings
- ~270K × ~15 tokens avg = ~4M tokens × $0.13/1M = **~$0.52**

**Total one-time ingest cost: ~$451**

---

## Phase 1: API Key Structure

```
Key A: Bible (dedicated)
Key B: Catechism, Councils, Canon Law
Key C: Summa, Encyclicals, Apostolic Exhortations
Key D: Church Fathers, Medieval, Papal Documents
```

Non-Bible collections assigned to Keys B/C/D via round-robin per query. Each key has a semaphore sized to the number of collections on that key.

---

## Phase 2: Query-Time Pipeline

Full collection isolation: every collection runs HyDE → embed → retrieve → independently until Global Sort + Dedup. No inter-collection coordination until that step.

---

### Step 1 — Query Embedding (t=0)

Single OpenAI call: `embed_text(query) → query_vec`

---

### Step 2 — HyDE Generation (t=0, parallel with Step 1)

**Unchanged from current pipeline.**

- **Bible (Key A):** 8 parallel Haiku calls (1 free-form + 7 genre variants)
- **All other collections:** 1 Haiku call each using collection-specific prompts

Each HyDE passage embeds via OpenAI immediately as its call returns.

`expand_query` is removed — annotation FTS replaces its function.

---

### Step 3 — Per-Collection Retrieval (pipelined, fully isolated)

6 strategies run per collection. Each operates independently and feeds into per-collection RRF merge.

| # | Strategy | What it searches | Vector/text used | n fetched | RRF guarantee | Weight |
|---|---|---|---|---|---|---|
| 1 | **Topic vector** | `topics` Qdrant collection | `query_vec` vs topic embeddings | quota × 3 | **top-4** | **1.5×** |
| 2 | Content vector | `chunks` Qdrant collection | `query_vec` vs content_embedding | quota × 2 | top-2 | 1.0× |
| 3 | FTS: content | `chunks.search_vector` (content tsvector) | `plainto_tsquery(query)` | quota × 2 | top-2 | 1.0× |
| 4 | FTS: annotation | `chunks.search_vector` (annotation tsvector) | `plainto_tsquery(query)` | quota × 2 | top-2 | 1.0× |
| 5 | HyDE vector(s) | `chunks` Qdrant collection | `hyde_embed` vs content_embedding | 3 per variant | top-1 per variant | 1.0× |

**Why two tsvector strategies?** Content tsvector matches the original passage vocabulary. Annotation tsvector matches Opus's theological vocabulary bridging — terms like "hypostatic union" in the annotation connect to passages that say "two natures in one person" in content. Together they cover both literal and conceptual keyword matches.

**Why topic vectors get 1.5× weight and top-4 guarantee:**
Standard RRF has a consensus bias — it favors chunks that appear in multiple strategies. But a chunk might be the perfect match for one precise topic while scoring modestly on broad content/FTS searches. The 1.5× weight and expanded guarantee (top-4 vs top-2) prevent these topic-only discoveries from being buried.

**Weighted RRF formula:**

```
score(chunk) = Σ weight_s × 1/(k + rank_s)    where k = 60
```

Topic strategy results get `weight = 1.5`, all others get `weight = 1.0`.

**Topic vector dedup:** Multiple topics from the same chunk may match the query. Before RRF merge, topic search results are deduped by `chunk_id` (keep the highest-scoring point per chunk).

**Per-collection RRF merge output:** ~14-20 unique candidates per standard collection, ~16-24 for Bible.

---

### Step 4 — Cross-Encoder Scoring (per collection, pipelined)

**Model:** `bge-reranker-v2-m3` (~568M params, loaded in server memory)

Scores each candidate against the query using **annotation + content concatenated** as the passage text — not raw content alone. This ensures the cross-encoder sees the theological vocabulary bridging from the annotation, preventing archaic/typological passages from being scored poorly.

- Input: ~14-20 candidates per collection from RRF
- Output: cross-encoder relevance score per candidate (continuous)
- Time: ~50-100ms per collection on CPU
- Cost: **$0**

Fires immediately as each collection's RRF merge completes. No collection waits for another.

---

### Step 5 — Global Sort + Dedup + Collection Guarantee

First point where collections interact.

**5a. Global sort** — all cross-encoder-scored chunks sorted descending by score.

**5b. Combined dedup** — for any two chunks from the same `document_id`:
- If they are **within 2 positions** of each other (same document, adjacent or near-adjacent passages) **AND** their content embeddings have **cosine similarity > 0.9** → drop the one with the lower cross-encoder score.
- This prevents near-duplicate adjacent passages from taking multiple result slots, while preserving genuinely different passages from the same document even when they're close together.

**5c. Per-title cap** — maximum **2 results per document title**. After dedup, if any document has more than 2 chunks in the result set, only the top-2 by cross-encoder score are kept. This ensures source diversity across the result set.

**5d. Collection guarantee** — for each selected collection absent from results after dedup + cap, inject its best chunk if cross-encoder score ≥ 0.25.

**5e. Hard cutoff** — cap each collection at `quota` results.

---

### Step 6 — Stream Chunks, Persist to DB, Yield Done

Same as current pipeline. Chunk SSE events → DB insert → done SSE event.

---

### Step 7 — Sequential Explanation Streaming

Same as current — one GPT call per result chunk, sequential, post-done. `explanation_delta` SSE events applied progressively by the client.

---

## Cost Comparison

### Per-query cost

| Component | V2 (current) | V3 |
|---|---|---|
| HyDE (Haiku) | $0.018 | $0.018 (unchanged) |
| Reranking (Sonnet) | $0.111 | **$0** (BGE) |
| Explanations (GPT) | ~$0.002 | ~$0.002 (unchanged) |
| Embeddings (OpenAI) | ~$0.001 | ~$0.001 (unchanged) |
| `expand_query` (Haiku) | ~$0.001 | **$0** (removed) |
| **Total per query** | **~$0.132** | **~$0.021** |

**Per-query savings: ~$0.111 (84% reduction)**

### One-time costs

| Item | Cost |
|---|---|
| Opus 4.8 enrichment (54,027 chunks) | ~$450 |
| Topic embedding (OpenAI, ~270K embeddings) | ~$1 |
| **Total one-time** | **~$451** |

### Break-even

$451 one-time cost ÷ $0.111 per-query savings = **~4,063 searches** to break even.

At 30 searches/day/user with a small user base, break-even is reached within weeks. After that, every search saves $0.111.

---

## Implementation Phases

### Phase 0: Enrichment Pipeline (datapipeline)
1. Write enrichment prompt (topics-first JSON schema, Opus 4.8)
2. Create enrichment script: iterate chunks, call Opus, store JSON in `chunks.annotation`
3. Create topic embedding script: extract topics from annotation JSON, embed each, upsert to new `topics` Qdrant collection
4. Rebuild `search_vector` tsvector from annotation text
5. Run enrichment on full corpus (~54K chunks)

### Phase 1: Retrieval Changes (services/api)
1. Add topic vector search strategy against `topics` Qdrant collection
2. Add annotation FTS strategy
3. Implement weighted RRF (1.5× for topic strategy)
4. Add topic dedup (by chunk_id before RRF)
5. Remove `expand_query` dependency

### Phase 2: Cross-Encoder + Dedup (services/api)
1. Install and load `bge-reranker-v2-m3` model
2. Replace Sonnet reranking with cross-encoder scoring (annotation + content concatenated)
3. Implement combined dedup (position within 2 + cosine > 0.9)
4. Implement per-title cap (max 2)
5. Wire into pipeline.py

### Phase 3: API Key Isolation (services/api)
1. Configure 4 API keys with per-key semaphores
2. Wire key assignment into pipeline

---

## Summary of Changes vs Current

| | Current | V3 |
|---|---|---|
| Enrichment | Single annotation text (not yet populated) | Opus 4.8: topics array + rich annotation |
| Topic embeddings | None | Dedicated `topics` Qdrant collection |
| Retrieval strategies | hyde_vec, query_vec, extra_vecs, FTS content, FTS expansion | topic_vec (1.5×), content_vec, hyde_vec, FTS content, FTS annotation |
| `expand_query` | Haiku call per query | Removed |
| Reranking | Sonnet 4.6 (~$0.111/search) | BGE-reranker-v2-m3 ($0) |
| Cross-encoder input | N/A | annotation + content concatenated |
| Dedup | None | Combined: same doc + within 2 positions + cosine > 0.9 |
| Per-title cap | None | Max 2 results per document title |
| RRF weighting | Uniform | Topic strategy 1.5× |
| API keys | 1 | 4 (Bible dedicated, 3 round-robin) |
| Est. cost/query | ~$0.132 | ~$0.021 |
| One-time cost | — | ~$451 (enrichment + topic embedding) |
| Break-even | — | ~4,063 searches |
