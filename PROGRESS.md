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
| 14 | Backend RAG: hyde.py + embed.py | `927df4c` `61fdb79` | HyDE passage generation with fallback; OpenAI text-embedding-3-large wrapper with index-sorted batch |
| 15 | Backend RAG: retrieve.py | `062cb7b` | Dual vector + FTS with RRF (k=60); asyncio.gather; dislike filter; Option C stub |
| 16 | Backend RAG: rerank.py + explain.py | `f2d26d2` | Per-collection Haiku re-ranking (0.0–1.0 scores, fallback); parallel explanation generation |
| 17 | Backend RAG: pipeline.py + Pydantic models | `fc81e26` `2609dc9` | Full SSE pipeline orchestrator; all 5 model files; security fixes (jsonb, task leak, error leakage, UUID validation) |
| 18 | Backend routes: search.py | `5bfad7e` `4066e14` | POST /search SSE, GET /searches, GET /searches/{id}/results; collection allowlist; rate limit dep |
| 19 | Backend routes: documents + bookmarks + feedback + preferences | `75edabc` `549f6d2` | All supporting CRUD routes; ownership checks; Query() annotations |
| 20 | Backend: main.py + rate_limit.py updates | `259aa27` | All 8 routers registered; all 4 RAG singletons in lifespan; production INTERNAL_API_SECRET guard added |
| 21 | Frontend: api.ts extensions + analytics.ts | `eb39283` `d90c2cf` | All V2 API functions + SSE streaming; 14 PostHog event wrappers; posthog-js installed |
| 22 | Frontend: AppShell + Sidebar + layout | `0438758` | AppShell with AppContext (token, preferences); Sidebar with search history; PostHog provider; middleware updated for /search /bookmarks /reader |
| 23 | Canon Law + search bottom bar | `c2b006a`–`4b9a351` | Migration 0007 (canon-law collection); backend allowlists updated; `rag/constants.py` (single VALID_COLLECTIONS source); `collections.ts` with CSS var colors; TranslationSelector, QuotaControl, SearchBar, CollectionToggles, BottomBar components + barrel export. Spec + security reviewed. |

## Deferred (Phase 3 — after frontend is working)

| # | Task | Notes |
|---|------|-------|
| 11 | catechism + encyclicals + church_fathers + saints | Build frontend first |
| 12 | embed.py + run_all.py | Build frontend first |

---

## Next Task to Implement

**Task 24 — Frontend: EmptyState (suggested query chips) + SearchPage.tsx state orchestration**

Build the search page shell: `app/search/page.tsx` rendering an `AppShell` with a flex-column main area. The main area: `EmptyState` (suggested query chips grid, fires a search on chip click) fills the results region before first query; `BottomBar` sits at the bottom. `SearchPage` manages all state: `activeCollections`, `translation`, `quota`, `searchValue`, `loading`, `results`, `searchId`. Wire `streamSearch()` to `BottomBar.onSearch`.

---

## Remaining Tasks (in order)

```
24  Frontend: EmptyState (suggested query chips) + SearchPage.tsx state orchestration
25  Frontend: ChunkCard + RelevanceExplanation + ResultsSkeleton + SearchResults (progressive SSE)
26  Frontend: DocumentReader + ReaderToolbar + ReaderChunk  (/reader/[docId])
27  Frontend: BookmarksPage + BookmarkCard  (/bookmarks)
28  Frontend: RateLimitModal + Toast + ErrorBoundary (common components)
29  Frontend: /chat redirect + all page routes + loading/error states + next.config.ts CSP headers
30  CLAUDE.md update with V2 invariants
--- PHASE 3 (after frontend is working) ---
31  Fix documents schema: add `translation` column + migration 0008
32  Datapipeline: bible.py (fix conflict key, then run)
33  Datapipeline: catechism.py, encyclicals.py, church_fathers.py, saints.py
34  Datapipeline: embed.py + run_all.py
```

---

## Known Issues / Gotchas

### 1. documents table UNIQUE constraint needs translation column (Phase 3 blocker)
- `documents` uses `UNIQUE(collection, title)` — conflicts when two Bible translations share a book name.
- Fix: add migration `0008` with `translation text` column and `UNIQUE(collection, title, translation)`.
- Note: `0007` was used for the canon-law collection addition; translation column fix is now `0008`.
- Also update `datapipeline/load.py`'s `upsert_document()`.
- **Do not run any datapipeline scripts until this is fixed.**

### 2. bible.py draft exists but deferred
- Commit `1c921d7` has a working, real-data-verified script. Don't run it until issue #1 is fixed.

### 3. Shared rate limit counter for V1 chat and V2 search
- Both currently share `user_usage.rate_count`/`quota_count` columns.
- V2 uses `rate_limit_search_per_minute=5`, V1 uses `rate_limit_per_minute=10`.
- A `TODO` comment is in `routes/search.py`'s `check_search_rate_limit`.
- Future improvement: add `search_rate_count`/`search_quota_count` columns in migration 0007.

### 4. JWKS cache thundering herd (pre-existing V1 issue)
- Under concurrent load, multiple coroutines can all find the JWKS cache stale and fire simultaneous HTTP requests to Supabase.
- Low priority for V2 launch; fix in V2.1 with double-checked locking.

---

## Key Architecture Decisions

- **RAG strategy:** Option B — HyDE + dual vector search + full-text + per-collection re-ranking + parallel explanations
- **Re-ranking:** Haiku per collection; quota×4 candidates → top quota; scores 0.0–1.0; fallback to RRF order on failure
- **Progressive loading:** SSE stream — chunk events first, explanations fill in as each Haiku call completes
- **Per-source quota:** [3|4|5] control, default 4; total = quota × active collections
- **Embedding model:** text-embedding-3-large (OpenAI, 1536 dims)
- **HNSW index:** m=16, ef_construction=64 on chunks(content_embedding)
- **Option C stubs:** `annotation`/`annotation_embedding` columns NULL — no code change needed to activate
- **V1 API contract preserved:** `/v1/chat`, `/v1/sessions` unchanged
- **AppContext:** Token + preferences managed in AppShell, shared via React context to all child components
- **Preferences auto-save:** Changes to collection toggles and quota debounce-save via `PUT /v1/preferences`
- **Mobile:** Deferred post-V2. React Native + Expo planned. Backend needs no changes.
- **Analytics:** PostHog (frontend only, no user query text sent)
- **Rate limits:** 5/min, 30/day for search

---

## Execution Approach

Using **subagent-driven development**: one implementer subagent per task → spec compliance review → code quality review. Issues found are fixed before moving on.

Skill templates at: `/home/carter/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/subagent-driven-development/`

To resume: read this file, then `git log --oneline -15` on `feature/v2-rag`, then start **Task 24**.

---

## File Locations

| Area | Path |
|------|------|
| Design spec + plan | `/home/carter/.claude/plans/i-want-to-develop-crispy-journal.md` |
| DB migrations | `supabase/migrations/0004–0007_*.sql` |
| Datapipeline | `datapipeline/` |
| Backend RAG modules | `services/api/app/rag/` (incl. `constants.py` — canonical VALID_COLLECTIONS) |
| Backend routes | `services/api/app/routes/` |
| Frontend components | `apps/web/src/components/` |
| Frontend pages | `apps/web/src/app/` |
| Frontend API client | `apps/web/src/lib/api.ts` |
| Frontend analytics | `apps/web/src/lib/analytics.ts` |
| AppContext (token + prefs) | `apps/web/src/components/layout/AppShell.tsx` |
| This file | `PROGRESS.md` (repo root) |

---

*Last updated: 2026-05-30 | Completed through Task 23 + post-task cleanup | Next: Task 24 (EmptyState + SearchPage orchestration)*
