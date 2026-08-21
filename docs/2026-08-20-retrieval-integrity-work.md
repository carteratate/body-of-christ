# Retrieval integrity work — state as of 2026-08-20

Working notes for the Summa-objection / store-divergence work. Written to survive a
session restart. Everything below is measured against `body-of-christ-dev` and the live
Qdrant cluster unless stated otherwise.

---

## The problem this started from

10,517 Summa chunks — **39.3% of that collection** — are objections Aquinas states in
order to REFUTE. `ingest/summa.py` splits each article into its dialectical parts and
moves the `"Objection 1"` marker out of `content` into `unit_label`. That label reached
nothing in the retrieval path, so a reranker saw only `"It would seem that…"`.

Retrieved and rankable today: the Arian case against the Son's eternity, and
*"one may, without sin, kill an innocent person."*

Objections stayed rare in results (2.0% of Summa results across 84 persisted searches)
only because Qdrant's payloads were **stale** and still carried the marker inline in
`content` — an accident, not a design, and one that any re-embed would erase.

---

## What shipped (code, all uncommitted on `codex/harden-llm-rerank-structured-output`)

### Step 1 — per-source result cap
`app/rag/dedup.py`, `app/rag/steps/min_floor.py`

The diversity cap keyed on `document_title`. summa, catechism and canon-law are each
ONE document, so each entire collection was capped at **2 results per search** —
binding in 41 of 80 eval queries. Now keyed on the reader chapter for those three,
document title for the other seven. `min_floor` rewritten as two passes so the
empty-results screen still spans collections.

- 3,000 randomised differential trials: the seven multi-document collections are
  **bit-for-bit unchanged**.
- Expect **~+21% results/search** (21.8 → 26.4 at quota=5), each costing one sequential
  explanation stream.

### Step 2 — payload reconcile tool
`datapipeline/reconcile.py`, `datapipeline/scripts/reconcile_qdrant_payloads.py`

Postgres and Qdrant have served **different text since 2026-06-23**. Commit `16f6d27`
stripped the marker from `content`; Postgres was rewritten 38 minutes later, Qdrant
never was. Live search reads Qdrant; saved-search history reads Postgres. **That bug is
still shipping.**

Tool reconciles payloads via `set_payload` — no re-embed, no ID change, no re-ingest
(which would cascade-delete `retrievals`, `bookmarks`, `retrieval_labels`,
`guest_trial_retrievals`). Dry-run default; `--fields content` gated behind
`--allow-content-sync`.

### Step 3 — passage-role label
`types.py`, `retrieve_fts.py`, `retrieve_vector.py`, `rrf.py`, `fetch_positions.py`,
`rerank_cohere.py`, `llm_rerank/{listwise,pointwise}.py`, `rerank_docs.py`,
`passage_role.py`, `rerank.py`, `explain.py`, `pipeline.py`, `models/{search,bookmarks}.py`,
`routes/{search,bookmarks}.py`, `compare/judge.py`, `apps/web/src/lib/api.ts`

`unit_label` now reaches both rerankers, the explanation model, and every serving path
(live SSE, history restore, bookmarks). Prompts explain the four dialectical roles with
a carve-out for locator labels (`Can. 33`, `§17`). Contract versions bumped on BOTH the
LLM path (`structured-positional-v2-passage-role`) and the Cohere path
(`cohere-doc-v2-passage-role`) — Cohere has no prompt, but its document text changed.

The eval judge renders `role=` too, so the instrument can see the variable that moved —
but its system prompt says nothing about objections, so it gets the fact without the
treatment's hypothesis.

### Summa splitter fix (unapplied)
`datapipeline/ingest/summa.py`

The marker pattern required a trailing comma. 33 markers in the live corpus are
comma-less (12 respondeo, 21 sed contra), so those articles look answer-less. Pattern
now matches the comma-less form **only at a line start** — one article contains
`"(Arg. On the contrary)."` inside its respondeo, and an unanchored fix would split it
at a citation.

**NOT APPLIED.** Runs at ingest only. 16 articles still have no respondeo chunk.

---

## What was applied to production

**Task 1 — `--fields structural`, applied 2026-08-20.** `unit_label` + `chapter_key`
written to all 53,747 Qdrant payloads. Verified against a pre-write snapshot: all 8
pre-existing fields preserved, vectors unchanged, point count unchanged, schema
unchanged (1536 unnamed), re-run reports `to_write=0`.

Census after: **`chapter_key` on 100%**, `unit_label` on 80.6% (church-fathers,
medieval and most council prose genuinely have no label — the tool never writes a null
over anything).

Why it mattered: `fetch_positions` was the only source of those fields for vector-path
candidates, and it skips the backfill entirely when the Postgres pool is unavailable.
On a degraded search an objection reached the reranker **and the explanation model**
unlabelled — and explanations are persisted to `retrievals.explanation` and re-served
forever.

---

## Open findings (measured, unfixed)

| finding | scale | note |
|---|---|---|
| **V5 pipeline would destroy production search if run** | — | writes 3072-dim NAMED vectors; live collection is 1536 unnamed. Also calls `clear_collection` unconditionally — `--clean` gates only the *Qdrant* delete. **Highest-risk item in the repo.** |
| live search vs history return different text | corpus-wide | fixed only by the gated content sync |
| `chapter_label` drift between stores | 296 (0.55%) | encyclicals 223, a-e 69, papal-docs 4. It is the **embedding prefix**, so those vectors were built from a different input than today's rows imply. Reconcile does NOT sync it, and syncing wouldn't fix the vectors — only a re-embed would. |
| content drift needing re-embed, not payload sync | 86 | a-e 78, summa 8 — Qdrant holds text unrelated to the row |
| 21 Summa chunks with empty `content` | 21 | from `_split_article`'s `else ""` branch |
| enrichment never run | 0 of 54,027 | complete, tested, unexecuted subsystem |
| no UI renders `unit_label` | — | type + API plumbed; nothing displays it |

⚠️ An earlier draft of this file claimed "one incomplete re-ingest explains all of it."
That is WRONG — see the review section below. There is a second, worse corruption:
26,718 points whose Qdrant `content` differs from `chunks.content`, including
`Gaudete in Domino`, where all 78 points hold footnote text.

---

## Test state

- `services/api`: **491 passing**
- `datapipeline/tests/test_reconcile.py`: **30 passing** (also passes with all
  credentials stripped)
- `datapipeline/tests/test_backfill_vectors.py`: **17 passing**
- `apps/web`: `tsc --noEmit` clean
- Pre-existing, unrelated: datapipeline has 5 collection errors (missing `tiktoken`)
  and 10 failures from gitignored `sources/`

Twelve adversarial review rounds across steps 1–3, all ending clean.

---

## Next

**Task 4 — vector backfill, applied 2026-08-20.** All 280 missing points embedded and
upserted. Verified: Qdrant `points_count` **53,747 -> 54,027**, every collection now
matches its Postgres row count exactly, `missing=0` and `orphaned=0` corpus-wide, re-run
is a no-op, and the payload reconcile reports the new points already in sync. Spot
checks: dim 1536, norm 1.0, all 10 payload keys, and a self-search returns the point at
1.0000 with its own adjacent sections at 0.918/0.895 — the vectors sit correctly
relative to their siblings, not merely present.

Nine encyclicals/exhortations that were **entirely absent** from the vector index
(Haerent Animo, Mysterium Fidei, Ineffabilis Deus, In Supremo Apostolatus, Sublimis
Deus, Meridionali Americae, Unam Sanctam, Annus Qui Hunc, In Dominico Agro) are now
reachable by semantic search for the first time.

Three adversarial rounds, 63+ mutants; final round found no code defect. Tool pins the
embedding model AND dimensions as module constants (settings drifted to 3072 under V5),
guards non-contiguous positions, checks vector/row count at the pairing site, and routes
upserts through the retrying helper.

---

## Next

1. **Commit.** ~40 files are uncommitted. This is the largest outstanding risk to the
   work itself. Suggested split: (a) per-source cap, (b) reconcile tool, (c) passage-role
   plumbing, (d) backfill tool + summa splitter fix.
2. **No evals.** A smaller, task-specific eval is a separate conversation now that
   tasks 1-4 are complete and verified.
3. **Separate ticket: `Gaudete in Domino`** — 78 points serving footnote text. A live
   retrieval-quality bug, unrelated to and unfixed by any of the above.

---

## Backfill tool — adversarial review round 1 (2026-08-20)

**Verdict: safe to run against production.** Verified end-to-end on a throwaway Qdrant
collection: correct dimensionality, unnamed vector shape, payload key set byte-identical
to neighbours, idempotent re-run ("nothing to do"), dry run genuinely read-only.

### Independently confirmed
- All four fidelity claims (prefix, `dimensions=1536`, unnamed vector, unchanged
  overlap config) verified against git history and the live collection.
- **Point identity: `chunks.id == passage_id(document_id, anchor) == Qdrant point id`
  across all 54,027 rows, 0 mismatches.** No duplicate-point risk.
- Embedding fidelity floor is **0.99983**, not the ">= 0.9999" claimed here earlier —
  API nondeterminism, not reconstruction error. Drifted-label chunks measured
  0.88–0.93 and drifted-content chunks 0.47–0.60, proving the check discriminates.
- **The drift does not intersect the backfill.** 278 of the 280 are in documents with
  *zero* Qdrant points (no in-document neighbour to be inconsistent with); the other 2
  sit in documents with zero content and zero label drift, neighbours measured
  0.99994–1.00000. Every drifted document has `missing=0`.

### Must fix before merge (neither changes the verdict)
1. **8 of the 17 tests do not test the tool.** All 9 mutations to `backfill_vectors.py`
   were killed, but **all 8 mutations to `scripts/backfill_missing_vectors.py` — where
   every load-bearing decision lives — survived with 17/17 passing**: empty prefix,
   dropped `dimensions=`, named vector, random point id, `if not apply` disabled,
   neighbour context destroyed, `k_prev`/`k_next` swapped, index-by-position.
   `backfill_collection` already takes its dependencies as parameters, so a fake client
   plus a monkeypatched `_embed` kills all eight cheaply.
2. **No retry on the Qdrant upsert** — calls `client.upsert` directly, bypassing
   `writers.qdrant.upsert_points`, which retries 4× with backoff. `_embed` likewise
   retries only `RateLimitError`, not timeout/connection/5xx.
3. **`plan()` assumes list index == passage position, unguarded.** True for every
   document today (0 gaps, 0 duplicates, 0 non-zero starts across 54,027 rows) but only
   by luck of the data. One deleted row shifts the neighbour window and yields a
   wrong-but-plausible embedding input. One assert makes it structural.

### Nits
Short embedding response silently under-writes and over-reports (no length check, and
positional matching means an omitted index shifts every later vector onto the wrong
row); dry run returns before `plan()` so the input construction is never exercised
without `--apply`; `missing_chunk_ids`' sortedness is discarded by a `set()` wrapper;
`--collection all` enumerates `BUILDERS` rather than the database.

### NEW FINDING — my causal story above was wrong
"One incomplete re-ingest explains every symptom" is **incomplete**. There is a second,
worse corruption: **26,718 points whose Qdrant payload `content` differs from
`chunks.content`.**

- **`Gaudete in Domino` (apostolic-exhortations): all 78 points hold FOOTNOTE text.**
  Payloads read `'2 Cor. 11:28.'`, `'Cf. Mk. 10:14-15.'` — median 14 characters, 72 of
  78 under 80 chars — while Postgres holds the real paragraphs. Those points are both
  *displayed* wrong in search results and *embedded* from footnotes. The document is
  entirely misaligned between the stores. **This is a live retrieval-quality bug and
  deserves its own ticket.**
- Scattered singles: Reconciliatio et Paenitentia, Ecclesiam Suam, Populorum
  Progressio, Orientale Lumen, Ordinatio Sacerdotalis (1 each), councils 15.
- Summa 26,620 — Qdrant carries the inline unit label, Postgres does not. Benign in
  direction; it is the marker-strip change loaded to the reader but never re-embedded.

None of this blocks the backfill — every affected document has `missing=0` and the tool
correctly leaves them alone.
