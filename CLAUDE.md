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
