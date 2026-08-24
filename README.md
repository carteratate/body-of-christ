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
  filtering and an adjustable per-source result quota.
- **Progressive, streamed results** — ranked passages appear first, then relevance
  explanations stream in passage-by-passage over SSE.
- **Document reader** — jump from any result into a chapter view of the full source.
- **Bookmarks** with personal notes, **search history**, and **thumbs-up/down feedback**.
- **Discover** — an AI scorer that rates how relevant each collection is to a query.
- **Guest trials** — a limited number of unauthenticated searches before sign-up.

---

## Architecture

TheoCorpus is a monorepo with three independently deployed pieces plus a local-only
data pipeline.

```
Browser
  │  (relative /v1/* requests — never calls Railway directly)
  ▼
Vercel  ─ apps/web ─ Next.js (App Router, TypeScript)
  │        └─ /v1/[...path] proxy route → injects x-internal-secret, forwards to API
  ▼
Railway ─ services/api ─ FastAPI (Docker)
  │        ├─ Supabase Postgres — RLS, full-text search (tsvector + GIN), Auth
  │        ├─ Qdrant           — vector store (cosine, HNSW)
  │        ├─ OpenAI           — embeddings (text-embedding-3-large)
  │        └─ Anthropic        — HyDE, reranking, explanations
```

Non-negotiable boundaries (see `CLAUDE.md` for the full list):

- **The frontend never talks to the database or Railway directly.** All data access
  goes through FastAPI, and the browser only ever hits the Vercel proxy at
  `apps/web/src/app/v1/[...path]/route.ts`. This avoids CORS, keeps the Railway URL
  private, and lets the server inject a shared `x-internal-secret`.
- **Embeddings live in Qdrant, not pgvector.** A `content_embedding` column exists on
  `chunks` but is vestigial and unused for retrieval.
- **Auth** is Supabase Auth. The frontend sends the JWT as `Authorization: Bearer`;
  the backend verifies signature, expiry, and issuer, and derives `user_id` from `sub`.
  RLS is enabled on all user-owned tables.

---

## The RAG pipeline

The full retrieval pipeline lives in `services/api/app/rag/`. For a single query:

1. **HyDE** — generate a hypothetical answer passage per collection.
2. **Embed** — concurrently embed the query + HyDE passages via OpenAI
   `text-embedding-3-large`.
3. **Retrieve** — per collection, run Qdrant cosine vector search and Supabase FTS in
   parallel, then merge with Reciprocal Rank Fusion (RRF, k=60).
4. **Rerank** — score candidates 0.0–1.0 with Claude Haiku per collection, then apply
   a global sort with a per-collection representation guarantee.
5. **Stream chunks** — emit ranked passages as `chunk` SSE events immediately.
6. **Persist** — write the search + retrievals to Postgres.
7. **Done** — emit a `done` SSE event with the `search_id`.
8. **Explain** — stream a per-passage relevance explanation via `explanation_delta`
   events.

No agent frameworks, no LangGraph. SSE event types: `chunk`, `explanation_delta`,
`done`, `error`, `status`.

---

## Repository layout

```
apps/web/            Next.js frontend (Vercel)
  src/app/           Routes: /search, /reader/[docId], /bookmarks, /sources,
                     /discover, /settings, /about, /login, /update-password
  src/app/v1/        [...path] proxy route → Railway
  src/components/    Feature-grouped UI (search/, reader/, bookmarks/, …)
  src/lib/           api.ts (all API + SSE), analytics.ts, collections.ts

services/api/        FastAPI backend (Railway, Docker)
  app/routes/        One module per endpoint group
  app/rag/           HyDE, embed, retrieve, rerank, explain, pipeline, constants
  app/auth/          Supabase JWT verification + JWKS cache
  tests/             pytest suite

supabase/migrations/ SQL migrations only (0001–0025). Additive, RLS everywhere.

datapipeline/        Standalone corpus publication tools (run locally/CI, not deployed)
  ingest/            Per-collection source adapters
  publication.py     Canonical collection-publication runner
  run_collection.py  Sole supported non-V5 publication CLI
  stages/            SQLite-cached ingest stages

docs/                Design notes and issue inventories
CLAUDE.md            Architectural invariants and project rules (authoritative)
PROGRESS.md          V2 implementation log
```

---

## Corpus & collections

Ten collections are live. The canonical list is
`services/api/app/rag/constants.py` (`VALID_COLLECTIONS`), mirrored on the frontend in
`apps/web/src/lib/collections.ts`. To add one, update `constants.py` first, then sync
`collections.ts`.

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
- Accounts / instances for: **Supabase** (Postgres + Auth), **Qdrant**,
  **OpenAI** (embeddings), **Anthropic** (LLM)

### 1. Backend (`services/api`)

```bash
cd services/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then fill in values (see below)
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

**Backend** (`services/api/.env`, see `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase pooler connection string |
| `SUPABASE_PROJECT_URL` | Supabase project URL (JWT issuer / JWKS) |
| `SUPABASE_JWT_AUDIENCE` | JWT audience (`authenticated`) |
| `ANTHROPIC_API_KEY` | Claude — HyDE, reranking, explanations |
| `OPENAI_API_KEY` | Embeddings (`text-embedding-3-large`) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Vector store |
| `INTERNAL_API_SECRET` | Shared secret; blocks direct API access (`openssl rand -hex 32`) |
| `CORS_ORIGINS` | Allowed frontend origins |
| `RATE_LIMIT_PER_MINUTE` / `DAILY_MESSAGE_QUOTA` | Rate limiting |

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
cd apps/web && npm run lint     # ESLint

# Backend
cd services/api && uvicorn app.main:app --reload   # dev server on :8000
cd services/api && pytest tests/                   # run tests

# Data pipeline
cd datapipeline && python run_collection.py --collection bible --target both
```

---

## Testing

The backend has an extensive pytest suite in `services/api/tests/` covering the RAG
steps (RRF, rerank, collection guarantee, anchor threading), route contracts,
persistence, dedup, and the evaluation harness.

```bash
cd services/api && pytest tests/
```

---

## Deployment

- **Backend** → Docker image on **Railway** (`railway.toml`, `services/api/Dockerfile`).
  The same image runs locally and in production. Required health endpoints:
  `GET /health`, `GET /health/db`.
- **Frontend** → **Vercel**. The proxy route forwards `/v1/*` to Railway using the
  server-side `API_URL`, injecting `x-internal-secret`.
- **Database** → Supabase; apply migrations from `supabase/migrations/` in order.
- All configuration is via environment variables — no config files with secrets.

---

## Data model

Postgres (Supabase) holds the corpus and user data; Qdrant holds the vectors.
Migrations are SQL-only and additive, with RLS on every user-owned table.

Core V2 tables: `documents`, `chunks` (with `search_vector` FTS + passage anchors),
`searches`, `retrievals`, `bookmarks`, `chunk_feedback`, `user_preferences`.
Legacy V1 chat tables (`chat_sessions`, `chat_messages`, `user_usage`) remain in place.

---

## Documentation

The codebase is documented in-repo. Start here:

| File | What it covers |
|---|---|
| `CLAUDE.md` | Authoritative architectural invariants, API routes, data model, and the Sacred Night design system |
| `PROGRESS.md` | Historical V2 implementation log and key engineering decisions |
| `datapipeline/README.md` | Supported collection publication, repair, reset, and wipe commands |
| `datapipeline/SOURCES.md` | Corpus source provenance and re-ingestion per collection |
| `docs/` | Design notes and codebase issue inventory |
