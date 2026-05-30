# Body of Christ V2 — Implementation Progress

> **Purpose:** Continuity file for implementation sessions. If you are a new Claude instance picking this up, read this first — it tells you exactly where things stand and what to do next.

---

## Branch
`feature/v2-rag` (based off `master`)

## Plan File
`/home/carter/.claude/plans/i-want-to-develop-crispy-journal.md`
Full V2 design spec + build sequence. Read it before making architectural decisions.

---

## Completed Tasks

| # | Task | Commits | Notes |
|---|------|---------|-------|
| 8 | Database migrations 0004–0006 | `2c08244` `68f7124` `96e3b3a` `072295c` | documents, chunks (HNSW+FTS), searches, retrievals, bookmarks, chunk_feedback, user_preferences. All RLS in place. |
| 9 | Datapipeline foundation | `4534e5a` `b63458f` | `datapipeline/` folder: config.py, load.py, requirements.txt, .env.example, README.md |
| 10 | Datapipeline: bible.py | `1c921d7` | Draft complete and verified against real data. **DO NOT RUN** until schema fix (see Known Issues). Deferred to Phase 3. |
| 13 | Backend: config + openai dependency | `fd6a076` `6e88acd` | openai>=1.0.0 in pyproject.toml; all RAG config fields added to config.py; rag/__init__.py created |
| 14 | Backend RAG: hyde.py + embed.py | `927df4c` `61fdb79` | HyDE passage generation with fallback; OpenAI text-embedding-3-large wrapper with index-sorted batch output |
| 15 | Backend RAG: retrieve.py | `062cb7b` | Dual vector + FTS with RRF (k=60); asyncio.gather; dislike filter; Option C stub |
| 16 | Backend RAG: rerank.py + explain.py | `f2d26d2` | Per-collection Haiku re-ranking (0.0–1.0 scores, fallback); parallel explanation generation with fallback |

## Deferred (Phase 3 — after frontend is working)

| # | Task | Notes |
|---|------|-------|
| 11 | catechism + encyclicals + church_fathers + saints | Build frontend first |
| 12 | embed.py + run_all.py | Build frontend first |

---

## Next Task to Implement

**Task 17 — Backend RAG: rag/pipeline.py + all Pydantic models**

### pipeline.py

Create `services/api/app/rag/pipeline.py` — the orchestrator that ties together hyde, embed, retrieve, rerank, and explain into a single async generator that yields SSE-style events.

**Function signature:**
```python
async def run_search_pipeline(
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    user_id: str,
) -> AsyncGenerator[dict, None]:
```

**Yields events (dicts) in this order:**
1. For each chunk as it clears re-ranking (in score order): `{"type": "chunk", "chunk_id": ..., "content": ..., "source": {...}, "reranker_score": ...}`
2. For each explanation as it completes: `{"type": "explanation", "chunk_id": ..., "explanation": ...}`
3. Final: `{"type": "done", "search_id": ..., "result_count": ...}` (search_id is the UUID inserted into `searches` table)
4. On unrecoverable error: `{"type": "error", "detail": "..."}`

**Pipeline steps:**
1. HyDE generation (parallel with query embedding): `asyncio.gather(generate_hyde_passage(query), embed_text(query))`
2. Embed HyDE passage if not None: `await embed_text(hyde_passage)`
3. For each active collection: `await retrieve_candidates(query, query_vec, hyde_vec, collection, quota, user_id)` — run concurrently with `asyncio.gather`
4. For each collection's candidates: `await rerank_collection(candidates, query, quota)` — run concurrently
5. Merge all collections' RankedChunks, sort globally by reranker_score desc
6. Yield `{"type": "chunk", ...}` for each result immediately
7. Insert search record into `searches` table; insert `retrievals` rows (rank, reranker_score — explanation not yet set)
8. Run explanation generation concurrently: `asyncio.gather(*[generate_explanation(...) for chunk in results])`
9. As each explanation completes, yield `{"type": "explanation", ...}` and UPDATE the retrievals row with explanation text
10. Yield `{"type": "done", ...}`

Use `asyncio.as_completed` or `asyncio.gather` for explanations — gather is simpler. For truly progressive explanation streaming (each yields as ready), use `asyncio.create_task` + `asyncio.as_completed`.

### Pydantic models

Create these files in `services/api/app/models/`:
- `search.py` — SearchRequest, SearchFilters, ChunkSource, ChunkResult, SearchResponse (for the done event)
- `documents.py` — DocumentResponse, ReaderChunk, ReaderResponse
- `bookmarks.py` — BookmarkCreate, BookmarkResponse, BookmarkListResponse
- `feedback.py` — FeedbackCreate, FeedbackResponse
- `preferences.py` — PreferencesResponse, PreferencesUpdate

Full schemas are in the plan file Part 5 (API Design section).

---

## Remaining Tasks After Task 17 (in order)

```
18  Backend routes: routes/search.py  (POST /v1/search SSE, GET /v1/searches, GET /v1/searches/{id}/results)
19  Backend routes: routes/documents.py + routes/bookmarks.py + routes/feedback.py + routes/preferences.py
20  Backend: main.py (register routers) + deps/rate_limit.py (tighten limits to 5/min, 30/day)
21  Frontend: lib/api.ts extensions + lib/analytics.ts
22  Frontend: AppShell + Sidebar + layout.tsx (PostHog init, posthog-js dep)
23  Frontend: search page bottom bar — SearchBar + CollectionToggles + TranslationSelector + quota [3|4|5]
24  Frontend: EmptyState (suggested query chips) + SearchPage.tsx state orchestration
25  Frontend: ChunkCard + RelevanceExplanation + ResultsSkeleton + SearchResults (progressive SSE rendering)
26  Frontend: DocumentReader + ReaderToolbar + ReaderChunk  (/reader/[docId])
27  Frontend: BookmarksPage + BookmarkCard  (/bookmarks)
28  Frontend: RateLimitModal + Toast + ErrorBoundary
29  Frontend: /chat redirect + all page routes + loading/error states + next.config.ts CSP headers
30  CLAUDE.md update with V2 invariants
--- PHASE 3 (after frontend is working) ---
31  Fix documents schema: add `translation` column + migration 0007
32  Datapipeline: bible.py (fix conflict key, then run)
33  Datapipeline: catechism.py, encyclicals.py, church_fathers.py, saints.py
34  Datapipeline: embed.py + run_all.py
```

---

## Known Issues / Gotchas

### 1. documents table UNIQUE constraint needs translation column (Phase 3 blocker)
- `documents` uses `UNIQUE(collection, title)` — conflicts when two Bible translations share a book name (e.g., "Genesis" in CPDV and "Genesis" in Douay-Rheims).
- Fix: add migration `0007` with `translation text` column on `documents` and `UNIQUE(collection, title, translation)`.
- Also update `datapipeline/load.py`'s `upsert_document()`.
- **Do not run any datapipeline scripts until this is fixed.**

### 2. bible.py draft exists but deferred
- Commit `1c921d7` has a working, real-data-verified script. Don't run it until issue #1 is fixed.

### 3. Datapipeline deferred to Phase 3
- Decision: build backend + frontend first, validate search infrastructure with a small hand-seeded dataset, then run corpus ingestion.

---

## Key Architecture Decisions

- **RAG strategy:** Option B — HyDE + dual vector search + full-text + per-collection re-ranking + parallel explanations
- **Re-ranking:** Haiku per collection; quota×4 candidates → top quota; scores 0.0–1.0; fallback to RRF order on failure
- **Progressive loading:** SSE stream — chunk events first, explanation events as each Haiku call completes
- **Per-source quota:** [3|4|5] control, default 4; total = quota × active collections
- **Embedding model:** text-embedding-3-large (OpenAI, 1536 dims)
- **HNSW index:** m=16, ef_construction=64 on chunks(content_embedding)
- **Option C stubs:** `annotation`/`annotation_embedding` columns NULL in chunks — no code change needed to activate when annotation job runs
- **V1 API contract preserved:** `/v1/chat`, `/v1/sessions` unchanged
- **Mobile:** Deferred post-V2. React Native + Expo planned. Backend needs no changes.
- **Analytics:** PostHog (frontend only, no user query text sent)
- **Rate limits:** 5/min, 30/day for search (config keys: `rate_limit_search_per_minute`, `daily_search_quota`)

---

## Execution Approach

Using **subagent-driven development**: one implementer subagent per task → spec compliance review subagent → code quality review subagent. Issues found are fixed before moving on.

Reference skill: `superpowers:subagent-driven-development`
Templates at: `/home/carter/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/subagent-driven-development/`

To resume: read this file, then `git log --oneline -15` on `feature/v2-rag`, then start Task 17.

---

## File Locations

| Area | Path |
|------|------|
| Design spec + plan | `/home/carter/.claude/plans/i-want-to-develop-crispy-journal.md` |
| DB migrations | `supabase/migrations/0004–0006_*.sql` |
| Datapipeline | `datapipeline/` |
| Backend RAG modules | `services/api/app/rag/` |
| Backend config | `services/api/app/config.py` |
| Frontend | `apps/web/src/` |
| This file | `PROGRESS.md` (repo root) |

---

*Last updated: 2026-05-30 | Completed through Task 16 | Next: Task 17 (pipeline.py + Pydantic models)*
