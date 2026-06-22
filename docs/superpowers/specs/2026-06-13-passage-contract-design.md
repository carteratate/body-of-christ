# Shared Contract — Canonical Passages, Identity, Anchors & API

**Date:** 2026-06-13
**Status:** Approved (design)
**Binds:** [Reader Rework](2026-06-13-reader-rework-design.md) · [Dual Datapipeline](2026-06-13-dual-datapipeline-design.md)

This document defines the **interface** shared by the reader and the two ingestion pipelines. It is
deliberately small and authoritative: once it is fixed, the reader and the pipelines can be built in
parallel against it. The two specs above reference this contract rather than redefining it.

---

## 1. Why a contract

Today the reader renders the same overlapping, breadcrumb-prefixed, char-split "search chunks" used for
retrieval, and the Sources list invents synthetic IDs (`{doc_id}:{author}:{work}`) that cannot open a
reader at all. The rework unifies reading and retrieval onto **one clean passage object** with **one stable
identity**, stored in two places (Supabase for reading + keyword search, Qdrant for vector search). Three
things must be agreed before anything else: **document identity**, the **passage model + anchor**, and the
**API shapes**.

---

## 2. Document identity

- Every readable work is **one document** with a **deterministic UUIDv5** derived from a stable work-key.
  Re-running a pipeline, or running the two pipelines independently, MUST produce the **same** `document_id`.
- Namespace: a fixed project UUID constant (`DOCUMENT_NS`) defined once in the pipeline and never changed.
- `document_id = uuid5(DOCUMENT_NS, work_key)` where `work_key` is the lowercased, normalized join of:

  | Collection | work_key components |
  |---|---|
  | bible | `("bible", translation, book)` — one document per book per translation |
  | catechism | `("catechism",)` — single document |
  | summa | `("summa",)` — single document |
  | church-fathers | `("church-fathers", author, work)` — one document per (father, work) |
  | encyclicals | `("encyclicals", slug)` — one per encyclical |
  | canon-law | `("canon-law",)` — single document |
  | councils | `("councils", council, document)` — one per council document |
  | medieval | `("medieval", author, work)` — one per work |

- Consequences:
  - Sources rows, Read More targets, and the reader all resolve to the **same** `document_id`. The
    `_get_church_fathers` synthetic-ID logic in `services/api/app/routes/sources.py` is **deleted**.
  - The Bible appears in Sources as a translation that expands to **book-level documents** (each book is a
    real document the reader can open).

---

## 3. Canonical passage model

A **passage** is the single unit shared by the reader and search. It is **clean, contiguous, and
non-overlapping**. The reader displays passages in order; search embeds them. Same row, same id, both stores.

### 3.1 Supabase schema (additive migration to `chunks`)

Per CLAUDE.md §4, schema changes are additive and SQL-migration-only. The existing `chunks` table is
**evolved**, not replaced:

| Column | State | Meaning |
|---|---|---|
| `id` | existing | passage UUID — **also** the Qdrant point id |
| `document_id` | existing | FK → `documents.id` (deterministic, §2) |
| `position` | existing | global 0-based order of the passage within the document |
| `content` | existing, **semantics change** | **clean** reading text — no `[breadcrumb]` headers, no `(1/3)` suffixes, normalized per the cleaning layer |
| `reference` | existing, **semantics change** | clean human citation (see per-collection rules in the pipeline spec) |
| `search_vector` | existing | Postgres FTS — **retained** (keyword search runs here) |
| `content_embedding` (pgvector) | existing, **retired** | the Supabase vector column is **no longer populated**. The embedding lives only as the Qdrant point vector; a reader/FTS row links to it by shared id (`chunks.id == point.id`), so Supabase needs no vector. Physically `DROP COLUMN` is non-additive (CLAUDE.md §4); left dormant/NULL unless that rule is relaxed (see §8) |
| `anchor` | **new** `text` | stable deep-link key, unique per `document_id` (§3.3) |
| `chapter_key` | **new** `text` | groups passages into a reader "chapter section" |
| `chapter_label` | **new** `text` | display heading for that section (e.g. `Chapter 3`, `Question 68, Article 3`) |
| `unit_label` | **new** `text NULL` | inline ordinal shown to the reader (e.g. verse `16`, `Reply to Objection 2`); null when not applicable |

- New index: `UNIQUE (document_id, anchor)` and `INDEX (document_id, chapter_key, position)`.
- Upsert key stays `(document_id, position)` (idempotent re-ingest).

### 3.2 Chapter sections

- `chapter_key` partitions a document's passages into the **reader's section unit** (one chapter = one
  section, per the reader spec). Examples: Bible `John/3`; Summa `I-II/Q68/A3`; CF `1-clement/ch-49`;
  CCC chapter/article node. Passages within a section render contiguously.
- `chapter_label` is the human heading; the TOC is the ordered distinct list of
  `(chapter_key, chapter_label)` per document.

### 3.3 Anchor format

- `anchor` is a stable, collection-shaped, URL-safe key, unique within a document, used for deep-linking
  (Read More → exact passage). It is **derived from structure**, not from row order, so it survives re-ingest.

  | Collection | anchor shape | example |
  |---|---|---|
  | bible | `{book-slug}/{chapter}/{verse}` (first verse of the passage) | `john/3/16` |
  | summa | `{part}/q{question}/a{article}/{sub}` | `i-ii/q68/a3/i-answer` |
  | church-fathers | `{work-slug}/{section-slug}` | `first-epistle-corinthians/chapter-49` |
  | catechism | `ccc/{first-paragraph}` or `ccc/{node-path}` | `ccc/2558` |
  | encyclicals | `{slug}/{section-ordinal}` | `rerum-novarum/12` |
  | councils | `{council-slug}/{doc-slug}/{ordinal}` | `nicaea-i/creed/1` |
  | canon-law | `can/{canon-number}` | `can/247` |
  | medieval | `{work-slug}/{section-slug}` | `imitation/1-3` |

- A passage that spans several base units (e.g. a Bible pericope of verses 1–8) anchors to its **first** unit.

---

## 4. Qdrant point contract

- Collection: `"chunks"` (unchanged), 1536-dim, cosine, HNSW `m=16 ef_construct=64`, payload keyword index
  on `collection` (unchanged).
- **One point per passage. `point.id == chunks.id`** (same UUID in both stores) — this is what makes RRF
  dedup across vector + FTS correct.
- Vector: the embedding of the **augmented** text (§5), not the stored text.
- Payload (all required unless noted):

  ```
  collection       str
  document_id      str   # deterministic, §2
  document_title   str
  author           str | null
  content          str   # CLEAN passage text (same as Supabase content)
  reference        str   # clean citation
  anchor           str   # §3.3 — NEW, powers Read More deep-link
  chapter_label    str   # NEW — lets results show section context
  ```

- `services/api/app/rag/retrieve.py` already reads `content, reference, collection, document_id,
  document_title, author`; it gains `anchor` (and `chapter_label`). The search result surfaced to the
  frontend (`ChunkResult.source`) gains `anchor`.

---

## 5. Embedding augmentation contract (overlap, decoupled from storage)

- Stored `content` is always clean and non-overlapping. **Overlap exists only in the embedding input.**
- For passage `Pₙ`, the embedded string is:

  ```
  embedding_input(Pₙ) = context_prefix + tail(Pₙ₋₁, k_prev) + Pₙ + head(Pₙ₊₁, k_next)
  ```

  - `context_prefix`: short structural hint (e.g. `"[John 3] "`) so the vector knows its locus without
    polluting stored text.
  - `tail/head`: up to `k_prev`/`k_next` characters of neighboring passages **within the same chapter_key**
    (never across documents; configurable to not cross chapter boundaries).
- `k_prev`, `k_next`, and `context_prefix` style are a **per-collection knob** (the relocated home of
  today's per-strategy overlap tuning). Default ≈ 200 chars each side; 0 disables.

---

## 6. API contract

All endpoints stay under `/v1`, require JWT, and respect existing auth/RLS/rate-limit rules. The
`POST /v1/chat` and `POST /v1/search` SSE contracts are **unchanged** except that each streamed result's
`source` object gains an `anchor` field (additive).

### New / changed endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/documents/{id}/toc` | **New.** Ordered chapter list: `[{chapter_key, chapter_label}]` + document metadata. Powers the book/chapter pickers and Contents drawer. |
| GET | `/v1/documents/{id}/reader?anchor=…` | **Changed.** Returns the chapter section containing `anchor` as ordered clean passages, plus `prev_chapter_key`/`next_chapter_key` for infinite scroll, and `highlight_anchor`. `?chapter={chapter_key}` selects a section directly; with neither, returns the first chapter. Replaces the ±position-window response. |
| GET | `/v1/sources` | **Changed.** Every row carries a real `document_id`. Bible is returned as book-level documents grouped under their translation. Synthetic-ID church-fathers logic removed. |

### Response shapes (Pydantic, `app/models/documents.py`)

```
ReaderPassage:  { id, anchor, chapter_key, chapter_label, unit_label?, reference?, content }
ReaderChapter:  { document: DocumentResponse, chapter_key, chapter_label,
                  passages: [ReaderPassage], prev_chapter_key?, next_chapter_key?,
                  highlight_anchor? }
TocEntry:       { chapter_key, chapter_label }
TocResponse:    { document: DocumentResponse, chapters: [TocEntry] }
SourceDocument: { id, collection, title, author?, year?, translation?, metadata?, chunk_count }
```

---

## 7. Invariants (must hold)

- Frontend never talks to the DB; all access via FastAPI (CLAUDE.md §1).
- Migrations are additive SQL only; RLS unchanged on user-owned tables (§4).
- `POST /v1/chat` and `POST /v1/search` request/response contracts unchanged (§3, §10, §14).
- Collections remain sourced from `services/api/app/rag/constants.py` (§13).
- Qdrant collection name (`chunks`), dims (1536), and model (`text-embedding-3-large`) unchanged.

---

## 8. Open items

- **`content_embedding` removal — decided:** the vector need not live in Supabase (the
  `chunks.id == point.id` link suffices). We stop populating it now and **leave the column dormant/NULL**;
  a physical `DROP COLUMN` (non-additive, CLAUDE.md §4) is deferred to an optional later cleanup migration.
- Final per-collection `k_prev/k_next` overlap values — tuned during pipeline implementation.
