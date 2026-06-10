# CLAUDE.md — Project Rules & Invariants

This repository (body-of-christ) implements a Catholic theology RAG chat application.
The user-facing product name is **Body of Christ**.
All changes MUST respect the following architectural, security, and design constraints.

---

## 1. Fixed Architecture (DO NOT CHANGE)

- Monorepo with separate deploy targets:
  - apps/web      → Next.js (TypeScript), deployed on Vercel
  - services/api  → Python FastAPI, deployed on Railway (Docker)
  - supabase/migrations → SQL migrations only

- Supabase is used for Postgres + pgvector (V2) + Auth.
- The frontend NEVER talks directly to the database.
- ALL client data access goes through FastAPI.

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
- chat_sessions (id, user_id, title, created_at, updated_at)
- chat_messages (id, session_id, user_id, role, content, created_at)
- user_usage (user_id, rate_window_start, rate_count, quota_date, quota_count)

### V2 Tables (planned)
- documents (id, collection, title, metadata)
- chunks (id, document_id, content, position)
- embeddings (chunk_id, embedding pgvector)
- retrievals (message_id ↔ chunk_id ↔ score)

### Planned collections (V2 filter values)
- "bible" — book/chapter/verse hierarchy, translation metadata
- "catechism" — numbered CCC paragraphs, part/section/chapter structure
- "encyclicals" — pope, year, topic tags
- "church-fathers" — author, work, century, tradition
- "summa" — Aquinas Summa Theologiae, part/treatise/question/article structure

SQL migrations ONLY. Schema changes must be additive. RLS on all user-owned tables.

---

## 5. RAG Rules (V2+)

Explicit pipeline: embed query → vector search with collection filters → apply thresholds → return excerpts → LLM explains relevance.
No LangGraph or agent frameworks.

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

## 10. V2 Routes

### Frontend Routes

| Route | File | Notes |
|---|---|---|
| `/` | `app/page.tsx` | Redirect → /search (authed) or /login |
| `/chat` | `app/chat/page.tsx` | `redirect` to /search (307) |
| `/search` | `app/search/page.tsx` | Main V2 search interface |
| `/bookmarks` | `app/bookmarks/page.tsx` | Saved passages |
| `/reader/[docId]` | `app/reader/[docId]/page.tsx` | Document reader |

### V2 API Endpoints (all under /v1/, require JWT)

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/search` | SSE stream; rate-limited (5/min, 30/day) |
| GET | `/v1/searches` | Search history (last 50) |
| GET | `/v1/searches/{id}/results` | Restore past search from retrievals |
| GET | `/v1/documents/{id}` | Document metadata only (NOT full chunk array) |
| GET | `/v1/documents/{id}/reader` | ±context chunks around chunk_id |
| POST | `/v1/bookmarks` | Body: `{chunk_id}` |
| GET | `/v1/bookmarks` | List user bookmarks |
| DELETE | `/v1/bookmarks/{id}` | Remove bookmark |
| POST | `/v1/feedback` | Body: `{chunk_id, feedback: "up"\|"down", search_id?}` |
| GET | `/v1/preferences` | Fetch user preferences |
| PUT | `/v1/preferences` | Update user preferences |

---

## 11. V2 Component Locations

- **Search:** `apps/web/src/components/search/`
  - `SearchPage.tsx`, `ChunkCard.tsx`, `SearchResults.tsx`, `ResultsSkeleton.tsx`, `EmptyState.tsx`, `RelevanceExplanation.tsx`
  - `BottomBar.tsx` — composed component that renders SearchBar + CollectionToggles + QuotaControl
- **Reader:** `apps/web/src/components/reader/`
  - `DocumentReader.tsx`, `ReaderToolbar.tsx`, `ReaderChunk.tsx`
- **Bookmarks:** `apps/web/src/components/bookmarks/`
  - `BookmarksPage.tsx`, `BookmarkCard.tsx`
- **Common:** `apps/web/src/components/common/`
  - `RateLimitModal.tsx`, `Toast.tsx` (+ `useToast` hook), `ErrorBoundary.tsx`
- **Layout:** `apps/web/src/components/layout/`
  - `AppShell.tsx`, `Sidebar.tsx`
  - `apps/web/src/components/layout/PostHogProvider.tsx` — PostHog analytics provider (imported by `app/layout.tsx`)

---

## 12. AppContext

- Provided by `AppShell` (`apps/web/src/components/layout/AppShell.tsx`)
- Provides: `token` (`string | null`), `preferences` (`UserPreferences | null`), `setPreferences` (`(p: Preferences) => void`)
- Consumed via `useAppContext()` hook exported from `AppShell.tsx`
- Preferences fetched on mount via `GET /v1/preferences`; `setPreferences` updates local context state
- **Auto-save** on toggle/quota/translation change is handled in `SearchPage.tsx` and `CollectionToggles.tsx` via debounced `PUT /v1/preferences` calls — NOT in AppShell
- **ALL authenticated pages MUST be wrapped in AppShell**

---

## 13. Collections — Canonical Source

- **Single source of truth:** `services/api/app/rag/constants.py` (`VALID_COLLECTIONS`)
- **Frontend mirror:** `apps/web/src/lib/collections.ts` (includes CSS var colors per collection)
- **Current values:** `"bible"`, `"catechism"`, `"church-fathers"`, `"encyclicals"`, `"summa"`, `"canon-law"`
- **To add a new collection:** update `constants.py` first, then sync `collections.ts`

### Collection Color Coding (left border + badge)

| Collection | Color | Hex |
|---|---|---|
| bible | green | `#4caf50` |
| catechism | blue | `#4a6fa5` |
| church-fathers | purple | `#7c6fa5` |
| encyclicals | amber | `#b5892a` |
| summa | warm brown | `#8B7355` |
| canon-law | red-brown | `#8B4513` |

---

## 14. SSE Streaming

- **Client function:** `streamSearch()` in `apps/web/src/lib/api.ts`
- **Signature:** `streamSearch(query, filters, quota, token, callbacks, signal?)`
- **Callbacks:**
  - `onChunk(chunk)` — receives each ranked result chunk
  - `onExplanation(chunk_id, explanation)` — LLM relevance explanation for a chunk
  - `onDone(search_id, result_count)` — pipeline complete
  - `onError(message)` — pipeline error
  - `onRateLimit(retryAfter: number, limitType: "per_minute" | "daily")` — 429 response
- **SSE event types from backend:** `"chunk"`, `"explanation"`, `"done"`, `"error"`
- **Rate limit detection:** 429 response body is parsed; if `detail` string contains `"daily"` → `limitType="daily"`, otherwise `limitType="per_minute"`
- **Cleanup:** Pass an `AbortController.signal` as the `signal?` parameter; call `controller.abort()` on component unmount

---

## 15. V2 Data Model — Actual State

> See §4 for the original V2 schema sketch. This section documents what is actually live.

**Migrations 0004–0007 are applied.** V2 tables are live, not planned.

### documents
- Columns: `id`, `collection`, `title`, `author`, `year`, `metadata jsonb`, `created_at`
- **Known issue:** `UNIQUE(collection, title)` constraint conflicts when two Bible translations share a book name. Migration 0008 (pending) adds a `translation text` column and changes the constraint to `UNIQUE(collection, title, translation)`. **DO NOT run any datapipeline scripts until migration 0008 is applied.** (See §17.)

### chunks
- `HNSW` index (`m=16`, `ef_construction=64`) on `content_embedding`
- `GIN` index on `search_vector`
- Option C stub columns (`annotation`, `annotation_embedding`) exist but are `NULL` until the annotation batch job runs

### Additional tables (migrations 0004–0007)
- `searches` — per-user search history
- `retrievals` — chunk ↔ search linkage with score
- `bookmarks` — user-saved chunks
- `chunk_feedback` — thumbs up/down per chunk per user
- `user_preferences` — per-user UI/search preferences

### canon-law collection
- Added in migration 0007
- Backend allowlists updated in `constants.py` and all `rag/` modules

---

## 16. CSP Headers

- Defined in `apps/web/next.config.ts`
- **`script-src` and `default-src` are intentionally omitted** — nonce-based CSP is deferred; `unsafe-inline` is required for Next.js hydration in the interim, so these directives are excluded rather than creating a false sense of security
- **`connect-src` includes:** `'self'`, `NEXT_PUBLIC_API_URL`, `https://app.posthog.com`, `https://eu.posthog.com`
- **NEVER add `unsafe-eval` to `script-src`**

---

## 17. Known Issues & Deferred Work

### 1. Shared Rate Limit Counter

V1 chat and V2 search share `user_usage.rate_count` / `quota_count` columns. V2 enforces 5/min; V1 enforces 10/min. This creates cross-contamination. There is a `TODO` comment in `routes/search.py` → `check_search_rate_limit`.

**Future fix:** add `search_rate_count` / `search_quota_count` columns to `user_usage`.

### 2. Phase 3 Corpus Ingestion Deferred

The following datapipeline scripts are not yet built:
- `catechism.py`, `encyclicals.py`, `church_fathers.py`, `summa.py`, `embed.py`
