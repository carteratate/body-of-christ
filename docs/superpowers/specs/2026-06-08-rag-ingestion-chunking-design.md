# RAG Ingestion Chunking — Design Spec
**Date:** 2026-06-08
**Scope:** Ingestion layer (Church Fathers, Encyclicals, Canon Law) + one retrieval fix (reranker)
**Status:** Approved for implementation

---

## Background

The current ingestion pipeline has three structural problems:

1. **Church Fathers** chunks at the wrong div level for most files — producing Book-level blobs of 10,000–50,000 chars that get arbitrarily sentence-split, losing all chapter structure.
2. **Encyclicals** use a fixed 3-paragraph window with zero overlap and no section awareness, producing chunks that cut across natural argument boundaries.
3. **Canon Law** emits one chunk per canon with no hierarchical context and no grouping, making topic-area retrieval weak.

Additionally, the **reranker** truncates chunk content to 600 chars before scoring, while chunks may be up to 3,500 chars — making 83% of each chunk invisible to the reranker.

---

## How Chunks Flow Through the Pipeline

Understanding downstream consumers constrains every design decision:

| Field | Consumers | Implication |
|---|---|---|
| `content` | Vector embedding (full text, truncated at 8,000 tokens) | Everything meaningful for retrieval must be here |
| `content` | FTS via `search_vector` (auto-generated column: `to_tsvector('english', content)`) | Author names, doc titles, canon numbers in content = free keyword matching |
| `content` | Reranker: `[chunk_id] {reference}: {content}` (post-fix: full content) | Headers must be front-loaded — most query-relevant signal in the opening lines |
| `content` | Explainer: `Passage ({reference}): {content}` | Full content; richer content = richer explanation |
| `content` | UI: displayed to user | Must be human-readable |
| `reference` | Reranker (as passage prefix) and Explainer (as passage label) | Must be a clean, complete citation — NOT embedded |
| `metadata` | Not used in retrieval currently | Store for future retrieval enhancements |

**Hard ceiling: 3,500 chars per chunk.** Splits always happen at structural unit boundaries (never mid-sentence, mid-paragraph, or mid-canon). When a natural unit must be split, use a **balanced split** — find the boundary closest to the midpoint of the unit, not the greedy first-fit.

---

## Change 1 — Reranker: Remove Content Truncation

**File:** `services/api/app/rag/rerank.py`

**Current:**
```python
snippet = c.content[:600]
```

**Change to:**
```python
snippet = c.content
```

**Rationale:** The 600-char limit was an arbitrary guard against prompt size. At `default_quota=4`, `candidate_multiplier=4`, the reranker receives up to 16 candidates per collection per call. At 3,500 chars each: 16 × 3,500 = 56,000 chars ≈ 14,000 tokens — well within Claude Haiku's 200K-token context window. The incremental cost is ~$0.012 per user search query across all collections. The ingestion ceiling (3,500 chars) is now the single control point for chunk size. No redundant truncation in the reranker.

---

## Change 2 — Church Fathers: `datapipeline/ingest/common.py`

### 2a. Depth-Adaptive Chunking

Replace the hardcoded div1→div2 walk in `_chunk_standard` with a depth-adaptive algorithm that detects the correct chunk level per file.

**Algorithm:**
1. Walk all div elements in the document. For each div, check whether it has at least one direct `<p>` child.
2. The deepest div level (div1, div2, div3, or div4) for which this is true across the majority of structural divs is the **chunk level**.
3. The immediate parent div at the level above is the **breadcrumb level**.
4. Walk all ancestors of each chunk-level div to build the full ancestry path for the reference.

**Per-file results (verified against source XML):**

| File | Chunk level | Breadcrumb parent |
|---|---|---|
| `confessions.xml` | div2 (Chapter) | div1 (Book) |
| `city-of-god.xml` | div3 (Chapter) | div2 (Book) |
| `on-the-holy-trinity.xml` | div4 (Chapter) | div3 (Book) |
| `incarnation.xml` | div1 (Chapter — special case, `type="chapter"`) | none |
| `apostolic-fathers.xml` | div3 (Chapter) | div2 (Work), div1 (Author) |
| `second-century.xml` | div3 (Vision/Commandment/Similitude) | div2 (Book type), div1 (Author) |
| `third-century.xml` | div3 (Chapter) | div2 (Work), div1 (Author) |
| `third-century-2.xml` | div4 (Chapter) | div3 (Book), div2 (Work), div1 (Author) |
| `third-century-3.xml` | div4 (Chapter) | div3 (Work), div2 (Part), div1 (Author) |
| `third-fourth-century.xml` | div4 (Chapter) | div3 (Book), div2 (Work), div1 (Author) |

**Special case — `incarnation.xml`:** Chapters live at div1. Detect this when div1 elements carry `type="chapter"`. Treat div1 as the chunk level; there is no parent breadcrumb.

**Skip list:** Exclude divs whose `title` (case-insensitive) is one of: `"title page"`, `"contents"`, `"table of contents"`, `"preface"`, `"editor's preface"`, `"introductory notice"`, `"introductory note"`, `"elucidations"`, `"indexes"`. These are editorial scaffolding, not content.

### 2b. Content Format

```
[{parent_shorttitle}] {chunk_title_up_to_120_chars}

{paragraph text...}
```

- **`parent_shorttitle`**: The `shorttitle` attribute of the immediate parent div (e.g., `"Book I"`, `"Part I"`, `"Book First.—Visions"`). Omitted if no meaningful parent exists (incarnation.xml, or when parent title is in the skip list).
- **`chunk_title`**: The full `title` attribute of the chunk-level div, truncated to 120 chars if longer. This is the descriptive chapter annotation that drives topic-matching in the embedding.
- **Exception — generic-titled chapters:** When ALL chunk-level divs in a file have titles matching `^Chapter [IVXLCDM]+$` (i.e., every chapter is named only by its roman numeral with no descriptive text), inject nothing — the title carries no semantic signal. Use only the breadcrumb path. Detection: check all chunk-level `title` attrs before chunking; if every one matches the pattern, set a `generic_titles=True` flag. Confessions is the primary case; any future file that shares this pattern will also qualify. Content format for this case:
  ```
  [Book I, Chapter I]

  Great art Thou, O Lord, and greatly to be praised...
  ```

**Example — City of God:**
```
[Book I] Of the Adversaries of the Name of Christ, Whom the Barbarians for Christ's Sake Spared When They Stormed the City

When the barbarians sacked Rome, they spared, for Christ's sake, all those...
```

**Example — Apostolic Fathers:**
```
[First Epistle to the Corinthians] Chapter I.—The salutation. Praise of the Corinthians before the breaking forth of schism among them.

The Church of God which sojourns in Rome to the Church of God which sojourns in Corinth...
```

**Example — Shepherd of Hermas:**
```
[Book First.—Visions] Vision First. Against Filthy and Proud Thoughts, and the Carelessness of Hermas in Chastising His Sons.

He who brought me up sold me to a certain Rhoda, who was at Rome...
```

### 2c. Reference Format

Full ancestry path, always. Build by walking up the div tree from the chunk level:

```
{Author} — {Work}, {Book shorttitle}, {Chapter shorttitle or number}
```

Examples:
- `"Augustine — City of God, Book I, Chapter 3"`
- `"Clement of Rome — First Epistle to the Corinthians, Chapter I"`
- `"Hippolytus — Refutation of All Heresies, Book I, Chapter I"`
- `"Lactantius — Divine Institutes, Book I, Chapter I"`
- `"Augustine — Confessions, Book I, Chapter I"`
- `"Athanasius — On the Incarnation, Chapter 1"`

Author comes from the `DC.Creator` metadata in the ThML head (already parsed). Work comes from the div1 or div2 `title` that identifies the work within the volume. Book and Chapter use `shorttitle` where available, falling back to `n` attribute (roman numeral) or sequential number.

### 2d. Ceiling and Split

- **Ceiling:** 3,500 chars.
- Chapters within the ceiling: one chunk, whole.
- Chapters exceeding the ceiling: apply `split_at_sentences()` with **target 1,800 chars**, 200-char sentence-boundary overlap. Both parts keep the full breadcrumb header. Reference for split parts appends ` (1/2)` / ` (2/2)` (e.g., `"Augustine — City of God, Book I, Chapter 3 (1/2)"`).

### 2e. Metadata

```json
{
  "author_id": "augustine",
  "book_id": "npnf102",
  "div_depth": 3,
  "parent_shorttitle": "Book I",
  "chapter_title": "Of Suicide Committed Through Fear of Punishment or Dishonour",
  "source_file": "city-of-god.xml"
}
```

---

## Change 3 — Encyclicals: `datapipeline/ingest/encyclicals.py`

### 3a. Section-Boundary Detection

Add a `_detect_section_header(element) -> str | None` function. A `<p>` element is a section header when:
- Its entire text content is wrapped in `<b>` or `<strong>` (the element itself contains only a bold/strong child, not inline bold within a sentence), **or**
- Its text matches `^[IVX]+\.\s+\w` (Roman numeral pattern: "I. Title text").

When a section header is detected during the parse pass, it is **not** included as a paragraph in any chunk. Instead, it is stored as the **active section label** for subsequent chunks.

All section labels encountered during a parse are collected into a list for the intro chunk (see §3d).

### 3b. Chunk Accumulation — Variable Window with Section Awareness

Replace the fixed 3-paragraph window in `group_paragraphs` with the following logic:

1. Accumulate paragraphs, tracking total character count.
2. Flush a chunk when **either**:
   - A section boundary is detected (always flush immediately before the new section), **or**
   - Adding the next paragraph would push the chunk past **1,200 chars** and the chunk already has at least one paragraph.
3. **Ceiling (safety net):** After flushing a chunk, if the emitted chunk exceeds **3,500 chars** (possible only when a single paragraph is longer than 1,200 chars and cannot be split at the paragraph boundary), apply a **balanced split** at the paragraph boundary closest to the midpoint of the chunk's paragraphs. Both halves carry the same section label. In practice this is extremely rare — virtually no encyclical paragraph is > 3,500 chars alone. The ceiling guard is a correctness invariant, not a normal code path.
4. Paragraphs shorter than 50 chars are filtered out (unchanged from current behavior).

### 3c. Leading One-Paragraph Overlap

Within a section, the last paragraph of chunk N becomes the **first paragraph** of chunk N+1. Overlap **resets** at section boundaries — the last paragraph of section A does not appear in the first chunk of section B.

The overlap paragraph is prepended to the content of chunk N+1 before the new paragraphs. This puts overlap within the opening content visible to the embedding and reranker.

### 3d. Intro Chunk (Position 0)

One intro chunk is written at `position=0` for each encyclical, before any paragraph chunks. It is built from:

1. **Preamble text:** Unnumbered paragraphs appearing before the first `^\d+\.\s+` numbered paragraph. Many encyclicals open with a papal greeting and thesis statement. Captured as a block, truncated at 600 chars.
2. **Section list:** All section headers detected during the parse pass, joined as `"Sections: I. ... II. ... III. ..."`. Truncated at 400 chars if many sections.

**Intro chunk content format:**
```
{Title} — {Author}, {Year}

{Preamble text, up to 600 chars}

Sections: {detected section headers, comma-separated}
```

If no preamble is found and no sections are detected, the intro chunk is skipped.

**Intro chunk reference:** `"{Title} — Overview"`

### 3e. Content Format (Regular Chunks)

```
In {Title} (Pope {Author}, {Year})[, §{Section Label}]:

{overlap paragraph, if same section}

{para 1}

{para 2}...
```

The section label in brackets is included only when a section header is active. If no section header has been detected, the content is:

```
In {Title} (Pope {Author}, {Year}):

{para 1}

{para 2}...
```

The document prefix (`"In {Title} (Pope {Author}, {Year}):"`) is always present. It is short (35–50 chars) and ensures author name, document title, and year are in every chunk's embedding and FTS index.

### 3f. Reference Format

```
{Title}, §§{first_para_num}–{last_para_num}
```

Example: `"Laudato Si, §§148–150"`

For the intro chunk: `"Laudato Si — Overview"`

### 3g. Metadata

```json
{
  "section": "III. The Human Roots of the Ecological Crisis",
  "para_range": [148, 150],
  "scripture_refs": ["Gn 1:28", "Sir 17:3–10"],
  "year": 2015,
  "pope": "Pope Francis"
}
```

**Scripture refs** are parsed from each paragraph's text using a regex covering standard citation formats: `Mt 5:13`, `1 Cor 13:4–7`, `Gn 1:28`, `Ps 24:1`, etc. Pattern: `r'\b([1-3]\s*[A-Z][a-z]+|[A-Z][a-z]+)\s+\d+:\d+(?:[–\-]\d+)?'`. Collected per paragraph, deduplicated across the chunk. Not used in current retrieval; stored for future cross-collection boosting.

---

## Change 4 — Canon Law: `datapipeline/ingest/canon_law.py`

### 4a. Hierarchy Tracking in the Parser

`parse_canon_page` currently skips ALL-CAPS text as section headers. Instead, maintain a running context dict and update it when headers are encountered:

```python
context = {"book": "", "part": "", "title": "", "chapter": "", "article": ""}
```

**Header classification:** When a paragraph's stripped text is ALL-CAPS or starts with a known keyword (`BOOK`, `PART`, `TITLE`, `CHAPTER`, `ART.`, `ARTICLE`, `SECTION`), classify it by keyword and update the appropriate context key. When a higher-level key updates, reset all lower-level keys to `""`:

Level order (high → low): `book → part → title → chapter → article`

Each parsed canon is returned as `(canon_num, canon_text, context_snapshot)` where `context_snapshot` is a copy of the current context dict at parse time.

**Test impact:** `test_parse_canon_skips_headers` verifies that header text does not appear in canon text fields — this remains true. The test's sample HTML has no Book/Title/Chapter/Article headers, so canon output is unchanged. Update the test to also verify that a header in the HTML updates the context rather than appearing in canon text.

### 4b. Article-Level Grouping in `main()`

After deduplication (unchanged — first-occurrence wins by canon number), group consecutive canons by their `context_key`:

```python
def context_key(ctx):
    return (ctx["book"], ctx["part"], ctx["title"], ctx["chapter"], ctx["article"])
```

`part` is included to prevent merging same-named titles that appear in different parts of the same book (e.g., Book IV has Parts I, II, III). For books with no `part` level, `part` will be `""` for all canons in that book, so grouping is unaffected.

**Fallback levels:** If `article` is empty, group by `(book, part, title, chapter)`. If `chapter` is also empty, group by `(book, part, title)`. If `title` is empty (and `part` is empty), group by `(book,)`. This handles Books (like V) that have no intermediate hierarchy.

Consecutive canons sharing the same context key form one group.

### 4c. Balanced Split at 3,500-Char Ceiling

When a group's formatted content exceeds 3,500 chars:

1. Find the canon index closest to the midpoint of the group (by character count of accumulated canon texts, not by canon count).
2. Split there. Both halves keep the full hierarchy header.
3. If either half still exceeds 3,500 chars, recurse.

Each resulting chunk's reference reflects its actual canon range.

### 4d. Content Format

```
{Book} — {Title}
{Chapter} — {Article}

Can. {N}: {text including §1, §2... sub-paragraphs}

Can. {N+1}: {text}
...
```

The hierarchy header is two lines. Lines are omitted when the corresponding context key is empty (e.g., if there is no Article, the second line is just `{Chapter}`; if there is no Chapter either, the second line is omitted entirely and only the Book-Title line appears).

The `Can. N:` prefix is always present and ensures every canon number is in the FTS index.

**Example:**
```
Book II — The People of God
Title I — The Obligations and Rights of All the Christian Faithful

Can. 208: In virtue of their rebirth in Christ, there exists among all the Christian faithful a true equality with regard to dignity and the activity whereby all cooperate in the building up of the Body of Christ in accord with each one's own condition and function.

Can. 209 §1: The Christian faithful, even in their own manner of acting, are always obliged to maintain communion with the Church.
§2: The faithful have the right to make known to the sacred pastors their needs, especially spiritual ones, and their desires.
```

### 4e. Reference Format

```
Code of Canon Law — {Book}, {Title} (Cann. {first}–{last})
```

Example: `"Code of Canon Law — Book II, Title I (Cann. 208–223)"`

When only one canon is in the chunk: `"Code of Canon Law — Book I (Can. 1)"`

### 4f. Metadata

```json
{
  "book": "Book II",
  "part": "",
  "title": "Title I",
  "chapter": "Chapter I",
  "article": "Article 1",
  "canon_range": [208, 223],
  "cross_refs": [204, 207, 869]
}
```

**Cross-references:** Parsed from canon text with `re.findall(r"(?:can(?:on)?\.?\s*)(\d+)", text, re.IGNORECASE)`. Collected per canon, deduplicated across the group. Stored for future graph-based retrieval boosting.

---

## Chunk Size Summary

| Source | Expected mean | Expected ceiling behavior |
|---|---|---|
| Church Fathers | ~800–1,500 chars (chapter-level) | ~10–15% of chapters split; 1,800-char target sliding window |
| Encyclicals | ~600–1,200 chars (section-aware) | Rare ceiling hits; balanced paragraph split when triggered |
| Canon Law | ~2,109 chars (measured) | 28.7% of groups hit ceiling; balanced canon-boundary split |

---

## Tests to Update

| File | Tests affected |
|---|---|
| `tests/test_common.py` | All tests — `_chunk_standard` behavior changes; reference format changes; add depth-adaptive tests |
| `tests/test_encyclicals.py` | `test_group_paragraphs_*` — new accumulation logic; add section-boundary tests, overlap tests, intro chunk test |
| `tests/test_canon_law.py` | `test_parse_canon_skips_headers` — update to verify context tracking; add hierarchy grouping tests |

---

## Out of Scope

- Retrieval layer changes beyond the reranker truncation fix
- Summa Theologica (unchanged)
- Bible (unchanged)
- Saints (unchanged)
- `annotation_embedding` activation
- Schema migrations (no new columns required; `metadata` JSONB already exists)
