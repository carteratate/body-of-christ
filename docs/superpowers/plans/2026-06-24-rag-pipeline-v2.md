# RAG Pipeline V2 — Enrichment + Cross-Encoder + Pipelined Execution

## Overview

A redesigned retrieval pipeline that adds ingest-time chunk enrichment, a local cross-encoder filter, per-collection API key isolation, and fully pipelined per-collection execution. Reduces estimated latency from 25-35s to 10-15s and cost from ~$0.10 to ~$0.06 per query while improving retrieval quality.

---

## Phase 0: Ingest-Time Enrichment (One-Time)

Run every chunk through an LLM at ingest time to generate an **annotation** stored in the existing `annotation` column and embedded into `annotation_embedding`. Every collection's pipeline uses this annotation at query time for both vector search and FTS.

---

## Phase 1: API Key Structure

```
Key A: Bible (dedicated)
Key B: Catechism, Councils, Canon Law
Key C: Summa, Encyclicals, Apostolic Exhortations
Key D: Church Fathers, Medieval, Papal Documents
```

Non-Bible collections assigned to Keys B/C/D via **round-robin per query** for dynamic load balancing. Each key has a semaphore sized to the number of collections on that key. If waves are needed within a key, the collection whose reranking job is expected to be largest fires first.

**Wave priority ordering (for Bible and for any future key that requires waves):**

Within Key A (Bible), wave 1 fires the free-form passage first since it is unconstrained and typically most query-relevant, then genre variants fill remaining wave slots.

Across all keys: **Bible (Key A), Church Fathers (Key D), and Catechism (Key B)** begin their HyDE calls at t=0 — these collections consistently produce the largest rerank jobs and benefit most from getting their retrieval started early. Since each collection is on its own key with independent semaphoring, this is naturally satisfied — all keys fire at t=0 with no artificial sequencing between them.

---

## Phase 2: Query Time Pipeline

**Full collection isolation:** every collection runs its own complete pipeline — HyDE → embed → retrieve → cross-encode → rerank — independently. No collection's process waits for, shares state with, or is influenced by any other collection's process until **Step 6 (Global Sort)**. All inter-collection coordination happens exactly once, at that step.

---

### Step 1 — Query Embedding (t=0)

Single OpenAI call: `embed_text(query) → query_vec`

---

### Step 2 — HyDE Generation (t=0, parallel with Step 1)

Separate Haiku call per collection using collection-specific prompt. Semaphored per API key. Each HyDE passage embeds via OpenAI immediately as its Haiku call returns — no collection waits for another.

**Bible (Key A, semaphore=4):**
8 parallel Haiku calls in 2 waves of 4:
- Wave 1: free-form, Psalms, OT Wisdom, OT Prophets
- Wave 2: OT Stories, NT Stories, NT Epistles, NT Teachings

**All other collections (Keys B/C/D, semaphore=3):**
1 Haiku call each using the existing collection-specific prompts. All 3 collections per key fire simultaneously.

`expand_query` is removed — enrichment FTS replaces its function.

---

### Step 3 — Per-Collection Retrieval (pipelined, fully isolated)

4 strategies start immediately at t≈0.5 when `query_vec` is ready. The HyDE strategy fires per collection as that collection's HyDE vector becomes available. Each collection's retrieval is entirely self-contained.

| Strategy | Vector/text used | n fetched | RRF guarantee |
|---|---|---|---|
| Qdrant: enrichment_vec | query_vec vs annotation_embedding | quota × 3 | top-2 |
| Qdrant: content_vec | query_vec vs content_embedding | quota × 2 | top-2 |
| FTS: content tsvector | plainto_tsquery on raw text | quota × 2 | top-2 |
| FTS: enrichment tsvector | plainto_tsquery on annotation | quota × 2 | top-2 |
| Qdrant: hyde_vec | hyde_embed vs content_embedding | 3 | top-1 per variant |

Bible gets 8 hyde_vec searches (one per HyDE variant), each returning top-3, each with top-1 guarantee.

**RRF merge per collection:** k=60, non-HyDE top-2 guaranteed, HyDE top-1 guaranteed per variant. After dedup: ~12-18 unique candidates per standard collection, ~14-20 for Bible.

---

### Step 4 — Cross-Encoder Filter (per collection, pipelined, fully isolated)

Local model (`bge-reranker-v2-m3`) loaded in memory on the server. Scores each candidate against the query.

Cross-encoder scores against `enrichment_annotation + chunk_content` concatenated — not raw content alone. This ensures vocabulary-bridged scoring and eliminates the typological and archaic vocabulary risk.

- Input: ~12-18 candidates per collection from RRF
- Output: top `quota + 3` candidates
- Time: ~50-100ms per collection
- Cost: $0

Fires immediately as each collection's RRF merge completes. No collection waits for another.

---

### Step 5 — Sonnet Reranking (per collection, pipelined, fully isolated)

Each collection's Sonnet call fires as soon as its cross-encoder output is ready. Uses the collection's assigned API key.

- Input: `quota + 3` candidates
- Sonnet scores relevance 0.0-1.0, detects overlap/redundancy, applies source diversity nudge, classifies user intent
- Time: ~6-12s per collection (down from 18-26s)
- Natural stagger from pipeline means Sonnet calls spread across ~2-3s

No collection's reranking waits for or is aware of any other collection.

---

### Step 6 — Global Sort + Collection Guarantee

First and only point where collections interact:

- Sort all reranked chunks globally by `reranker_score` descending
- Drop excluded chunks
- Cap each collection at `quota` results
- For any selected collection absent from results, inject its best chunk if score ≥ 0.25

---

### Step 7 — Stream Chunks, Persist to DB, Yield Done

Same as current pipeline.

---

### Step 8 — Sequential Explanation Streaming

Same as current — one GPT call per result chunk, sequential, post-done.

---

## Summary of Changes vs Current

| | Current | New |
|---|---|---|
| Enrichment | None | Ingest-time annotation on every chunk |
| Retrieval strategies | query_vec, hyde_vec, extra_vecs, FTS×1, expand FTS×2 | enrichment_vec, content_vec, hyde_vec, FTS×2 (content + enrichment) |
| expand_query | Yes | Removed |
| Cross-encoder | None | Local model, scores enrichment+content concatenated |
| Candidates to Sonnet | 4-21 per collection | quota+3 always |
| API keys | 1 | 4 (Bible dedicated, 3 round-robin) |
| HyDE semaphoring | None | Per key, priority-ordered by rerank job size |
| Collection isolation | Partial | Full — no inter-collection dependency until Global Sort |
| Execution model | All collections wait for all HyDE before retrieval | Pipelined — each collection progresses independently |
| Estimated latency | 25-35s | 10-15s |
| Estimated cost/query | ~$0.10 | ~$0.06 |
