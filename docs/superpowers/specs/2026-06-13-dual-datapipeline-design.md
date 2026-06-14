# Dual Datapipeline — Direct-to-Qdrant + Direct-to-Supabase, with a Cleaning Layer

**Date:** 2026-06-13
**Status:** Approved (design)
**Depends on:** [Shared Contract](2026-06-13-passage-contract-design.md)

## 1. Goals

1. Replace the painful 3-step chain (ingest→Supabase → `embed.py` → `migrate_to_qdrant.py`) with **two
   direct pipelines** fed by **one parse**:
   - **Reader pipeline** → Supabase (clean passages + FTS).
   - **Search pipeline** → embed (neighbor-augmented) → Qdrant.
2. Produce **clean, structurally-modeled passages** (the contract's canonical passage) for **every**
   collection — production-grade, easy to read, no strange formatting.
3. Fix the church-fathers metadata, fix the Summa artifacts, and delete stale Qdrant points before
   re-ingest.

Non-goals: changing the retrieval algorithm (HyDE/RRF/rerank), LangGraph/agents (forbidden, CLAUDE.md §5),
serverless.

## 2. Architecture

```
                         ┌─────────────────────────────────────────┐
   source file  ──parse──►   ordered list of CLEAN passages         │
   (per collection)      │   (content, reference, anchor,           │
                         │    chapter_key/label, unit_label, pos)   │
                         └──────────────┬───────────────┬──────────┘
                                        │               │
                       reader_writer    │               │   search_writer
                       (Supabase upsert)▼               ▼  (embed + Qdrant upsert)
                  documents + chunks (clean,        Qdrant "chunks"
                  search_vector, anchors)           (point.id == chunk.id,
                                                     vector from augmented text)
```

- **One parse, one passage list, two writers.** Identity (`document_id`) and `anchor` are assigned once in
  the parse stage, so both writers agree (contract §2–3). No Supabase→Qdrant migration step.
- Pipelines can run **independently** (`--target reader|search|both`) and are **idempotent** (upsert by
  `(document_id, position)` in Supabase; by point id in Qdrant).

## 3. datapipeline module layout

Restructure `datapipeline/` around the passage as the shared currency:

```
datapipeline/
  config.py                  # + QDRANT_URL/QDRANT_API_KEY, per-collection overlap knobs
  identity.py                # NEW: DOCUMENT_NS, document_id(work_key), anchor builders, slugify
  model.py                   # NEW: Passage dataclass (content, reference, anchor, chapter_key,
                             #      chapter_label, unit_label, position, metadata) + Document
  normalize/                 # NEW: pure, unit-tested text cleaners (§5)
    text.py                  #   whitespace, punctuation, ellipsis, smart-quote policy
    caps.py                  #   ALL-CAPS → Title Case (titles, references)
    footnotes.py             #   strip inline [N] endnote anchors
    summa.py                 #   abbreviation expansion + reference reconstruction
  ingest/<collection>.py     # produce CLEAN structured Passage lists (no DB writes)
  writers/
    reader_writer.py         # Supabase upsert of documents + clean passages (replaces load.py role)
    search_writer.py         # build augmented embed input, batch-embed, Qdrant upsert
    qdrant.py                # Qdrant client + ensure_collection + filtered delete
  embed.py                   # batch OpenAI embeddings (reused by search_writer)
  run_all.py                 # orchestrate: parse → writers, with CLI flags
  scripts/
    delete_collection_qdrant.py   # NEW: filtered delete (Step 4)
  sources/<collection>/      # source files (see §7 acquisition)
```

- `ingest/*` stop importing `load`; they return `list[Passage]`. Writers own all I/O.
- CLI (run_all + per-collection): `--collection`, `--target {reader,search,both}`, `--dry-run`, `--limit`,
  `--clean` (delete the collection's Qdrant points before search-write), `--overlap`, `--max-passage`
  (override the per-collection config defaults for this run).

## 4. Passage construction per collection (structural rules)

The parse stage emits **clean, contiguous, non-overlapping** passages, grouped into chapter sections, with
a hard **max passage size** (≈3,500 chars; oversized units split into clean sub-passages that stay
contiguous in the reader and become sibling search points with embed-time overlap).

- **Bible** — **passage = pericope / natural heading section, clamped to chapter boundaries** (never
  per-verse). The **reader section is the chapter** (`chapter_key = {book}/{chapter}`); a chapter groups its
  pericope passages. A source pericope that spans chapters (e.g. `2 Samuel 15:1–19:43`) is **split at each
  chapter boundary** so a passage never crosses a chapter and one-chapter-at-a-time reading works; the
  pericope heading is carried onto each part. Passage heading = pericope title; `anchor =
  {book}/{chapter}/{first-verse}`. Verse boundaries are retained (inline markers / `metadata`) so the reader
  renders superscript verse numbers, but the verse is never the chunk/search unit. Max-size sub-splitting
  still applies to any over-long passage. Net: chunk counts stay near today's (~3k), no mega-blobs.
- **Summa** — `chapter_key` = Article; split each Article into its natural parts as sub-passages with
  `unit_label`: `Objection 1..n`, `On the contrary`, `I answer that`, `Reply to Objection 1..n`. This fixes
  the 46k giants. Apply Summa cleaners (§5.2). Reference reconstructed to `Summa Theologiae, {part}, Q. {q},
  A. {a}`.
- **Catechism** — keep the three-tier chunker's strengths but: **merge** TOC-only fragments
  (`Article 2`, `PART TWO:`) into the following content or promote to `chapter_label`; never emit a 9-char
  structural passage. `unit_label` = CCC `§`; normalize scriptural ellipses.
- **Church-fathers** — **one document per (father, work)** parsed from the ThML `div1`=father / `div2`=work
  structure; Augustine multi-work files keyed by work with author `Augustine`; skip front-matter
  (`title page, contents, preface, introductory notice, elucidations, …`); drop standalone "Introductory
  Note" div2s. Clean references (no `…Testaments., Chapter 5 (3/4)`).
- **Encyclicals** — section passages; strip inline footnote `[N]`; Title-case shouting section titles.
- **Councils** — per (council, document); chapter/section passages; Title-case shouting headings; handle
  the few footnote dumps.
- **Canon-law** — per-canon passages; `unit_label`/anchor = canon number; Title-case `THE FORMATION OF
  CLERICS`-style titles.
- **Medieval** — per (author, work); chapter/section passages.

## 5. Cleaning layer (full inventory — approved scope)

All cleaning is **pure functions** in `normalize/`, applied in the parse stage, unit-tested with
golden samples. Smart/curly quotes are **kept** (good typography). Two tiers:

### 5.1 Universal (all collections)
- **Whitespace**: collapse runs of spaces; remove spaces before `. , ; : ! ?`; trim; normalize blank-line
  paragraph breaks.
- **Ellipsis**: normalize genuine omission marks (`. . .`, `...`) → a single `…`. **Distinguish** from
  pathological long dot-runs (≥4 spaced dots — table/diagram artifacts, e.g. the Summa "diagram") which
  collapse to a paragraph break / single space.
- **ALL-CAPS shouting** (≥3 consecutive all-caps words) in headings, titles, and **references** → Title
  Case (preserve known acronyms/roman numerals).
- **Inline footnote anchors** `[N]` that are endnote markers (encyclicals, councils) → stripped. (Does
  **not** touch meaningful bracket data handled elsewhere — CCC numbers are stored in `unit_label`, Summa
  `Q[7]` is expanded by §5.2.)
- **Editorial bracket-star notes** `[*Cf. …]` → dropped (or converted to a clean parenthetical).

### 5.2 Summa apparatus (collection-specific)
Expand the cryptic scheme in **content and references**:

| Token | Expansion |
|---|---|
| `FP`,`SP`,`FS`,`SS`,`TP`,`XP` | First Part, Second Part, First Part of the Second Part, Second Part of the Second Part, Third Part, Supplement |
| `Q[n]` / `QQ[n]-[m]` | Q. n / Qq. n–m |
| `A[n]` / `AA[n],m` | A. n / Aa. n, m |
| `OBJ[n]` | Objection n |
| `SC` | "On the contrary" |
| `RO[n]` / reply markers | Reply to Objection n |
| `Question. 102` (period-after-word) | Question 102 |

- **Reference reconstruction**: from the raw breadcrumb build
  `Summa Theologiae, {part-abbrev I/I-II/II-II/III/Suppl.}, Q. {q}, A. {a} — {Title-cased article title}`.
- Strip the rare leader-dot table run (the original brief's artifact) — **now fixed**, superseding the
  earlier "documentation only" instruction.

### 5.3 Church-fathers references
- Build `reference` from clean (father, work, section); collapse `.,`/double punctuation; no `(n/m)` split
  suffix (splitting handled by sub-passage `unit_label` instead).

## 6. Embedding & Qdrant write (search pipeline)
- Model `text-embedding-3-large`, `dimensions=1536`; batch ≤100; retry on 429 (reuse `embed.py` pattern).
- Embed the **augmented** input per contract §5 (`context_prefix + tail(prev) + content + head(next)`,
  per-collection knob); store **clean** content in payload.
- Qdrant point id = passage id; payload per contract §4 (incl. `anchor`, `chapter_label`).
- `ensure_collection` matches existing config; upsert idempotent; `--clean` filter-deletes the collection
  first.

## 7. Source acquisition workstream (approved: re-acquire first)
Local sources exist only for **bible, catechism, church-fathers, summa**. Before the uniform structural
rework, re-acquire the rest and record provenance under `sources/<collection>/` + a `SOURCES.md`:
- **medieval** — re-download from the ccel.org URLs already listed in `ingest/medieval.py`.
- **encyclicals, canon-law, councils** — locate and vendor the original sources (the DB has the data but no
  local source). Until acquired, these collections are **blocked** for full re-ingest.
- Re-ingest proceeds collection-by-collection as sources land; the contract guarantees stable identity so
  re-ingests are safe/idempotent.

## 8. Church-fathers rebuild + Qdrant cleanup (the brief's Steps 2 & 4)
- **Rebuild** church-fathers to per-(father, work) documents writing to **both** stores via the dual
  pipeline (supersedes the earlier "Qdrant-only" instruction — the reader and FTS require Supabase).
  Parser changes live in `ingest/church_fathers.py` + the ThML helpers in `ingest/common.py`
  (`_detect_is_multi_author`, `_build_reference`, div1/div2 work extraction).
- **Step 4 — delete stale points first**: `scripts/delete_collection_qdrant.py --collection church-fathers`
  filter-deletes `payload.collection == "church-fathers"` before re-ingest (also reusable via `--clean`).

## 9. Migration & data changes
- Additive SQL migration adds `anchor, chapter_key, chapter_label, unit_label` to `chunks` + indexes
  (contract §3.1). The Supabase `chunks.content_embedding` pgvector column is **retired** — no longer
  written; vectors live only as Qdrant point vectors, linked by `chunks.id == point.id`. Left dormant
  (dropping it is non-additive; see contract §8).
- `documents.id` becomes the deterministic UUIDv5 — for clean collections this is achieved by re-ingest;
  existing rows are superseded by upsert. (Document a one-time reconciliation for any FK references —
  searches/retrievals/bookmarks point at `chunks.id`, which are re-created; bookmarks to old church-fathers
  chunks will not survive the rebuild — acceptable, flagged.)
- `services/api/app/routes/sources.py` simplified to the contract's `SourceDocument` (real ids, bible
  book-level), deleting `_get_church_fathers`.

## 10. Testing
- Unit tests per cleaner in `normalize/` with golden before/after samples drawn from the real artifacts
  found in the audit (Summa apparatus, catechism ellipses, encyclical footnotes, ALL-CAPS titles).
- Identity/anchor tests: determinism, uniqueness per document.
- Passage-size invariant: no passage exceeds the max; sub-splits remain contiguous.
- Idempotency: re-running a pipeline produces no duplicates and stable ids.
- Pipeline parity: a sampled passage exists in both Supabase and Qdrant with identical id + clean content.

## 11. Sequencing (within pipeline work)
1. Contract migration (schema) + `identity.py` + `model.py` + `normalize/` with tests.
2. `writers/` (reader + search) against the contract.
3. Re-ingest the 4 locally-sourced collections (bible, catechism, church-fathers, summa) — church-fathers
   includes the `--clean` Qdrant delete.
4. Source acquisition → re-ingest encyclicals, canon-law, councils, medieval.
5. Retire `migrate_to_qdrant.py` and the embed-into-Supabase path.

## 12. Risks / open items
- Sourcing encyclicals/canon-law/councils may block step 4; bible/catechism/CF/summa are unblocked.
- Bookmarks referencing rebuilt church-fathers chunks are lost on rebuild (ids change) — **accepted by owner.**
- Overlap (`k_prev/k_next`) and max-passage size are **config values** in `datapipeline/config.py` with
  per-collection defaults, overridable per-run via `--overlap` / `--max-passage`; not hardcoded constants.
  Tuned by editing config or passing a flag and re-running.
