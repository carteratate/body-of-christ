# Final Four Collections — Dual-Pipeline Adapters (encyclicals, councils, canon-law, medieval)

> **Superseded publication design.** Preserve this file as design history; do not run
> its publication commands. Use [`datapipeline/README.md`](../../../datapipeline/README.md).

**Date:** 2026-06-21
**Status:** Draft (design) — awaiting owner review
**Depends on:** [Shared Contract](2026-06-13-passage-contract-design.md) · [Dual Datapipeline](2026-06-13-dual-datapipeline-design.md)

Bring the last four corpus collections into the dual datapipeline so they produce clean,
anchored `Passage`s readable in the new reader with Supabase↔Qdrant parity. This follows the
established pattern (bible, catechism, church-fathers, summa are already done); it adds one
`build_documents()` adapter per collection plus a `BUILDERS` registration. No contract, schema,
reader, or writer changes.

---

## 1. What is already fixed (constraints, not decisions)

From the contract (§2–3.3) and dual-pipeline design (§4):

| Collection | Document unit (`work_key`) | Anchor shape | unit_label |
|---|---|---|---|
| medieval | one per `(author, work)` | `{work-slug}/{section-slug}` | — |
| encyclicals | one per encyclical `(slug)` | `{slug}/{N}` | `§N` |
| councils | one per `(council, document)` | `{council-slug}/{section-slug}/{ordinal}` | `Canon N` / `§N` |
| canon-law | **single** document | `can/{N}` | `Can. N` |

Invariants carried over: deterministic ids via `identity.py`; `content` is **clean** (no
`[breadcrumb]` prefixes, no `(1/3)` suffixes — those are removed, structure goes to
`reference`/`chapter_label`/`unit_label`); `search_vector` auto-generated; `content_embedding`
not written; passages capped at `settings.MAX_PASSAGE_CHARS` via sentence/whitespace sub-split;
dedup suffix `--N` kept distinct from split suffix `/pN`; the author-aware
`UNIQUE(collection, title, translation, author)` constraint must not be violated.

No new SQL migration: `anchor`, `chapter_key`, `chapter_label`, `unit_label` and the author-aware
unique constraint are already live (migrations 0004–0014). This will be verified against dev before
the live run, not assumed.

---

## 2. Source acquisition (DONE) — vendored, not live-fetched

**Decision:** vendor first. `scripts/vendor_sources.py` has downloaded all sources into
`sources/<collection>/` with a `manifest.json` (`pages.json` for canon-law) capturing
title/author/year/url/file per document. Adapters read **local files only** — no network at ingest.
This removes upstream-site risk from the paid live run, makes tests reproducible against real data,
and matches the existing four collections. Counts vendored: medieval 4, encyclicals 18, councils 36
(20 ecumenical + 16 Vatican II), canon-law 44 pages.

`vendor_sources.py` is idempotent (`--force` to re-download) and is the recorded provenance tool
(design §7). `scripts/audit_sources.py` is the read-only structural-analysis tool used to derive
this design (kept for future re-audits).

---

## 3. Structural findings that shaped the design

- **Encyclicals (18) — per-document layout study:** three numbering layouts must be handled —
  **A inline** (`12. body…`, 14 docs), **B heading+body** (a short/bold `N.` line with the body in
  the following `<p>`s — Redemptor Hominis & Laborem Exercens, which produced *zero* paragraphs under
  the old inline-only regex), and **A+B mixed** (Evangelii Nuntiandi, Evangelium Vitae). Only these
  **4 documents** are non-trivial; the rest are pure inline. Section structure: ~8 are genuinely
  sectioned (Roman/bold headers interspersed among paragraphs), the rest flat. Critically, the
  `bold=2` seen on every flat document is **title/subtitle noise** rendered before §1, not a section
  → rule: **ignore Roman/bold headers that occur before the first numbered paragraph** (title +
  preamble); only headers between numbered paragraphs are chapters. Footnote `[N]` density is high
  (≤225/doc). A few single paragraphs exceed 3,500 chars (Spe Salvi 4,458). Every doc has a preamble
  (greeting) before §1.
- **Councils (36):** heterogeneous. Ecumenical 1–20 split into header-prose (h2/h3/h4), numbered
  canons (`Canon N`), and plain prose; Vatican II is numbered `§` paragraphs under `CHAPTER N`
  headers. ALL-CAPS headings throughout; some footnote dumps.
- **Canon-law (1,747 canons):** **max canon = 2,031 chars — none exceed the cap**, so
  one-passage-per-canon never sub-splits. **Structural correction:** vatican.va serves the Code as 44
  canon-range pages and **Book/Title headers appear only on the page where a section starts** —
  continuation pages carry no header, so the current per-page parse loses the Book for ~40% of canons
  (the `?` bucket). Fix: assign **Book by canon-number range** (the 7 books have fixed ranges) and
  **carry Title/Chapter context across page boundaries** in canon order. With that fix, the
  Book+Title+Chapter grouping yields **237 chapters, median ~2.2k chars / 6 canons** (max 21k / 38
  canons). Hierarchy header text is inconsistent and ALL-CAPS ("BOOK I." vs "BOOK I. GENERAL NORMS").
- **Medieval (4):** CCEL ThML — identical format to church-fathers. Anselm `basic_works.xml` is
  multi-work/single-author (div1=work); Boethius/Bernard/Imitation are single works whose div1/div2
  are chapters/books.

---

## 4. Confirmed design decisions

1. **Granularity:** one passage per numbered unit (§ / canon) for encyclicals & councils — precise
   anchors, `unit_label`, embedding overlap restores context. Oversized units sub-split.
2. **Header-less fallback:** paragraph-range buckets (chapter = `§§1–20`, …) so long flat documents
   stay navigable. Documents *with* headers group by header.
3. **Canon-law reader chapter:** Book + Title + Chapter (option C — 237 chapters, ~6 canons each),
   `chapter_label` = cleaned breadcrumb that **matches the grouping level**
   ("Book III: The Teaching Function of the Church — {Title} — {Chapter}").
4. **Medieval Imitation:** keep one passage per chapter (no merge); overlap supplies search context.

---

## 5. Per-collection design

### 5.1 medieval (`ingest/medieval.py` → rewrite)

- Reuse church-fathers' per-work builder. **Refactor:** extract `_make_doc` + `_cap_pieces` from
  `ingest/church_fathers.py` into a shared helper (e.g. `ingest/thml_doc.py`) so both collections
  share one tested path; church-fathers behavior unchanged.
- `build_documents()` iterates `sources/medieval/manifest.json`; for each entry reads the local XML,
  overrides ThML title/author/year from the manifest.
- **Anselm** (`fix_author: true`): div1 = work; author = "Anselm"; one Document per work-div1; skip
  front-matter via `_cf_skippable`. **Others:** single Document; `iter_chapters` flattens
  book→chapter ("Book N · Chapter M").
- `document_id("medieval", author, work)`; `anchor = {work-slug}/{section-slug}` (+`/pN`);
  `chapter_key` = same base; `chapter_label` = book·chapter or chapter label; `reference =
  "{author} — {title}, {label}"`; `unit_label = None`. Cleaners: `clean_text`, `smart_title_case`.

### 5.2 encyclicals (`ingest/encyclicals.py` → rewrite)

- `build_documents()` iterates `sources/encyclicals/manifest.json`; one Document per encyclical
  (`document_id("encyclicals", slug)`), title/author(=Pope)/year from manifest.
- **Tokenizer** over `<p>` produces a typed stream: `section` (Roman `^[IVX]+\.` or bold-only header),
  `para` (a numbered unit — assembled from inline `N. body…` OR a bold/short `N.`/`N. title` heading
  plus the following body `<p>`s until the next number/header), and `preamble` (leading unnumbered
  prose). **Per-document layout study (all 18) drives this:** only 4 docs are non-trivial — Redemptor
  Hominis & Laborem Exercens are pure heading+body (layout B); Evangelii Nuntiandi & Evangelium Vitae
  are mixed; the other 14 are inline. **Rule:** headers (Roman/bold) appearing *before* the first
  numbered paragraph are title/preamble, not chapters, and are excluded from section detection (this
  removes the title-noise that otherwise looks like 2 sections on every flat doc).
- **Passage = one numbered §** → `anchor = {slug}/{N}`, `unit_label = "§N"`,
  `reference = "{title}, §{N}"`. Oversized § sub-split → `{slug}/{N}/pK`. Leading preamble (greeting)
  becomes a single "Preamble" passage when present (`anchor = {slug}/preamble`).
- **chapter_key:** if the doc has ≥1 real section header → group by section (`chapter_label` =
  title-cased heading, `chapter_key = {slug}/sec-{ordinal}`); else paragraph-range buckets of
  `ENCYCLICAL_BUCKET` (=20) (`chapter_key = {slug}/bucket-{k}`, `chapter_label = "Paragraphs A–B"`).
- Cleaners: `strip_footnote_markers` (body), `title_case_shouting` (headings), `clean_text`.

### 5.3 councils (`ingest/councils.py` → rewrite)

- `build_documents()` iterates `sources/councils/manifest.json`, branching on `group`:
  - **ecumenical-1-20:** one Document per council (`document_id("councils", council, council)`;
    `title = council`, `author = None`). Detect h2/h3/h4 headers → chapter boundaries; `Canon N` →
    passage (`unit_label = "Canon N"`, `anchor = {council-slug}/canon/{N}`); numbered `N.` → passage
    (`unit_label = "§N"`); plain prose → accumulate to the cap as sequential passages
    (`anchor = {council-slug}/{section-slug}/{seq}`). Header-less councils use paragraph/​prose
    buckets per §4.2.
  - **vatican-ii:** one Document per document (`document_id("councils", "Second Vatican Council",
    title)`; `title = doc`, `author = None`, `metadata.council = "Second Vatican Council"`,
    `document_type`). `CHAPTER N` → chapter; numbered `§` → passage
    (`unit_label = "§N"`, `anchor = {doc-slug}/{chapter-slug|n}/{N}`).
- `reference`: ecumenical `"{council} — {section}"` / `"{council}, Canon N"`; Vatican II
  `"{doc}, §{N}"`. Cleaners: `strip_footnote_markers`, `title_case_shouting`, `clean_text`.
- Title/author = None for all councils ⇒ no unique-constraint collision (council and Vatican II
  titles are each distinct).

### 5.4 canon-law (`ingest/canon_law.py` → rewrite)

- `build_documents()` reads `sources/canon-law/pages.json`, parses each page with `parse_canon_page`,
  dedups by canon number (sorted) → one Document (`document_id("canon-law")`; title "Code of Canon
  Law (1983)", author "Catholic Church", year 1983).
- **Passage = one per canon** (never split, max 2,031 < cap): `anchor = can/{N}`,
  `unit_label = "Can. N"`, `position` = global order by canon number,
  `reference = "Code of Canon Law, Can. {N}"`. Content = cleaned canon body (`clean_text`;
  `§`-subparagraph markers preserved as paragraph breaks).
- **Hierarchy assignment (the structural fix):** Book is assigned by **canon-number range** from a
  fixed 7-entry table (I:1–203, II:204–746, III:747–833, IV:834–1253, V:1254–1310, VI:1311–1399,
  VII:1400–1752) with canonical English names — not from page headers (which are missing on
  continuation pages). Title/Chapter are taken from the per-page detected context and
  **forward-filled across pages** in canon order (reset at each Book boundary); ALL-CAPS Title/Chapter
  headers are Title-cased via `title_case_shouting`.
- **chapter_key** = `book/title/chapter` (option C — 237 chapters); `chapter_label` = the matching
  breadcrumb "Book III: The Teaching Function of the Church — {Title} — {Chapter}" (omitting empty
  levels). Verified by a pre-live-run print of the full chapter-label list to catch fragmentation.

---

## 6. Registration & writers (unchanged path)

Each adapter registers in `run_collection.py` `BUILDERS`:

```python
"medieval":    medieval.build_documents,
"encyclicals": encyclicals.build_documents,
"councils":    councils.build_documents,
"canon-law":   canon_law.build_documents,
```

Writers, identity, model, and the CLI are untouched. Per-collection overlap knobs added to
`config.PER_COLLECTION_OVERLAP` (default `(200,200)`; canon-law/encyclicals benefit from neighbor
overlap given small units — tuned during implementation, default acceptable).

---

## 7. Testing (TDD)

Per-adapter unit tests, fixtures-first then real-file smoke tests against the vendored sources:

- **Parser edge cases (inline fixtures):** encyclical three layouts incl. the heading+body case
  (Redemptor/Laborem produce numbered paragraphs); pre-§1 header noise excluded from sections;
  footnote `[N]` stripped; oversized § sub-splits with `/pN`; bucket fallback labels; canon Book
  assigned by number range; Title/Chapter forward-filled across page boundaries; ALL-CAPS Title
  cased.
- **Per-document encyclical assertions (from the layout study):** each of the 18 produces a non-trivial
  passage count (so a layout-B regression fails loudly) — e.g. Redemptor Hominis & Laborem Exercens
  yield their ~20/~25 §-passages under their Roman chapters; the flat docs yield their full §-runs in
  §§-buckets; the 4 non-trivial docs (2 pure-B, 2 mixed) have explicit count checks.
- **Real-file invariants:** doc counts; `content` never begins with `[`; anchors unique per
  document; `chapter_key`/`chapter_label` non-null; `unit_label` set where expected; canon-law emits
  one passage per unique canon (1,747), exactly 7 books, ~237 chapters, and no `?`/empty Book;
  medieval Anselm → 3 work documents, single-author preserved.
- Shared invariants already covered by `test_identity.py`, `test_reader_writer.py`,
  `test_search_writer.py`, `test_run_collection.py`. Do **not** introduce new failures; the
  pre-existing `test_catechism.py::test_tier3_in_brief_section_flagged` failure is out of scope.

Run: `cd datapipeline && python3 -m pytest -q`.

---

## 8. Sequencing & the live-run gate

1. **medieval** (proof; reuses CF machinery) → 2. **encyclicals** → 3. **councils** →
   4. **canon-law**. Each: write adapter + tests (green) before its live run.
2. **APPROVAL GATE:** `run_collection.py --collection <name> --target both --clean` spends OpenAI
   embedding money and mutates dev Supabase + Qdrant. Get explicit approval per collection before
   running. First do a dry build (`--target reader --limit 1` or an in-process build) to confirm the
   adapter; then the full `--target both --clean`.
3. **Parity verification** after each live run: per-collection Supabase count == Qdrant point count;
   anchors non-null; a sampled `chunks.id` exists in Qdrant with clean payload + anchor. Optional
   end-to-end via FastAPI `TestClient` (`/v1/documents/{id}/toc` + `/reader`) with
   `get_current_user` override and the `x-internal-secret` header.

`clear_collection` (Supabase) + `--clean` (Qdrant) replace the old pre-rework chunks; FKs cascade,
so clearing is safe. Bookmarks/retrievals pointing at old chunk ids for these collections do not
survive (ids change) — accepted, consistent with the church-fathers rebuild.

---

## 9. Risks (both headline risks reduced by the §3 studies)

- **Encyclical/council layouts** are heterogeneous, but the per-document study (§3, §5.2) reduced this
  to 4 known non-trivial encyclicals; the unified tokenizer is guarded by **per-document count
  assertions**, so any layout regression fails a specific test rather than silently dropping a doc.
  Councils get the same treatment over the 36 vendored docs.
- **Canon-law hierarchy** is now mostly **deterministic** (Book by canon-number range, not header
  scraping); only Title/Chapter labels rely on cross-page forward-fill + Title-casing. A pre-live-run
  print of the 237 chapter labels is the final eyeball before any embedding spend. A bug here affects
  only grouping/labels — never anchors (`can/{N}`) or content.
- Per-collection embedding overlap defaults may need tuning for very short canons (config knob, no
  re-architecture).
