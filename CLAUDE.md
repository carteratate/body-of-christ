# CLAUDE.md — Project Rules & Invariants

This repository (body-of-christ) implements a Catholic theology RAG search application.
The user-facing product name is **TheoCorpus**.
All changes MUST respect the following architectural, security, and design constraints.

---

## 0. Quick Commands

```bash
# Frontend (apps/web)
npm run dev            # dev server on :3000
npm run build          # production build
npm run lint           # ESLint — the repo baseline is ZERO errors
npm test               # vitest run

# Backend (services/api) — deps in pyproject.toml; `python3` on this machine
uvicorn app.main:app --reload   # dev server on :8000
python3 -m pytest tests/

# Datapipeline (one collection; use --target reader/search for a repair)
cd datapipeline && python3 run_collection.py --collection bible --target both

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
  - `services/api`        → Python FastAPI, Docker
  - `supabase/migrations` → SQL migrations only
  - `datapipeline/`       → standalone Python scripts (run locally/CI, not deployed)

- **Supabase** — Postgres (RLS, FTS via `search_vector` GIN index) + Auth
- **Qdrant** — vector store for cosine-similarity search (HNSW). Embeddings live here, NOT in pgvector.
- The frontend NEVER talks directly to the database.
- ALL client data access goes through FastAPI.
- **The frontend NEVER calls the API host directly from the browser.** All API calls go through the Vercel proxy at `apps/web/src/app/v1/[...path]/route.ts`, which forwards using the server-side `API_URL` env var. This is intentional — it avoids CORS, keeps the API host private, and allows `x-internal-secret` to be added server-side.
- **`const API_URL = ""` in `apps/web/src/lib/api.ts` is correct and intentional.** The empty string causes all fetch calls to use relative paths (`/v1/...`), which hit the Vercel proxy. Keep it empty. The env var that matters is server-side `API_URL` (no `NEXT_PUBLIC_` prefix), used only by the proxy route.
- **`NEXT_PUBLIC_API_URL` is used only in `next.config.ts` for CSP headers.** It does NOT control where API calls are routed. Keep it out of `api.ts`.

---

## 2. Authentication & Authorization (CRITICAL)

- Auth via Supabase Auth; frontend sends JWT as `Authorization: Bearer <token>`.
- Backend verifies the Supabase JWT (signature, expiration, issuer) and extracts `user_id` from `sub`. Implementation is the `app/auth/` package — `jwks.py` (key cache) and `verify.py`.
- RLS MUST be enabled on all user-owned tables.
- Supabase service role key MUST NEVER appear in frontend code.
- **Guests** are a separate audience with no Supabase user: a guest session token grants a limited search trial, and guest work is claimed into a real account on signup (`POST /v1/guest/claim`). Guest state lives in `guest_trials` and the guest continuity/transfer columns; it is never a JWT identity.

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

This contract MUST NOT change across versions. Note it is a **compatibility endpoint with no live caller** — `/chat` redirects to `/search`, and the browser client (`components/chat/ChatShell.tsx`, `streamMessage` in `api.ts`) is unreachable. Keep the endpoint; treat the frontend half as a deletion candidate.

---

## 4. Data Model

SQL migrations ONLY. Schema changes must be additive. RLS on all user-owned tables.

### Core (V1)
- `chat_sessions`, `chat_messages`, `user_usage`

### Search corpus & activity (V2)
- `documents` (id, collection, title, author, year, translation, metadata jsonb)
- `chunks` (id, document_id, content, position, anchor, chapter_key, chapter_label, unit_label, reference, search_vector tsvector, content_embedding vector, annotation, annotation_embedding)
- `searches`, `retrievals`, `bookmarks`, `chunk_feedback`, `user_preferences`

### Later additions
- `compare_runs` — retrieval-lab evaluation runs (0018, 0020, 0026)
- `retrieval_labels` — human relevance labels (0022, 0024)
- `guest_trials` — guest session quota + continuity + transfer readiness (0023, 0025, 0026, 0027)
- `reading_progress` — per-document reader position (0027)
- `product_feedback` — in-app feedback, including anonymous (0028–0030)

Migrations run 0001–0030. **Two identity collisions exist — `0026_compare_runs_pricing` / `0026_guest_onboarding_continuity`, and `0027_reading_progress` / `0027_guest_transfer_readiness`.** All four hold live schema. Audit the Supabase migration ledger before renaming any of them.

`chunks.content_embedding` exists but is **unused** — zero references in `services/api/app/`. Qdrant owns all vector search. Leave the column alone.

---

## 5. RAG Pipeline

Two layers, and the split is the point:

- `rag/pipeline.py` owns the **SSE contract and DB side-effects only**.
- `rag/pipelines/runner.py` owns the **compute**; `rag/pipelines/registry.py` names the configurations.

Production runs the `hyde_cohere_luna` config (`_PRODUCTION_PIPELINE` in `pipeline.py`): HyDE → embed → parallel Qdrant vector + Supabase FTS retrieval → RRF merge → **Cohere rerank per collection → one global listwise LLM call** → dedup → collection guarantee → quota cap. Steps live in `rag/steps/`.

The registry also holds ablation configs (no-HyDE, Cohere-only, Haiku instead of Luna, no-lexical). Changing which pipeline is production is a one-line change to `_PRODUCTION_PIPELINE`; changing a *step* affects every config that uses it.

**The pipeline spans three LLM providers** — do not assume Anthropic-only. Defaults in `config.py`: HyDE `claude-haiku-4-5`, LLM rerank `claude-haiku-4-5` (`hyde_*_haiku`) or `gpt-5.6-luna` (`*_luna`), the Cohere rerank path, embeddings OpenAI `text-embedding-3-large`, explanations OpenAI `gpt-5.4-mini`. Legacy chat uses `claude-sonnet-4-6`. Every one is env-overridable; read `config.py` before naming a model.

Streaming order: `chunk` events fire as soon as ranking completes, then the search and its retrievals persist, then `done`, then explanations stream per chunk via `explanation_delta`. Explanations arriving after `done` is normal and the frontend depends on it.

No LangGraph or agent frameworks. No pgvector for retrieval.

---

## 6. Deployment

- Backend: Docker image; same image runs locally and in prod.
- Frontend: Vercel.
- Config via environment variables only.
- Required health endpoints: GET /health, GET /health/db

---

## 7. Coding Standards

- Backend: FastAPI + Pydantic, structured logging, no secrets logged.
- Frontend: TypeScript, HTTP calls centralized in `src/lib/api.ts`, no DB SDK in frontend.
- Lint baseline is zero errors. Leave no new warnings in files you touch.

---

## 8. Non-Goals

- No direct DB queries from frontend
- No serverless backend (Lambda, Supabase Edge Functions)
- No Kubernetes, no agent frameworks, no premature microservices

---

## 9. Design System

Tokens are defined in `apps/web/src/app/globals.css` under `@theme`. Use the Tailwind `brand` namespace (`bg-brand-surface`, `text-brand-muted`, …) and `var(--color-collection-*)` for collection accents. **No hardcoded hex in components.**

Two themes, selected by `data-theme` on `<html>` and persisted in `user_preferences.theme`:

| Token | Slate Night (dark, default) | Ivory Vault (light) |
|---|---|---|
| `brand-bg` | `#0D1828` | `#f0e8d8` |
| `brand-surface` | `#172232` | `#e3dbc8` |
| `brand-accent` | `#C4972A` | `#C4972A` |
| `brand-primary` | `#EAE6DC` | `#1a1610` |
| `brand-muted` | `#7A8099` | `#6a6050` |

Any new color must be added to **both** theme blocks.

---

## 10. Routes

### Frontend

Authenticated pages live at the bare path; the guest mirror is a sibling under `/guest/` or `/search/guest`. Both must be updated together when shared behavior changes.

| Route | Notes |
|---|---|
| `/` | Redirects to /search when authed; otherwise renders `LandingPage` |
| `/search`, `/search/guest` | Main search interface — both render `SearchPage` |
| `/reader/[docId]`, `/reader/guest/[docId]` | Document reader (chapter-based) |
| `/history` | Search history |
| `/bookmarks` | Saved passages |
| `/sources` | Corpus document browser |
| `/discover` | AI collection scorer (evaluate endpoint) |
| `/settings` | User preferences |
| `/about`, `/guest/about` | Product info |
| `/feedback`, `/guest/feedback` | Product feedback form |
| `/login`, `/signup`, `/update-password`, `/auth/callback` | Auth flows |
| `/chat` | `redirect` to /search — legacy |
| `/icon-preview`, `/onboarding-preview` | Design drafts, not product surface |
| `/v1/[...path]` | The proxy route — see §1 |

### API (all under `/v1/`)

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | Current user |
| POST | `/search` | SSE stream; 5/min, 30/day |
| POST | `/search/guest` | SSE stream; guest session token, trial-limited |
| POST | `/guest/claim` | Transfer guest work into a new account |
| GET | `/searches`, `/searches/{id}/results` | History; restore a past search |
| DELETE | `/searches/{id}` | Retrievals cascade |
| GET | `/documents/{id}`, `/{id}/toc`, `/{id}/reader` | Reader: metadata, chapter list, one chapter |
| GET/PUT | `/reading-progress`, `/reading-progress/{doc_id}` | Reader position |
| GET | `/sources` | All documents with chunk counts; 1h in-memory cache |
| POST | `/evaluate`, `/evaluate/explain` | Collection scoring; 10/day |
| POST/GET/PATCH/DELETE | `/bookmarks`, `/bookmarks/{id}` | PATCH body is `{note}` |
| POST | `/feedback` | `{chunk_id, feedback: "up"\|"down", search_id?}` |
| POST | `/product-feedback` | In-app feedback; allows anonymous |
| POST | `/labels` | Human relevance labels (retrieval lab) |
| GET/PUT | `/preferences` | User preferences |
| POST/GET | `/search/compare`, `/search/compare/view`, `/search/compare/stats` | **Retrieval lab.** Mounted in production startup today; treat as a separate concern from product routes. |
| POST | `/chat`, `/chat/stream` | Legacy — see §3 |

---

## 11. Frontend Layout

Components are grouped by feature under `apps/web/src/components/<feature>/` (search, reader, history, bookmarks, sources, discover, settings, feedback, landing, auth, chat, common, layout). Read the directory rather than a list here.

What is **not** discoverable by looking:

- **Search lifecycle does not live in `components/search/`.** It lives in `apps/web/src/lib/search-experience/` — see §12.
- **`lib/search-stream.ts` is the sole SSE protocol module** — see §14.
- `components/layout/` holds three shells: `AppShell` (authenticated), `GuestShell` (guest), and `AuthenticatedRouteShell`, which picks between them by pathname against its own `AUTHENTICATED_ROUTES` list — **add new authenticated routes there or they render in the guest shell.** Guest and authenticated pages share components by receiving an `isGuest` prop, not by forking.
- `components/chat/ChatShell.tsx` is unreachable — see §3.

---

## 12. Search-experience runtime (`lib/search-experience/`)

**The search and restore lifecycle has one owner.** `createSearchExperience()` in `runtime.ts` exposes exactly three operations:

```ts
read:      () => SearchExperienceSnapshot   // immutable current state
subscribe: (listener) => unsubscribe
send:      (command: SearchExperienceCommand) => void
```

It owns run identity, `AbortController` lifecycle, stale-event rejection, frozen submitted requests, passage/explanation buffering, terminal rules, retry, rate limits, guest continuity, pending-history ownership, and animation milestones.

Everything it touches externally is an injected port: `audience` (a discriminated authenticated/guest search adapter), plus `credentials`/`savedSearch` for authenticated and `guestAccess`/`guestContinuity` for guest, and `pendingHistory`, `analytics`, `time`. Wiring lives in `useSearchPageExperience.ts`; React subscription is `useSearchExperience.ts` (`useSyncExternalStore`, no transitions).

Rules when working here:

- `SearchPage.tsx` renders snapshots and forwards commands. Keep AbortControllers, run generations, stream buffers, terminal flags, and animation timers out of it. Draft query/collection/translation/quota controls, route translation, result filtering, hints, and DOM measurement stay in the page.
- Next routing and React stay outside the runtime.
- Test through `read`/`subscribe`/`send` with scripted in-memory adapters. Do not assert on private reducer state.
- `LoadingAnimation` owns visual timing and emits semantic milestones (`filters-ready` at 3.2s, ready-to-reveal, fade-complete). Passages stay buffered until ready-to-reveal. Do not reintroduce a page-side timer.

---

## 13. AppContext

- Provided by `AppShell`; consumed via `useAppContext()`.
- **ALL authenticated pages MUST be wrapped in AppShell.** `GuestShell` supplies the guest equivalent.
- Holds: auth (`token`, `userId`, `ready`), preferences, search history (`searches`, `refreshSearches`, `removeSearch`, `restoreSearch`, `historyRevision`, `invalidateSearchHistory`), the pending-search slot, `activeSearchId`/`searchKey`/`newSearch`, the cached source corpus, `bookmarkIds`, and mobile navigation state.

**`clearPendingSearch(expectedId?: string)` is generation-guarded** — it no-ops when `expectedId` does not match the current pending entry, so a stale aborted run cannot clear its replacement's row. Always pass the owning entry id.

Auto-save on toggle/quota/translation change is debounced `PUT /v1/preferences` in `SearchPage.tsx` and `CollectionToggles.tsx` — NOT in AppShell.

---

## 14. SSE Streaming

- **`lib/search-stream.ts` is the only SSE decoder.** `consumeSearchStream(body, callbacks, signal)` owns buffering, event decoding, terminal rules, and abort. `streamSearch` (authenticated) and `streamGuestSearch` (guest) are request adapters over it and differ only in endpoint and credential.
- Add a new event field **once**, in `search-stream.ts`.
- **Backend event types:** `chunk`, `status`, `explanation_delta`, `done`, `error`, and `results_ready` (guest only — ranked passages are ready; guest `done` is a later completion/transfer milestone).
- **Callbacks:** `onChunk`, `onExplanationDelta`, `onStatus?`, `onResultsReady?`, `onRateLimit(retryAfter, "per_minute" | "daily")`, plus:
  - `onDone(searchId, resultCount, outcome, collectionOutcomes, persisted)` — `persisted: false` means results are usable but not saved to history.
  - `onError(message, code?, stage?, collectionOutcomes?)`
- `outcome` is `success | degraded_success | no_candidates`. **Only an explicit `no_candidates` means an empty corpus result** — an error is not a no-results screen.
- Cleanup: pass an `AbortController.signal` and abort on unmount.

---

## 15. Collections — Canonical Source

- **Single source of truth:** `services/api/app/rag/constants.py` (`VALID_COLLECTIONS`), 10 collections.
- **Frontend mirror:** `apps/web/src/lib/collections.ts` (label + CSS var per collection).
- **To add one:** update `constants.py`, sync `collections.ts`, add a `--color-collection-*` token in `globals.css`, and add a migration extending the DB collection constraint.

---

## 16. CSP Headers

- Defined in `apps/web/next.config.ts`.
- **`script-src` and `default-src` are intentionally omitted** — nonce-based CSP is deferred, and `unsafe-inline` is required for Next.js hydration in the interim, so these directives are excluded rather than creating a false sense of security.
- **`connect-src` includes:** `'self'`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `https://app.posthog.com`, `https://eu.posthog.com`
- **NEVER add `unsafe-eval` to `script-src`.**

---

## 17. Known Issues & Deferred Work

### 1. Shared rate-limit counter (V1 chat / V2 search)

V1 chat and V2 search share `user_usage.rate_count` / `quota_count`. V2 enforces 5/min and 30/day; V1 enforces 10/min. This cross-contaminates. `TODO` in `routes/search.py` → `check_search_rate_limit`.
**Fix:** add `search_rate_count` / `search_quota_count` columns.

### 2. JWKS refresh still stampedes

`app/auth/jwks.py` has an `asyncio.Lock`, but it guards only the **cache write** — `_fetch_from_remote()` runs outside it. Concurrent coroutines that all see a stale cache still all issue HTTP requests to Supabase. Low priority; the fix is to hold the lock across the fetch with a double-check on entry.

### 3. Retrieval lab is mounted in production startup

`compare`, `compare_stats`, and the judge client initialize with the product API. Separating them into an adapter or explicit deployment mode is tracked as architecture item 7.

### 4. Tracked relics

`app/icon-preview/` (~1,177 lines of animation draft, source of the remaining lint warnings), `components/chat/ChatShell.tsx`, `rag/steps/persist.py` (empty), and `rag/steps/dedup.py` (pass-through) are all dead. Architecture item 8.

---

## Agent skills

### Issue tracker

Issues and specifications are tracked in GitHub Issues for `carteratate/body-of-christ`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default Matt Pocock triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context documentation layout. See `docs/agents/domain.md`.

### Architecture review

The August 2026 production architecture review is `docs/architecture/architecture-review-2026-08-23.html`. Items 1–3 are implemented; items 4–8 are open and are referenced by number above.
