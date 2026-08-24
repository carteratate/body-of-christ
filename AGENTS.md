# AGENTS.md — Project Rules & Invariants

This repository (body-of-christ) implements a Catholic theology RAG search application.
The user-facing product name is **TheoCorpus**.
All changes MUST respect the following architectural, security, and design constraints.

---

## 0. Quick Commands

```bash
# Frontend (apps/web)
cd apps/web && npm run dev          # dev server on :3000
cd apps/web && npm run build        # production build
cd apps/web && npm run lint         # ESLint

# Backend (services/api)
cd services/api && uvicorn app.main:app --reload   # dev server on :8000
cd services/api && pytest tests/                   # run all tests

# Datapipeline (one collection; use --target reader/search for a repair)
cd datapipeline && python run_collection.py --collection bible --target both

# Docker (prod-like)
docker build -t theocorpus-api services/api
docker run --env-file services/api/.env -p 8000:8000 theocorpus-api
```

For collection publication, store repair, search-index reset, or reader wipe, read
`datapipeline/README.md` before running commands.

---

## 1. Fixed Architecture (DO NOT CHANGE)

- Monorepo with separate deploy targets:
  - `apps/web`            → Next.js (TypeScript), deployed on Vercel
  - `services/api`        → Python FastAPI, deployed on Railway (Docker)
  - `supabase/migrations` → SQL migrations only
  - `datapipeline/`       → standalone Python scripts (run locally/CI, not deployed)

- **Supabase** — Postgres (RLS, FTS via `search_vector` GIN index) + Auth
- **Qdrant** — vector store for cosine-similarity search (HNSW). Embeddings live here, NOT in pgvector.
- The frontend NEVER talks directly to the database.
- ALL client data access goes through FastAPI.
- **The frontend NEVER calls Railway directly from the browser.** All API calls go through the Vercel proxy at `apps/web/src/app/v1/[...path]/route.ts`, which forwards to Railway using the server-side `API_URL` env var. This is intentional — it avoids CORS, keeps the Railway URL private, and allows `x-internal-secret` to be added server-side.
- **`const API_URL = ""` in `apps/web/src/lib/api.ts` is correct and intentional.** The empty string causes all fetch calls to use relative paths (`/v1/...`), which hit the Vercel proxy. Do NOT change this to read from an env var. The env var that matters is server-side `API_URL` (no `NEXT_PUBLIC_` prefix), set in Vercel, used only by the proxy route.
- **`NEXT_PUBLIC_API_URL` is used only in `next.config.ts` for CSP headers.** It does NOT control where API calls are routed. Do not use it in `api.ts`.

---

## 2. Authentication & Authorization (CRITICAL)

- Auth via Supabase Auth; frontend sends JWT as `Authorization: Bearer <token>`.
- Backend MUST verify Supabase JWT (signature, expiration, issuer) and extract `user_id` from `sub`.
- RLS MUST be enabled on all user-owned tables.
- Supabase service role key MUST NEVER appear in frontend code.

---

## 3. API Design (STABILITY REQUIRED)

All endpoints under `/v1/...`.

### POST /v1/chat (NON-NEGOTIABLE CONTRACT)

Request:
- session_id: string | null
- message: string
- filters: { collections: string[] }
- top_k?: number
- min_score?: number

Response:
- session_id: string
- message_id: string
- answer: string
- sources: []   // empty in V1, populated in V2+

This contract MUST NOT change across versions.

---

## 4. Data Model

### V1 Tables
- `chat_sessions` (id, user_id, title, created_at, updated_at)
- `chat_messages` (id, session_id, user_id, role, content, created_at)
- `user_usage` (user_id, rate_window_start, rate_count, quota_date, quota_count, evaluate_date, evaluate_count)

### V2 Tables (live — migrations 0004–0017 applied)
- `documents` (id, collection, title, author, year, translation, metadata jsonb, created_at)
- `chunks` (id, document_id, content, position, anchor, chapter_key, chapter_label, unit_label, reference, search_vector tsvector, content_embedding vector, annotation, annotation_embedding)
- `searches` (id, user_id, query, filters jsonb, result_count, created_at)
- `retrievals` (id, search_id, chunk_id, rank, reranker_score, explanation)
- `bookmarks` (id, user_id, chunk_id, note, created_at)
- `chunk_feedback` (id, user_id, chunk_id, feedback)
- `user_preferences` (user_id, preferred_translation, default_collections, default_quota, theme)

SQL migrations ONLY. Schema changes must be additive. RLS on all user-owned tables.

---

## 5. RAG Pipeline (V2)

Full pipeline in `services/api/app/rag/pipeline.py`:

1. **HyDE** — per-collection hypothetical passage generation (`hyde.py`)
2. **Embed** — concurrent embedding of query + HyDE passages via OpenAI `text-embedding-3-large` (`embed.py`)
3. **Retrieve** — per-collection parallel search: Qdrant cosine vector search + Supabase FTS, merged with RRF (k=60) (`retrieve.py`)
4. **Rerank** — per-collection Codex Haiku re-ranking (0.0–1.0 scores); global sort + collection guarantee (`rerank.py`)
5. **Stream chunks** — yield `chunk` SSE events immediately after reranking
6. **Persist** — insert search + retrievals to DB
7. **Yield done** — `done` SSE event with search_id
8. **Explain** — sequential streaming explanation per chunk via `explanation_delta` SSE events (`explain.py`)

No LangGraph or agent frameworks. No pgvector for retrieval (embeddings are in Qdrant only).

---

## 6. Deployment

- Backend: Docker → Railway. Same image runs locally and in prod.
- Frontend: Vercel.
- Config via environment variables only.
- Required health endpoints: GET /health, GET /health/db

---

## 7. Coding Standards

- Backend: FastAPI + Pydantic, structured logging, no secrets logged.
- Frontend: TypeScript, API calls centralized in `src/lib/api.ts`, no DB SDK in frontend.

---

## 8. Non-Goals

- No direct DB queries from frontend
- No serverless backend (Lambda, Supabase Edge Functions)
- No Kubernetes, no agent frameworks, no premature microservices

---

## 9. Design System — Sacred Night (dark mode, default)

| Token | Value | Usage |
|---|---|---|
| Background | `#090E1A` | Page background |
| Surface | `#111829` | Cards, sidebar, bubbles |
| Accent | `#C4972A` | CTAs, links, active states |
| Text primary | `#EAE6DC` | Body text, headings |
| Text muted | `#7A8099` | Timestamps, placeholders |

Use CSS custom properties via Tailwind `brand` namespace. No hardcoded hex values in components.

---

## 10. Routes

### Frontend Routes

| Route | File | Notes |
|---|---|---|
| `/` | `app/page.tsx` | Redirect → /search (authed) or /login |
| `/login` | `app/login/page.tsx` | Supabase auth form |
| `/update-password` | `app/update-password/page.tsx` | Password reset flow |
| `/chat` | `app/chat/page.tsx` | `redirect` to /search (307) |
| `/search` | `app/search/page.tsx` | Main V2 search interface |
| `/bookmarks` | `app/bookmarks/page.tsx` | Saved passages |
| `/reader/[docId]` | `app/reader/[docId]/page.tsx` | Document reader (chapter-based) |
| `/sources` | `app/sources/page.tsx` | Corpus document browser |
| `/discover` | `app/discover/page.tsx` | AI collection scorer (evaluate endpoint) |
| `/about` | `app/about/page.tsx` | Product info page |
| `/settings` | `app/settings/page.tsx` | User preferences |

### API Endpoints (all under /v1/, require JWT)

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/me` | Current user info |
| POST | `/v1/search` | SSE stream; rate-limited (5/min, 30/day) |
| GET | `/v1/searches` | Search history (last 50) |
| GET | `/v1/searches/{id}/results` | Restore past search from retrievals |
| GET | `/v1/documents/{id}` | Document metadata + chunk count |
| GET | `/v1/documents/{id}/toc` | Ordered chapter list for reader |
| GET | `/v1/documents/{id}/reader` | One chapter of passages (anchor or chapter param) |
| GET | `/v1/sources` | All documents with chunk counts; 1h in-memory cache |
| POST | `/v1/evaluate` | AI scores each collection for a query; 10/day limit |
| POST | `/v1/bookmarks` | Body: `{chunk_id}` |
| GET | `/v1/bookmarks` | List user bookmarks (with joined chunk content) |
| PATCH | `/v1/bookmarks/{id}` | Body: `{note}` — update personal note |
| DELETE | `/v1/bookmarks/{id}` | Remove bookmark |
| POST | `/v1/feedback` | Body: `{chunk_id, feedback: "up"\|"down", search_id?}` |
| GET | `/v1/preferences` | Fetch user preferences |
| PUT | `/v1/preferences` | Update user preferences |

---

## 11. Component Locations

- **Search:** `apps/web/src/components/search/`
  - `SearchPage.tsx`, `ChunkCard.tsx`, `SearchResults.tsx`, `ResultsSkeleton.tsx`, `EmptyState.tsx`, `RelevanceExplanation.tsx`
  - `BottomBar.tsx` — SearchBar + CollectionToggles + QuotaControl composed
  - `SearchBar.tsx`, `CollectionToggles.tsx`, `QuotaControl.tsx`, `TranslationSelector.tsx`
  - `SearchProgress.tsx`, `LoadingAnimation.tsx`, `NoResultsScreen.tsx`, `ResultFilterBar.tsx`
- **Reader:** `apps/web/src/components/reader/`
  - `DocumentReader.tsx`, `ReaderChrome.tsx`, `ChapterSection.tsx`, `Passage.tsx`, `ContentsDrawer.tsx`
- **Bookmarks:** `apps/web/src/components/bookmarks/`
  - `BookmarksPage.tsx`, `BookmarkCard.tsx`
- **Discover:** `apps/web/src/components/discover/`
  - `DiscoverPage.tsx`, `RelevanceChart.tsx`
- **Sources:** `apps/web/src/components/sources/`
  - `SourcesPage.tsx`
- **About:** `apps/web/src/components/about/`
  - `AboutPage.tsx`
- **Settings:** `apps/web/src/components/settings/`
  - `SettingsPage.tsx`
- **Auth:** `apps/web/src/components/auth/`
  - `LoginForm.tsx`
- **Chat (legacy):** `apps/web/src/components/chat/`
  - `ChatShell.tsx`
- **Common:** `apps/web/src/components/common/`
  - `RateLimitModal.tsx`, `Toast.tsx` (+ `useToast` hook), `ErrorBoundary.tsx`
- **Layout:** `apps/web/src/components/layout/`
  - `AppShell.tsx`, `Sidebar.tsx`, `PostHogProvider.tsx`

---

## 12. AppContext

- Provided by `AppShell` (`apps/web/src/components/layout/AppShell.tsx`)
- Consumed via `useAppContext()` hook exported from `AppShell.tsx`
- **ALL authenticated pages MUST be wrapped in AppShell**

| Value | Type | Notes |
|---|---|---|
| `token` | `string \| null` | Supabase JWT |
| `ready` | `boolean` | True once auth state resolved |
| `preferences` | `Preferences \| null` | Fetched on mount via GET /v1/preferences |
| `setPreferences` | `(p: Preferences) => void` | Updates local context only |
| `preferencesError` | `boolean` | True if preferences fetch failed |
| `searches` | `SearchSummaryV2[]` | DB-backed search history |
| `refreshSearches` | `() => void` | Re-fetches search history from API |
| `pendingSearch` | `{ id, query } \| null` | In-flight search slot (separate from DB list) |
| `setPendingSearch` | `(id, query) => void` | — |
| `clearPendingSearch` | `() => void` | — |
| `activeSearchId` | `string \| null` | Currently displayed search |
| `setActiveSearchId` | `(id \| null) => void` | — |
| `searchKey` | `number` | Increment triggers new search render |
| `newSearch` | `() => void` | Resets searchKey + activeSearchId |
| `corpusPassages` | `number \| null` | Total passages; populated lazily by /sources |
| `setCorpusPassages` | `(n: number) => void` | — |

**Auto-save** on toggle/quota/translation change is handled in `SearchPage.tsx` and `CollectionToggles.tsx` via debounced `PUT /v1/preferences` calls — NOT in AppShell.

---

## 13. Collections — Canonical Source

- **Single source of truth:** `services/api/app/rag/constants.py` (`VALID_COLLECTIONS`)
- **Frontend mirror:** `apps/web/src/lib/collections.ts` (includes CSS var colors per collection)
- **To add a new collection:** update `constants.py` first, then sync `collections.ts`

### Current Collections (10)

| Key | Label | Hex |
|---|---|---|
| `bible` | Bible | `#d4885a` |
| `catechism` | Catechism | `#5b9bd4` |
| `summa` | Summa Theologica | `#55cc88` |
| `encyclicals` | Encyclicals | `#e8c040` |
| `councils` | Councils | `#60d4c8` |
| `church-fathers` | Church Fathers | `#b070d4` |
| `medieval` | Medieval | `#90a0a8` |
| `canon-law` | Canon Law | `#e84040` |
| `apostolic-exhortations` | Apostolic Exhortations | `#4858c8` |
| `papal-documents` | Papal Documents | `#b86080` |

Colors are defined as CSS custom properties (e.g. `var(--color-collection-bible)`) — use those in components, not raw hex.

---

## 14. SSE Streaming

- **Client function:** `streamSearch()` in `apps/web/src/lib/api.ts`
- **Signature:** `streamSearch(token, query, filters, quota, callbacks, signal?)`
- **Callbacks:**
  - `onChunk(chunk: ChunkResult)` — ranked result chunk
  - `onExplanationDelta(chunkId: string, delta: string)` — streams explanation text incrementally
  - `onDone(searchId: string, resultCount: number)` — pipeline complete
  - `onError(message: string)` — pipeline error
  - `onRateLimit(retryAfter: number | null, limitType: "per_minute" | "daily")` — 429 response
  - `onStatus?(phase: "searching" | "ranking", collections?: string[])` — optional progress updates
- **SSE event types from backend:** `"chunk"`, `"explanation_delta"`, `"done"`, `"error"`, `"status"`
- **Rate limit detection:** 429 response body parsed; `detail` containing `"daily"` → `limitType="daily"`, else `"per_minute"`
- **Cleanup:** Pass an `AbortController.signal`; call `controller.abort()` on component unmount

---

## 15. V2 Data Model — Actual State

All 17 migrations (0001–0017) are applied. Notable migrations beyond the V2 foundation:

| Migration | What it adds |
|---|---|
| 0008 | `translation` column on `documents`; `UNIQUE(collection, title, translation)` |
| 0010 | `metadata jsonb` on `chunks` |
| 0011 | `medieval` and `councils` collections added to DB constraints |
| 0012 | `theme` column on `user_preferences` |
| 0013 | `anchor`, `chapter_key`, `chapter_label`, `unit_label` passage columns on `chunks` |
| 0014 | `UNIQUE(title, author)` on documents (title-author dedup) |
| 0015 | `apostolic-exhortations` and `papal-documents` collections |
| 0016 | `note text` column on `bookmarks` |
| 0017 | `evaluate_date` + `evaluate_count` columns on `user_usage` |

**`content_embedding` (vector) column exists on `chunks` but is unused for retrieval** — embeddings live in Qdrant. The column is vestigial and can be ignored.

---

## 16. CSP Headers

- Defined in `apps/web/next.config.ts`
- **`script-src` and `default-src` are intentionally omitted** — nonce-based CSP is deferred; `unsafe-inline` is required for Next.js hydration in the interim, so these directives are excluded rather than creating a false sense of security
- **`connect-src` includes:** `'self'`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `https://app.posthog.com`, `https://eu.posthog.com`
- **NEVER add `unsafe-eval` to `script-src`**

---

## 17. Known Issues & Deferred Work

### 1. Shared Rate Limit Counter (V1 chat / V2 search)

V1 chat and V2 search share `user_usage.rate_count` / `quota_count` columns. V2 enforces 5/min and 30/day; V1 enforces 10/min. This creates cross-contamination. `TODO` comment in `routes/search.py` → `check_search_rate_limit`.

**Future fix:** add `search_rate_count` / `search_quota_count` columns to `user_usage`.

### 2. JWKS Cache Thundering Herd

Under concurrent load, multiple coroutines can all find the JWKS cache stale and fire simultaneous HTTP requests to Supabase. Low priority; fix with double-checked locking in a future maintenance pass.

### 3. `content_embedding` Column is Vestigial

`chunks.content_embedding` exists in the schema but is not populated or used — Qdrant handles all vector search. Do not write code that reads from or writes to this column.

---

## Agent skills

### Issue tracker

Issues and specifications are tracked in GitHub Issues for `carteratate/body-of-christ`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default Matt Pocock triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context documentation layout. See `docs/agents/domain.md`.
