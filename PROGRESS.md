# TheoCorpus V2 — Implementation Progress

> **Historical implementation log.** File names and operational commands below record
> the repository at the time of each entry. Use
> [`datapipeline/README.md`](datapipeline/README.md) for the current collection
> publication and repair interface.

> **Purpose:** Preserve the V2 implementation sequence and decisions as a historical
> record. Current operational guidance lives in the linked subsystem documentation.

---

## Branch
`master` (V2 feature branch was merged)

## Plan File
`/home/carter/.claude/plans/i-want-to-develop-crispy-journal.md`
Historical external plan path, retained as provenance; it is not available in this
repository and is not current architectural guidance.

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
| 24 | EmptyState + SearchPage orchestration | `6f7b831`–`1d722db` | `EmptyState.tsx` (8 suggested query chips, 2-col grid); `SearchPage.tsx` (full state: activeCollections, translation, quota, searchValue, loading, results, searchId; SSE streaming via streamSearch; ?restore= flow; abort on unmount); `app/search/page.tsx` (AppShell wrapper). Spec, quality (abort leak fix, restore ref fix), and security reviewed (error classification, UUID param validation). |
| 25 | ChunkCard + RelevanceExplanation + ResultsSkeleton + SearchResults | `fe525de`–`f98f8c1` | `ChunkCard.tsx` (6 wired actions: bookmark toggle, clipboard copy, read more router.push, thumbs up/down, explore more; collection left border; bible badge translation; all analytics wired); `RelevanceExplanation.tsx` (null→shimmer, ""→null, string→text); `ResultsSkeleton.tsx` (4 ghost cards, animate-pulse); `SearchResults.tsx` (progressive reveal: skeleton when loading+empty, ChunkCard list otherwise). SearchPage updated with handleExploreMore (300ms debounced, cancels on keypress, stable useCallback). Spec, quality (hover token, stale closure, bookmark analytics, design system danger token, aria-labels), and security reviewed (UUID-guard on Read More nav). |
| 26 | DocumentReader + ReaderToolbar + ReaderChunk (/reader/[docId]) | `7a999b5`–`51214ea` | `DocumentReader.tsx` (fetches getReader, loading skeleton, error/404 states, scroll origin into view, prev/next/jump navigation, ?explore= routing); `ReaderToolbar.tsx` (← Results, collection badge, position info, prev/next disabled at doc boundaries, jump by position or reference substring); `ReaderChunk.tsx` (gold border + "← Your result" for origin chunk, bookmark/copy/explore-more actions, trackExploreMoreClicked source:"reader"); `app/reader/[docId]/page.tsx` (Next.js 15 async params); `components/reader/index.ts` barrel export. SearchPage.tsx updated with ?explore= param reading (auto-fills search + 100ms auto-submit, exploredForQuery ref guard). Spec compliance (double-trim fix, missing chunk_id guard, 404 check hardening) and code quality (copy format parenthetical) reviewed and fixed. |
| 27 | BookmarksPage + BookmarkCard (/bookmarks) | `da55cc8` | `BookmarkCard.tsx` (collection-colored left border, badge, reference, 3 actions: remove bookmark fire-and-forget, copy, explore-more; null chunk fallback; token typed string\|null with API guards; navigator.clipboard guard); `BookmarksPage.tsx` (useCallback fetch, 3-ghost-card skeleton, empty state + "Start Searching" link, error state + Retry, optimistic removal via local filter); `app/bookmarks/page.tsx` (AppShell wrapper); `components/bookmarks/index.ts` barrel export. No Read More — BookmarkChunkInfo.source has no document_id. Spec, quality (useCallback, clipboard guard, token null safety), and security reviewed. |
| 28 | Frontend: RateLimitModal + Toast + ErrorBoundary (common components) | `3dcb3be` `5dc6a1b` `cc351c4` | `RateLimitModal.tsx` (portal via ReactDOM.createPortal, countdown timer, backdrop dismiss, trackRateLimitHit on open, ARIA role="dialog"); `Toast.tsx` + `useToast` hook (fixed bottom-right, 3s auto-dismiss, stable useCallback in hook, role="status"); `ErrorBoundary.tsx` (class component, getDerivedStateFromError, componentDidCatch fires trackErrorOccurred with hardcoded "render_error" — raw error.message never sent to PostHog); `components/common/index.ts` barrel export. Spec, quality (interval leak fix, stale closure fix, ARIA), and security (no PII in telemetry) reviewed. |
| 29 | Frontend: /chat redirect + all page routes + loading/error states + next.config.ts CSP headers | `8534305` `74fdf40` | `app/chat/page.tsx` (redirect → /search); `app/page.tsx` (authenticated root → /search); `api.ts` onRateLimit now passes limitType ("per_minute"\|"daily") by reading 429 body; `SearchPage.tsx` (RateLimitModal replaces inline placeholder, rateLimitType state, reset on new search); `ChunkCard.tsx` (Toast via portal on bookmark/copy success+failure); `BookmarksPage.tsx` (Toast, passes showToast to BookmarkCard); `BookmarkCard.tsx` (handleRemove post-success, Toast on remove failure and copy); ErrorBoundary wraps SearchPage/BookmarksPage/DocumentReader in page routes; loading.tsx files for /search, /bookmarks, /reader/[docId]; CSP headers in next.config.ts (no unsafe-eval, unsafe-inline for script-src required by Next.js hydration). Spec (37/37), quality (Toast portal, remove rollback, CSP), and fix re-review all passed. |
| 30 | CLAUDE.md update with V2 invariants | (see commit) | Added sections 10–17: V2 routes, component locations, AppContext, Collections canonical source (constants.py + collections.ts), SSE streaming callbacks, V2 data model actual state, CSP headers, known issues & deferred work. 7 code quality issues found and fixed (PostHog domains, redirect type, setPreferences in context, auto-save attribution, BottomBar description, PostHogProvider location, streamSearch signal param). |
| 31 | Fix documents schema: translation column + migration 0008 | `c2dcd8a` `628ab05` `c79279b` `317c24a` | Migration 0008: `ADD COLUMN translation text NOT NULL DEFAULT ''`, `ADD CONSTRAINT UNIQUE(collection,title,translation)`. `load.py` `upsert_document()` updated (new translation param, `translation or ""` coercion, new conflict target). `bible.py` call site updated to pass `translation=translation`. datapipeline/README.md DO NOT RUN gate added. |

## Phase 3 — Datapipeline (completed)

All corpus ingestion scripts are built and live in `datapipeline/ingest/`:

| Script | Collection |
|---|---|
| `bible.py` | Bible (CPDV + Douay-Rheims) |
| `catechism.py` | Catechism of the Catholic Church |
| `encyclicals.py` | Papal encyclicals (1740–2025) |
| `church_fathers.py` | Ante-Nicene + Nicene/Post-Nicene Fathers |
| `summa.py` | Summa Theologiae |
| `canon_law.py` | 1983 Code of Canon Law |
| `medieval.py` | Medieval theology (Anselm, Boethius, à Kempis…) |
| `councils.py` | Ecumenical councils + Vatican II |
| `apostolic_exhortations.py` | Post-synodal apostolic exhortations |
| `papal_documents.py` | Papal bulls and apostolic letters |
| `thml_doc.py` | THML format parser (CCEL sources) |

Supporting: `embed.py` (push to Qdrant), `load.py` (upsert to Supabase), `normalize/` (text cleaning)

---

## Known Issues / Gotchas

### ~~1. documents table UNIQUE constraint needs translation column~~ ✅ RESOLVED (Migration 0008)

### ~~2. bible.py data-blocked~~ ✅ RESOLVED — bible.py complete with CPDV + Douay-Rheims

### 3. Shared rate limit counter for V1 chat and V2 search
- Both currently share `user_usage.rate_count`/`quota_count` columns.
- V2 uses `rate_limit_search_per_minute=5`, V1 uses `rate_limit_per_minute=10`.
- A `TODO` comment is in `routes/search.py`'s `check_search_rate_limit`.
- Future fix: add `search_rate_count`/`search_quota_count` columns in a new migration.

### 4. JWKS cache thundering herd (pre-existing V1 issue)
- Under concurrent load, multiple coroutines can all find the JWKS cache stale and fire simultaneous HTTP requests to Supabase.
- Low priority; fix with double-checked locking in a future maintenance pass.

---

## Key Architecture Decisions

- **RAG strategy:** HyDE + concurrent per-collection Qdrant vector search + Supabase FTS + RRF merge + per-collection Haiku re-ranking + streaming explanation deltas
- **Vector store:** Qdrant (cosine HNSW). `chunks.content_embedding` in Postgres is vestigial — not used for retrieval.
- **Re-ranking:** Claude Haiku per collection; quota×candidate_multiplier candidates → top quota; scores 0.0–1.0; fallback to RRF order on failure
- **Progressive loading:** SSE stream — `chunk` events first, `done` event, then `explanation_delta` events stream in sequentially
- **Per-source quota:** [3|4|5] control, default 4; total = quota × active collections
- **Embedding model:** text-embedding-3-large (OpenAI, 1536 dims)
- **V1 API contract preserved:** `/v1/chat`, `/v1/sessions` unchanged
- **AppContext:** Token, preferences, search history, pending search slot, active search ID, corpus passage count — all in AppShell
- **Preferences auto-save:** Collection toggles and quota debounce-save via `PUT /v1/preferences`
- **Mobile:** Deferred. React Native + Expo planned. Backend needs no changes.
- **Analytics:** PostHog (frontend only, no user query text sent)
- **Rate limits:** Search: 5/min, 30/day | Evaluate: 10/day | Bookmark writes: 20/min

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
| DB migrations | `supabase/migrations/0001–0017_*.sql` |
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

*Last updated: 2026-06-23 | V2 fully shipped to master | All datapipeline scripts built | 10 collections live | Migrations 0001–0017 applied*
