# Project Rules & Invariants

> This file is the repo-wide source of agent guidance. The root `AGENTS.md` is a
> symlink to it — edit this file, never a copy. (They were separate files until
> 2026-09-17; the fork drifted 18 migrations out of date and is why they are one file now.)
>
> One scoped file exists below the root: **`apps/web/AGENTS.md`**, a real file covering
> frontend-only rules. It points back at the sections here rather than restating them —
> when a rule in §1, §9, §10–§14 or §18 changes, check whether it needs updating too.

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
- `chunks` (id, document_id, content, position, anchor, chapter_key, chapter_label, unit_label, reference, search_vector tsvector, annotation, annotation_vector tsvector, content_embedding vector, annotation_embedding)
- `searches`, `retrievals`, `bookmarks`, `user_preferences`
  (`chunk_feedback` was dropped and replaced by `retrieval_labels` in 0022)

### Later additions
- `compare_runs` — retrieval-lab evaluation runs (0018, 0020, 0026)
- `retrieval_labels` — human relevance labels (0022, 0024)
- `guest_trials` — guest session quota + continuity + transfer readiness (0023, 0025, 0026, 0027)
- `guest_trial_retrievals` — guest results, held apart from `retrievals` until
  `POST /v1/guest/claim` transfers them (0026_guest_onboarding_continuity). Read by
  `routes/guest_search.py` and the guest reader path in `routes/documents.py`.
- `reading_progress` — per-document reader position (0027)
- `product_feedback` — in-app feedback, including anonymous (0028–0030)
- `user_preferences.last_standard_quota` — remembers the pre-focused quota (0034); see §18
- `studies`, `study_blocks` — **drafted, not yet in the repo.** A `0035_studies.sql`
  migration and a `test_study_schema.py` exist on at least one working tree but are
  committed to no branch, so `git log` will not find them and a fresh clone will not have
  them. `CONTEXT.md` already carries the vocabulary (Study, Study block, My Passages,
  Published version). The design point: a Study block is either authored writing or a
  Passage occurrence carrying a private source snapshot, so corpus pruning can remove the
  live chunk without erasing authored work. Update this entry when the migration lands.

Migrations 0001–0034 are committed; `0035_studies.sql` is drafted only (see above). **Two identity collisions exist — `0026_compare_runs_pricing` / `0026_guest_onboarding_continuity`, and `0027_reading_progress` / `0027_guest_transfer_readiness`.** All four hold live schema, and the two members of each pair touch disjoint tables, so order within a pair does not matter. Audit the Supabase migration ledger before renaming any of them.

`chunks.content_embedding` and `chunks.annotation_embedding` exist but are **unused** —
NULL in every row, and no pgvector operator (`<=>`, `<->`, `<#>`) appears anywhere in the
repo. Qdrant owns all vector search, including the V5 `facets` and `questions` collections.
The 237 MB HNSW index over `content_embedding` was dropped in 0033's sibling, 0032. Leave
the columns themselves alone: all-NULL columns cost zero bytes, and `DROP COLUMN` does not
rewrite the table, so removing them would reclaim nothing.

**`app/db.py` registers a jsonb codec (`encoder=json.dumps`), so asyncpg serialises jsonb
parameters itself. Never call `json.dumps` on a value bound to a jsonb column from the API** —
that double-encodes it into a jsonb *string*, which reads back fine through the app but makes
the column unqueryable from SQL. 0033 repaired 205 such rows. The datapipeline pools register
no codec, so `json.dumps` there is correct.

---

## 5. RAG Pipeline

Two layers, and the split is the point:

- `rag/pipeline.py` owns the **SSE contract and DB side-effects only**.
- `rag/pipelines/runner.py` owns the **compute**; `rag/pipelines/registry.py` names the configurations.

Production runs the `hyde_cohere_luna` config (`_PRODUCTION_PIPELINE` in `pipeline.py`): HyDE → embed → parallel Qdrant vector + Supabase FTS retrieval → RRF merge → **Cohere rerank per collection → one global listwise LLM call** → dedup → collection guarantee → quota cap → `min_floor` (only if everything else emptied). Steps live in `rag/steps/`.

**`rag/search_plan.py` resolves one validated `SearchPlan` before the pipeline runs.** It
is the single place that normalizes collections and enforces the focused-search invariant,
and it hands the runner three derived values: `focused`, `terminal_candidate_budget`, and
`max_passages_per_document`. `SearchPlanError` carries a stable `code` so routes translate
failures consistently. See §18.

The registry also holds ablation configs (no-HyDE, Cohere-only, Haiku instead of Luna, no-lexical). Changing which pipeline is production is a one-line change to `_PRODUCTION_PIPELINE`; changing a *step* affects every config that uses it.

**The pipeline spans three LLM providers** — do not assume Anthropic-only. Defaults in `config.py`: HyDE `claude-haiku-4-5`, LLM rerank `claude-haiku-4-5` (`hyde_*_haiku`) or `gpt-5.6-luna` (`*_luna`), the Cohere rerank path, embeddings OpenAI `text-embedding-3-large`, explanations OpenAI `gpt-5.4-mini`. Legacy chat uses `claude-sonnet-4-6`. Every one is env-overridable; read `config.py` before naming a model.

Streaming order: `chunk` events fire as soon as ranking completes, then the search and its retrievals persist, then `done`, then explanations stream per chunk via `explanation_delta`. Explanations arriving after `done` is normal and the frontend depends on it.

No LangGraph or agent frameworks. No pgvector for retrieval.

---

## 6. Deployment

- Backend: Docker image; same image runs locally and in prod.
- Frontend: Vercel.
- Config via environment variables only.
- Health endpoints: GET /health, GET /health/db, and GET /health/search, which reports
  retrieval-provider readiness and returns 503 when a dependency is missing. Model-provider
  credentials are configuration-checked only — validating them costs a billable request.

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
| `/icon-preview`, `/onboarding-preview`, `/prototypes/quota-ten-proof` | Design drafts, not product surface |
| `/v1/[...path]` | The proxy route — see §1 |

### API (all under `/v1/`)

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | Current user |
| POST | `/search` | SSE stream; 5/min, 30/day. Quota 10 is focused — see §18. |
| POST | `/search/guest` | SSE stream; guest session token, trial-limited |
| POST | `/guest/claim` | Transfer guest work into a new account |
| GET | `/searches`, `/searches/{id}/results` | History; restore a past search |
| DELETE | `/searches/{id}` | Retrievals cascade |
| GET | `/documents/{id}`, `/{id}/toc`, `/{id}/reader` | Reader: metadata, chapter list, one chapter |
| GET/PUT | `/reading-progress`, `/reading-progress/{doc_id}` | Reader position |
| GET | `/sources` | All documents with chunk counts; 1h in-memory cache |
| POST | `/evaluate`, `/evaluate/explain` | Collection scoring; 10/day |
| POST/GET/PATCH/DELETE | `/bookmarks`, `/bookmarks/{id}` | PATCH body is `{note}` |
| POST | `/product-feedback` | In-app feedback; allows anonymous |
| POST | `/labels` | Human relevance labels (retrieval lab) |
| GET/PUT | `/preferences` | User preferences |
| POST/GET | `/search/compare`, `/search/compare/view`, `/search/compare/stats` | **Retrieval lab.** Mounted in production startup today; treat as a separate concern from product routes. |
| POST | `/chat`, `/chat/stream` | Legacy — see §3 |
| GET | `/sessions`, `/sessions/{id}/messages` | Legacy chat history. Mounted in production; no live caller. |

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

- `SearchPage.tsx` renders snapshots and forwards commands. Keep AbortControllers, run generations, stream buffers, terminal flags, and animation timers out of it. Draft query/collection/translation/quota controls, route translation, result filtering, hints, and DOM measurement stay in the page — except the draft *transition rules*, which live in `lib/search-draft.ts` (§18).
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
  - `onDone(searchId, resultCount, outcome, collectionOutcomes, persisted, deliveryOutcome?)` — `persisted: false` means results are usable but not saved to history. `deliveryOutcome` is focused-search only (§18) and absent otherwise.
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

V1 chat and V2 search share `user_usage.rate_count` / `quota_count`. V2 enforces 5/min and 30/day (`RATE_LIMIT_SEARCH_PER_MINUTE` / `DAILY_SEARCH_QUOTA`); V1 enforces 10/min (`RATE_LIMIT_PER_MINUTE` / `DAILY_MESSAGE_QUOTA`). The two pairs are separate settings over one counter, so they cross-contaminate. `TODO` in `routes/search.py` → `check_search_rate_limit`.
**Fix:** add `search_rate_count` / `search_quota_count` columns.

### 2. JWKS refresh still stampedes

`app/auth/jwks.py` has an `asyncio.Lock`, but it guards only the **cache write** — `_fetch_from_remote()` runs outside it. Concurrent coroutines that all see a stale cache still all issue HTTP requests to Supabase. Low priority; the fix is to hold the lock across the fetch with a double-check on entry.

### 3. Retrieval lab is mounted in production startup

`compare`, `compare_stats`, and the judge client initialize with the product API. Separating them into an adapter or explicit deployment mode is tracked as architecture item 7.

### 4. Tracked relics

`app/icon-preview/` (~1,177 lines of animation draft), `components/chat/ChatShell.tsx`,
and `rag/steps/persist.py` (a one-line placeholder docstring, imported nowhere) are dead.
Architecture item 8.

**`rag/steps/dedup.py` is NOT dead — do not delete it.** `pipelines/runner.py` imports it
in the parenthesized `from app.rag.steps import (...)` block, which is easy to miss with a
single-line grep. It is the step that carries `per_source_cap` / `per_document_cap`, so
focused search (§18) depends on it.

Lint warnings are 4 total, 0 errors: 2 in `icon-preview/`, 2 in
`components/common/ErrorBoundary.tsx`.

---

## 18. Focused search (quota 10)

Quota is one of `3, 4, 5, 10`. **Quota 10 is "focused": it requires exactly one
collection**, and it changes retrieval shape rather than just raising the result count.

**The invariant is enforced in one place** — `resolve_search_plan()` in
`rag/search_plan.py`. Do not re-derive "is this focused?" from a raw quota int anywhere
else; take `SearchPlan.focused`. `SearchPlanError.code` is stable and routes translate it:
`no_valid_collections` → 400, everything else (`invalid_quota`, `duplicate_collections`,
`invalid_collections`, `focused_collection_count`) → 422.

What focused changes, all derived from the plan:

| | Standard | Focused |
|---|---|---|
| Collections | 1–10 | exactly 1 |
| `terminal_candidate_budget` | `settings.llm_pool_global_cap` | 25 |
| `max_passages_per_document` | 2 | 4 | *(per **chapter** for chapter-keyed collections — see below)* |
| Bible HyDE | genre-selected subset | all genres, fused as one retrieval family (`hyde_s25.run(..., all_bible_genres=True)`) |

`max_passages_per_document` is passed as **both** `per_source_cap` and `per_document_cap`
to `steps/dedup.py`, and again to `min_floor`.

**The name is now wider than what it limits.** For the chapter-keyed collections in
`rag/dedup.py` (`summa`, `catechism`, `canon-law`, `bible`) both caps key on the reader
chapter, not the document. Those four are each stored as a single document — the Bible as
one per book — so keying on the document capped a focused search at 4 results in total
however many distinct articles or psalms ranked, which made issue #28's "return exactly
ten" unreachable for exactly the collections focused search is most used on. Issue #105 is
that defect reported from production.

**`per_document_cap` is inert at the values production passes.** `document_key` strictly
refines `source_key`, so the document count can never reach a ceiling the source count has
not already reached; the cap can only bind when it is strictly smaller than
`per_source_cap`, and `runner.py` passes them equal. Standard search passes
`per_document_cap=None` and never consults it. Do not write code that assumes it fires.
`FOCUSED_MAX_PASSAGES_PER_DOCUMENT` / `STANDARD_MAX_PASSAGES_PER_DOCUMENT` in
`search_plan.py` are misnamed for the same reason.

### delivery_outcome

Focused searches report how well the quota was filled: `complete` | `underfilled` |
`minimum_floor` (`_delivery_outcome()` in `pipelines/runner.py`). It reaches the client as
the optional 6th argument to `onDone` (§14), and it is persisted into the `searches.filters`
jsonb **only when quota is 10** (`pipeline.py`), so a restored focused search can explain
its own delivery. Standard searches never set it; treat `undefined` as "not applicable",
not as a failure.

### Preferences

`user_preferences` carries both `default_quota` and `last_standard_quota` (0034).
`last_standard_quota` remembers where to return when the person leaves focused mode, so
toggling 10 → back does not strand them on an arbitrary default. DB constraints mirror the
API invariant: `default_quota IN (3,4,5,10)`, `last_standard_quota IN (3,4,5)`, and
`default_quota <> 10 OR exactly one default_collection`. Keep all three in step when
changing quota rules.

### Frontend

**`lib/search-draft.ts` owns draft quota/collection state and focused eligibility** —
`SearchQuota`, `StandardQuota`, `focusedEligible`, and the draft reducer. This is the one
exception to §12's "draft controls stay in the page": the page renders it, but the
transition rules live here and are unit-tested directly. `QuotaControl.tsx` and
`BottomBar.tsx` render it. `LoadingAnimation` takes `quota` as a prop and scales its
winner count to it, so ten works without a special case.

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
