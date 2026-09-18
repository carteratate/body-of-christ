# TheoCorpus

**A Catholic theology retrieval-augmented search engine.** Ask a question in natural
language and get ranked, citation-anchored passages drawn from Scripture, the
Catechism, the Church Fathers, the Summa, conciliar documents, canon law, and the
papal magisterium — each result reranked and explained by an LLM, and linked back to
its place in the source text.

🔗 **Live:** [theo-corpus.com](https://theo-corpus.com)

> The repository is named `body-of-christ`; the user-facing product is **TheoCorpus**.

---

## Table of Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [The RAG pipeline](#the-rag-pipeline)
- [Repository layout](#repository-layout)
- [Corpus & collections](#corpus--collections)
- [Getting started](#getting-started)
- [Environment configuration](#environment-configuration)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Data model](#data-model)
- [Documentation](#documentation)

---

## What it does

TheoCorpus is a semantic search interface over a curated corpus of Catholic
theological texts. Unlike a chatbot, it does not synthesize answers — it **retrieves
and ranks primary-source passages**, then generates a short explanation of *why* each
passage is relevant to your query. Every result is anchored to a real location in the
source document and can be opened in a chapter-based reader.

Key capabilities:

- **Natural-language search** across 10 theological collections, with per-collection
  filtering and an adjustable per-source result quota (3, 4, 5, or 10).
- **Focused search** — quota 10 against a single collection, which widens the candidate
  budget and allows more passages per document instead of just returning more rows.
- **Progressive, streamed results** — ranked passages appear first, then relevance
  explanations stream in passage-by-passage over SSE.
- **Document reader** — jump from any result into a chapter view of the full source,
  with saved reading position.
- **Bookmarks** with personal notes, and **search history** you can restore or delete.
- **Discover** — an AI scorer that rates how relevant each collection is to a query.
- **Guest trials** — a limited number of unauthenticated searches, claimed into a real
  account on sign-up.
- **In-app feedback**, including anonymous.

---

## Architecture

TheoCorpus is a monorepo with three independently deployed pieces plus a local-only
data pipeline.

```
Browser
  │  (relative /v1/* requests — never calls the API host directly)
  ▼
Vercel  ─ apps/web ─ Next.js (App Router, TypeScript)
  │        └─ /v1/[...path] proxy route → injects x-internal-secret, forwards to API
  ▼
Railway ─ services/api ─ FastAPI (Docker)
  │        ├─ Supabase Postgres — RLS, full-text search (tsvector + GIN), Auth
  │        ├─ Qdrant           — vector store (cosine, HNSW)
  │        ├─ OpenAI           — embeddings + listwise rerank + explanations
  │        ├─ Anthropic        — HyDE, and the Haiku rerank path
  │        └─ Cohere           — first-stage per-collection rerank
```

The pipeline spans **three LLM providers** — do not assume Anthropic-only. Every model is
env-overridable; `services/api/app/config.py` is the source of truth.

Non-negotiable boundaries (see `CLAUDE.md` for the full list):

- **The frontend never talks to the database or the API host directly.** All data access
  goes through FastAPI, and the browser only ever hits the Vercel proxy at
  `apps/web/src/app/v1/[...path]/route.ts`. This avoids CORS, keeps the API host
  private, and lets the server inject a shared `x-internal-secret`.
- **Embeddings live in Qdrant, not pgvector.** `chunks.content_embedding` and
  `chunks.annotation_embedding` exist but are NULL in every row and unused for
  retrieval; their HNSW index was dropped in migration 0032. Leave the columns alone —
  all-NULL columns cost nothing and dropping them would reclaim nothing.
- **Auth** is Supabase Auth. The frontend sends the JWT as `Authorization: Bearer`;
  the backend verifies signature, expiry, and issuer, and derives `user_id` from `sub`.
  RLS is enabled on all user-owned tables.

---

## The RAG pipeline

The retrieval pipeline lives in `services/api/app/rag/`, split deliberately in two:

- **`rag/pipeline.py`** owns the SSE contract and database side-effects, nothing else.
- **`rag/pipelines/runner.py`** owns the compute; **`rag/pipelines/registry.py`** names
  the configurations. Individual steps live in `rag/steps/`.

Production runs the `hyde_cohere_luna` configuration (`_PRODUCTION_PIPELINE` in
`pipeline.py`). For a single query:

1. **Plan** — `rag/search_plan.py` resolves collections + quota into one validated
   `SearchPlan`, enforcing the focused-search invariant once.
2. **HyDE** — generate hypothetical answer passages (Claude Haiku). For the Bible, a
   genre-selection call picks which genres to generate.
3. **Embed** — concurrently embed the query + HyDE passages via OpenAI
   `text-embedding-3-large`.
4. **Retrieve** — per collection, run Qdrant cosine vector search and Supabase FTS in
   parallel, then merge with Reciprocal Rank Fusion (RRF, k=60).
5. **Rerank** — Cohere reranks per collection, then **one global listwise LLM call**
   (OpenAI `gpt-5.6-luna`) scores the surviving pool.
6. **Dedup → collection guarantee → quota cap**, with a last-resort `min_floor` if
   scoring excluded everything.
7. **Stream chunks** — emit ranked passages as `chunk` SSE events immediately.
8. **Persist** — write the search + retrievals to Postgres.
9. **Done** — emit a `done` SSE event with the `search_id`.
10. **Explain** — stream a per-passage relevance explanation (OpenAI `gpt-5.4-mini`)
    via `explanation_delta` events. These arrive *after* `done`, by design.

The registry also holds ablation configs (no-HyDE, Cohere-only, Haiku instead of Luna,
no-lexical). Switching production is a one-line change to `_PRODUCTION_PIPELINE`.

No agent frameworks, no LangGraph. SSE event types: `chunk`, `status`,
`explanation_delta`, `done`, `error`, and `results_ready` (guest only).

---

## Repository layout

```
apps/web/            Next.js frontend (Vercel)
  src/app/           Routes: /search, /history, /bookmarks, /sources, /discover,
                     /settings, /about, /feedback, /reader/[docId], auth flows,
                     and the guest mirrors (/search/guest, /reader/guest, /guest/*)
  src/app/v1/        [...path] proxy route → the API host
  src/components/    Feature-grouped UI (search/, reader/, bookmarks/, layout/, …)
  src/lib/           api.ts (HTTP), search-stream.ts (the only SSE decoder),
                     search-experience/ (search + restore lifecycle),
                     search-draft.ts, collections.ts, analytics.ts

services/api/        FastAPI backend (Railway, Docker)
  app/routes/        One module per endpoint group
  app/rag/           pipeline.py (SSE + persistence), pipelines/ (compute + registry),
                     steps/, search_plan.py, constants.py
  app/auth/          Supabase JWT verification + JWKS cache
  tests/             pytest suite

supabase/migrations/ SQL migrations only (0001–0035). Additive, RLS everywhere.

datapipeline/        Standalone corpus publication tools (run locally/CI, not deployed)
  ingest/            Per-collection source adapters
  publication.py     Canonical collection-publication runner
  run_collection.py  Sole supported non-V5 publication CLI
  scripts/           Narrow repair tools (dry-run by default)
  stages/            SQLite-cached V5 experiment, separate from the above

docs/                Design notes, specs, and the architecture review
CLAUDE.md            Architectural invariants and project rules (authoritative).
                     AGENTS.md is a symlink to it.
CONTEXT.md           Domain vocabulary — the words this project uses on purpose
PROGRESS.md          Historical V2 implementation log
```

---

## Corpus & collections

Ten collections are live. The canonical list is
`services/api/app/rag/constants.py` (`VALID_COLLECTIONS`), mirrored on the frontend in
`apps/web/src/lib/collections.ts`.

Adding one takes four coordinated changes: update `constants.py`, sync
`collections.ts`, add a `--color-collection-*` token in `globals.css`, and add a
migration extending the DB collection constraint.

| Key | Collection |
|---|---|
| `bible` | Bible (WEB-C / Douay-Rheims) |
| `catechism` | Catechism of the Catholic Church |
| `summa` | Summa Theologica |
| `encyclicals` | Papal Encyclicals |
| `councils` | Ecumenical Councils & Vatican II |
| `church-fathers` | Church Fathers (ANF / NPNF) |
| `medieval` | Medieval Theology |
| `canon-law` | 1983 Code of Canon Law |
| `apostolic-exhortations` | Apostolic Exhortations |
| `papal-documents` | Papal Documents |

Source provenance for each collection is documented in `datapipeline/SOURCES.md`.

---

## Getting started

### Prerequisites

- **Node.js ≥ 20** (frontend)
- **Python ≥ 3.11** (backend & data pipeline)
- Accounts / instances for: **Supabase** (Postgres + Auth), **Qdrant** (vectors),
  **OpenAI** (embeddings, listwise rerank, explanations), **Anthropic** (HyDE), and
  **Cohere** (first-stage rerank — optional, but the production pipeline uses it)

### 1. Backend (`services/api`)

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example .env      # the template lives at the repo root
uvicorn app.main:app --reload   # → http://localhost:8000
```

### 2. Frontend (`apps/web`)

```bash
cd apps/web
npm install
npm run dev                     # → http://localhost:3000
```

Set the server-side `API_URL` (e.g. `http://localhost:8000`) so the proxy route can
reach your local backend.

### 3. Health check

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

---

## Environment configuration

Config is entirely via environment variables. Copy the example files and fill them in;
never commit real secrets.

**Backend** (`services/api/.env`, templated by `.env.example` at the repo root). The
authoritative list — names, defaults, and which are required — is
`services/api/app/config.py`.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ | Supabase pooler connection string |
| `SUPABASE_PROJECT_URL` | ✅ | Supabase project URL (JWT issuer / JWKS) |
| `QDRANT_URL` / `QDRANT_API_KEY` | ✅ | Vector store |
| `OPENAI_API_KEY` | ✅ | Embeddings, listwise rerank, explanations |
| `ANTHROPIC_API_KEY` | ✅ | HyDE, Haiku rerank path, collection scoring, legacy chat |
| `COHERE_API_KEY` | — | First-stage rerank. Needed for the production pipeline config. |
| `ANTHROPIC_API_KEY_B/C/D` | — | Extra keys for per-key HyDE semaphoring; fall back to `ANTHROPIC_API_KEY` |
| `SUPABASE_JWT_AUDIENCE` | — | JWT audience (default `authenticated`) |
| `INTERNAL_API_SECRET` | — | Shared secret; blocks direct API access (`openssl rand -hex 32`) |
| `GUEST_IP_HASH_SECRET` | — | Keyed pseudonymization for guest IP quotas; falls back to `INTERNAL_API_SECRET` |
| `CORS_ORIGINS` | — | Allowed frontend origins |
| `RATE_LIMIT_PER_MINUTE` / `DAILY_MESSAGE_QUOTA` | — | Rate limiting |

**Frontend** (Vercel / `.env.local`):

| Variable | Purpose |
|---|---|
| `API_URL` | **Server-side only** — where the proxy forwards (Railway URL). No `NEXT_PUBLIC_` prefix. |
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Auth client |
| `NEXT_PUBLIC_API_URL` | Used **only** in `next.config.ts` for CSP `connect-src` — does not route API calls |

> ⚠️ `const API_URL = ""` in `apps/web/src/lib/api.ts` is intentional — the empty
> string forces relative `/v1/...` paths through the Vercel proxy. Do not change it.

**Supabase Auth URL configuration:**

Add the following URLs under **Authentication → URL Configuration → Redirect URLs**,
using both the production origin and `http://localhost:3000` for local development:

- `<origin>/auth/callback?next=/search` — email confirmation
- `<origin>/update-password` — password recovery

---

## Development

```bash
# Frontend
cd apps/web && npm run dev      # dev server on :3000
cd apps/web && npm run build    # production build
cd apps/web && npm run lint     # ESLint — baseline is ZERO errors
cd apps/web && npm test         # vitest run

# Backend
cd services/api && uvicorn app.main:app --reload   # dev server on :8000
cd services/api && python3 -m pytest tests/

# Data pipeline
cd datapipeline && python3 run_collection.py --collection bible --target both
```

---

## Testing

The backend has an extensive pytest suite in `services/api/tests/` covering the RAG
steps (RRF, rerank, collection guarantee, dedup, anchor threading), search-plan
validation, route contracts, persistence, and the evaluation harness.

The frontend runs vitest, with the heaviest coverage on the parts that are easy to get
subtly wrong: the SSE decoder (`search-stream.ts`), the search-experience runtime
(driven through `read`/`subscribe`/`send` with scripted in-memory adapters), and the
search draft reducer.

```bash
cd services/api && python3 -m pytest tests/
cd apps/web && npm test
```

The lint baseline is **zero errors**. Leave no new warnings in files you touch.

---

## Deployment

- **Backend** → Docker image on **Railway** (`railway.toml` at the repo root,
  `services/api/Dockerfile`). The same image runs locally and in production. Required
  health endpoints: `GET /health`, `GET /health/db`.
- **Frontend** → **Vercel**. The proxy route forwards `/v1/*` to the API host using the
  server-side `API_URL`, injecting `x-internal-secret`.
- **Database** → Supabase; apply migrations from `supabase/migrations/` in order.
- All configuration is via environment variables — no config files with secrets.

---

## Data model

Postgres (Supabase) holds the corpus and user data; Qdrant holds the vectors.
Migrations are SQL-only and additive, with RLS on every user-owned table.

**Corpus:** `documents`, `chunks` (with `search_vector` FTS, passage anchors, and
annotations).

**User activity:** `searches`, `retrievals`, `bookmarks`, `user_preferences`,
`reading_progress`, `product_feedback`, `guest_trials`.

**Retrieval lab:** `compare_runs`, `retrieval_labels`.

**Legacy V1 chat:** `chat_sessions`, `chat_messages`, `user_usage` — still in place.

**Drafted but not yet committed:** `studies`, `study_blocks` — see `CLAUDE.md` §4.

> ⚠️ `app/db.py` registers a jsonb codec, so asyncpg serialises jsonb parameters itself.
> **Never call `json.dumps` on a value bound to a jsonb column from the API** — that
> double-encodes it into a jsonb *string*, which reads back fine through the app but
> makes the column unqueryable from SQL. Migration 0033 repaired 205 such rows. The
> datapipeline pools register no codec, so `json.dumps` there is correct.

---

## Documentation

The codebase is documented in-repo. Start here:

| File | What it covers |
|---|---|
| `CLAUDE.md` | Authoritative architectural invariants, API routes, data model, and the two-theme design system. **`AGENTS.md` is a symlink to it** — one file, no drift. |
| `CONTEXT.md` | Domain vocabulary: the terms this project uses deliberately, and what to avoid |
| `datapipeline/README.md` | Supported collection publication, repair, reset, and wipe commands |
| `datapipeline/SOURCES.md` | Corpus source provenance and re-ingestion per collection |
| `docs/architecture/` | The August 2026 production architecture review (items 4–8 open) |
| `docs/agents/` | Issue tracker, triage labels, and domain-doc conventions for agents |
| `docs/superpowers/` | Historical plans and specs, one per feature |
| `PROGRESS.md` | Historical V2 implementation log. Banner-marked; not current guidance. |

Dated files under `docs/` are point-in-time records. Several carry a "superseded"
banner pointing at the doc that replaced them — trust the banner.
