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
| 8 | Database migrations 0004–0006 | `2c08244` `68f7124` `96e3b3a` `072295c` | documents, chunks (HNSW), searches, retrievals, bookmarks, chunk_feedback, user_preferences. All RLS in place. |
| 9 | Datapipeline foundation | `4534e5a` `b63458f` | `datapipeline/` folder: config.py, load.py, requirements.txt, .env.example, README.md |

## In-Progress / Deferred

| # | Task | Status | Notes |
|---|------|--------|-------|
| 10 | Datapipeline: bible.py | **DEFERRED** | Draft committed at `1c921d7`. Works against real data (73 books, deuterocanonicals verified). Do NOT run until schema issue below is fixed. |
| 11–12 | Datapipeline: remaining collections + embed.py | **DEFERRED** | Build backend + frontend first. See Phase 3 in plan. |

---

## Next Task to Implement

**Task 13 — Backend: config + dependencies + openai client**

Add to `services/api/`:
- `pyproject.toml` — add `openai>=1.0.0` dependency
- `app/config.py` — add: `OPENAI_API_KEY`, `EMBEDDING_MODEL="text-embedding-3-large"`, `EMBEDDING_DIMS=1536`, `HYDE_MODEL="claude-haiku-4-5"`, `RERANK_MODEL="claude-haiku-4-5"`, `EXPLAIN_MODEL="claude-haiku-4-5"`, `DEFAULT_QUOTA=4`, `CANDIDATE_MULTIPLIER=4`, `RATE_LIMIT_PER_MINUTE=5`, `DAILY_SEARCH_QUOTA=30`
- Create `app/rag/__init__.py` (empty)

Then continue with tasks 14–20 (RAG pipeline), then 21–29 (frontend), then 30 (CLAUDE.md).

---

## Remaining Tasks (in order)

```
13  Backend: config + dependencies + openai client
14  Backend RAG: rag/hyde.py + rag/embed.py
15  Backend RAG: rag/retrieve.py
16  Backend RAG: rag/rerank.py + rag/explain.py
17  Backend RAG: rag/pipeline.py + all Pydantic models
18  Backend routes: routes/search.py  (POST /v1/search SSE, GET /v1/searches, GET /v1/searches/{id}/results)
19  Backend routes: routes/documents.py + routes/bookmarks.py + routes/feedback.py + routes/preferences.py
20  Backend: main.py (register routers) + deps/rate_limit.py (tighten limits to 5/min, 30/day)
21  Frontend: lib/api.ts extensions + lib/analytics.ts
22  Frontend: AppShell + Sidebar + layout.tsx (PostHog init)
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

### 1. documents table UNIQUE constraint is wrong for multi-translation Bible
- **Problem:** `UNIQUE(collection, title)` on `documents` means "Genesis" in CPDV and "Genesis" in Douay-Rheims would conflict.
- **Fix needed before Phase 3:** Add migration `0007` to add `translation text` column to `documents` and change unique constraint to `UNIQUE(collection, title, translation)`. Also update `datapipeline/load.py`'s `upsert_document()` signature.
- **Why deferred:** Don't need corpus ingestion until backend + frontend are working.

### 2. bible.py draft uses upsert ON CONFLICT (collection, title)
- Commit `1c921d7` has a working script but uses the wrong conflict key (see issue 1 above).
- Don't run this script until migration 0007 is applied.

### 3. The datapipeline was deprioritized in favour of building the search infrastructure first
- Decision made 2026-05-30: build backend RAG pipeline + frontend first, validate with hand-seeded data, then run ingestion.
- Reason: avoids redoing ingestion work if the pipeline architecture needs changes.

---

## Key Architecture Decisions (summary)

- **RAG strategy:** Option B — HyDE + dual vector search + full-text + per-collection re-ranking + parallel explanations
- **Re-ranking:** Haiku call per collection; quota×4 candidates → top quota; scores 0.0–1.0
- **Progressive loading:** SSE stream; chunk cards appear immediately, explanations fill in as each Haiku call completes
- **Per-source quota:** [3|4|5] control, default 4; total results = quota × active collections
- **Embedding model:** text-embedding-3-large (OpenAI, 1536 dims)
- **HNSW index:** m=16, ef_construction=64 on chunks(content_embedding)
- **Option C stubs:** `annotation` and `annotation_embedding` columns in `chunks` are NULL — ready for future annotation batch job, no code change needed to activate
- **V1 API contract preserved:** `/v1/chat`, `/v1/sessions` unchanged per CLAUDE.md
- **Mobile:** Deferred post-V2. React Native + Expo planned. Backend needs no changes.
- **Analytics:** PostHog (frontend only, no user query text sent)
- **Rate limits:** 5/minute, 30/day (tighter than V1 due to ~7 LLM sub-calls per search)

---

## File Locations

| Area | Path |
|------|------|
| Design spec + plan | `/home/carter/.claude/plans/i-want-to-develop-crispy-journal.md` |
| DB migrations | `supabase/migrations/0004–0006_*.sql` |
| Datapipeline | `datapipeline/` |
| Backend | `services/api/app/` |
| Frontend | `apps/web/src/` |
| This file | `PROGRESS.md` (repo root) |

---

## Execution Approach

Using **subagent-driven development**: one implementer subagent per task, followed by a spec compliance review subagent, then a code quality review subagent. Issues found by reviewers are fixed before moving to the next task.

Reference skill: `superpowers:subagent-driven-development`
Prompt templates at: `/home/carter/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/subagent-driven-development/`

---

*Last updated: 2026-05-30 | Next: Task 13*
