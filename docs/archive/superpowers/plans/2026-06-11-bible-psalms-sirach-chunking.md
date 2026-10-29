# Bible Psalms & Sirach Chunking Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two chunking quality problems in `bible.py`: Psalms currently chunks into 5 massive blobs (one per "Book of Psalms"), and Sirach chunks per-chapter despite having 245 explicit stanza-break (`\b`) markers in the USFM that define natural thematic units.

**Architecture:** Two independent changes to `datapipeline/ingest/bible.py`. (1) **Psalms**: add `"Psalms"` to the existing `_DEUTEROCANONICAL_BOOKS` set — this re-routes it through the existing `chunk_deuterocanonical_book` function, producing 150 per-psalm chunks with no new code. (2) **Sirach**: introduce a `_STANZA_BOOKS` set, remove Sirach from `_DEUTEROCANONICAL_BOOKS`, add `parse_usfm_stanzas()` to read `\b` boundaries from a USFM file, add `chunk_stanza_book()` to emit one chunk per stanza, store the USFM file path in `BookVerses` so `ingest_webc` can call the stanza parser, and add a third routing branch in `ingest_webc`.

**Tech Stack:** Python 3.12, pytest, USFM files in `datapipeline/sources/bible/eng-web-c_usfm/`. All tests run via `cd datapipeline && python3 -m pytest tests/test_bible.py -v` from the repo root.

---

## Background

**Psalms problem:** `PericopeGroupedKJVVerses.json` defines only 5 pericopes for Psalms ("Book 1" through "Book 5"), each spanning 30–50 chapters. This yields 5 chunks with 40–50 psalms each — useless for retrieval. Since each chapter in the Psalms USFM file is one psalm, routing through `chunk_deuterocanonical_book` produces 150 per-psalm chunks automatically.

**Sirach problem:** Sirach is currently in `_DEUTEROCANONICAL_BOOKS` → per-chapter chunking → 51 chunks averaging 2,716 chars, each mixing 3–12 completely different topics. The WEB-C USFM for Sirach contains 245 `\b` (blank-line paragraph / stanza-break) markers that delimit natural thematic units. Chunking at `\b` boundaries yields ~246 focused stanzas at a useful size for semantic search.

**`\b` marker semantics:** In the Sirach USFM, `\b` appears as its own line (with optional trailing whitespace) and signals the start of a new thematic stanza. When `\b` is seen, the verses accumulated since the previous `\b` form one complete stanza. Chapter boundaries (`\c`) also flush the current stanza so a stanza never crosses chapter lines.

---

## File Map

| File | Change |
|---|---|
| `datapipeline/ingest/bible.py` | All implementation changes |
| `datapipeline/tests/test_bible.py` | New tests for Psalms routing + stanza functions |

No other files touch. No schema migrations needed (existing `chunks`/`documents` tables already handle the new shapes).

---

## Task 1: Psalms — Route through per-chapter chunking

**Files:**
- Modify: `datapipeline/ingest/bible.py` (line 108–110, `_DEUTEROCANONICAL_BOOKS`)
- Modify: `datapipeline/tests/test_bible.py` (append new test)

- [ ] **Step 1: Write the failing test**

Add to the bottom of `datapipeline/tests/test_bible.py`:

```python
# ---------------------------------------------------------------------------
# Psalms routing
# ---------------------------------------------------------------------------

from ingest.bible import _DEUTEROCANONICAL_BOOKS


def test_psalms_in_deuterocanonical_books():
    """Psalms must be routed through per-chapter chunking, not pericope chunking."""
    assert "Psalms" in _DEUTEROCANONICAL_BOOKS
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py::test_psalms_in_deuterocanonical_books -v
```

Expected: FAIL — `AssertionError: assert 'Psalms' in frozenset(...)`

- [ ] **Step 3: Add Psalms to `_DEUTEROCANONICAL_BOOKS`**

In `datapipeline/ingest/bible.py`, change lines 107–110:

```python
# Deuterocanonical books + Psalms chunked per-chapter (not by pericope).
# Psalms pericopes in the JSON are only 5 "Book of Psalms" blobs; per-chapter
# gives one chunk per psalm (150 total), which is far better for retrieval.
_DEUTEROCANONICAL_BOOKS: frozenset[str] = frozenset({
    "Tobit", "Judith", "1 Maccabees", "2 Maccabees", "Wisdom", "Sirach", "Baruch",
    "Psalms",
})
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -v
```

Expected: all 29 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible.py
git commit -m "fix(bible): route Psalms through per-chapter chunking — 150 psalm chunks instead of 5 blobs"
```

---

## Task 2: Sirach — Add `usfm_path` to `BookVerses`

**Files:**
- Modify: `datapipeline/ingest/bible.py` (the `BookVerses` dataclass + `load_usfm_directory`)

This enables `ingest_webc` to call `parse_usfm_stanzas` with the path of the Sirach file. Adding `usfm_path` as an optional field with a default of `""` keeps all existing tests passing.

- [ ] **Step 1: Add `usfm_path` field to `BookVerses`**

In `datapipeline/ingest/bible.py`, change the `BookVerses` dataclass (around line 129):

```python
@dataclass
class BookVerses:
    name: str               # canonical book name
    book_code: str          # USFM code e.g. "GEN"
    testament: str          # "OT" | "NT"
    verses: list[Verse] = field(default_factory=list)
    usfm_path: str = ""     # absolute path to source .usfm file
```

- [ ] **Step 2: Populate `usfm_path` in `load_usfm_directory`**

In `datapipeline/ingest/bible.py`, update the `BookVerses(...)` constructor call inside `load_usfm_directory` (around line 250):

```python
        books[canonical] = BookVerses(
            name=canonical,
            book_code=code,
            testament=testament,
            verses=verse_list,
            usfm_path=path,
        )
```

- [ ] **Step 3: Run the full test suite — verify all still pass**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -v
```

Expected: all 29 tests PASS (existing tests use `_make_book()` which leaves `usfm_path=""`, so no breakage).

- [ ] **Step 4: Commit**

```bash
git add datapipeline/ingest/bible.py
git commit -m "refactor(bible): add usfm_path field to BookVerses for stanza parsing"
```

---

## Task 3: Sirach — `parse_usfm_stanzas` function

**Files:**
- Modify: `datapipeline/ingest/bible.py` (new function after `parse_usfm_file`)
- Modify: `datapipeline/tests/test_bible.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Add to `datapipeline/tests/test_bible.py`, after the imports block at the top (add `parse_usfm_stanzas` to the import list):

```python
from ingest.bible import (
    _clean_usfm_text,
    _format_reference,
    _parse_ref,
    _DEUTEROCANONICAL_BOOKS,
    BookVerses,
    Verse,
    Pericope,
    collect_pericope_verses,
    chunk_canonical_book,
    chunk_deuterocanonical_book,
    load_pericopes,
    parse_usfm_file,
    parse_usfm_stanzas,
)
```

Then add these tests at the bottom of the file (after the Psalms test):

```python
# ---------------------------------------------------------------------------
# parse_usfm_stanzas
# ---------------------------------------------------------------------------

_STANZA_USFM = textwrap.dedent(r"""
    \id SIR
    \c 1
    \b
    \q1
    \v 1 All wisdom comes from the Lord,
    \q2 and is with him forever.
    \v 2 Who can count the sand of the seas,
    \b
    \v 3 The fear of the Lord is glory, exultation,
    \v 4 Whoever fears the Lord, it will go well for him.
    \c 2
    \v 1 My son, if you come to serve the Lord,
    \v 2 prepare your soul for temptation.
    \b
    \v 3 Set your heart right, and endure.
""").lstrip()


def _write_stanza_usfm(content: str) -> str:
    import tempfile
    f = tempfile.NamedTemporaryFile(suffix=".usfm", mode="w", encoding="utf-8", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_parse_usfm_stanzas_count():
    """\\b markers and chapter boundaries together define stanza count."""
    path = _write_stanza_usfm(_STANZA_USFM)
    try:
        stanzas = parse_usfm_stanzas(path)
        # ch1: 2 stanzas (each \\b flushes); ch2: 2 stanzas (\\c flush + \\b flush)
        assert len(stanzas) == 4
    finally:
        os.unlink(path)


def test_parse_usfm_stanzas_first_stanza_verses():
    """First stanza contains exactly the verses before the first \\b in ch1."""
    path = _write_stanza_usfm(_STANZA_USFM)
    try:
        stanzas = parse_usfm_stanzas(path)
        stanza0 = stanzas[0]
        assert len(stanza0) == 2
        ch, v, text = stanza0[0]
        assert ch == 1 and v == 1
        assert "All wisdom" in text
    finally:
        os.unlink(path)


def test_parse_usfm_stanzas_chapter_boundary_flush():
    """\\c marker flushes current stanza; ch2's first verses become a new stanza."""
    path = _write_stanza_usfm(_STANZA_USFM)
    try:
        stanzas = parse_usfm_stanzas(path)
        # stanza index 2 = first stanza of ch2 (flushed by \\b at line "\\b")
        ch2_stanzas = [s for s in stanzas if s and s[0][0] == 2]
        assert len(ch2_stanzas) == 2
        assert ch2_stanzas[0][0] == (2, 1, "My son, if you come to serve the Lord,")
    finally:
        os.unlink(path)


def test_parse_usfm_stanzas_clean_text():
    """Verse text in stanzas has USFM markers stripped (\\q1, \\q2, etc.)."""
    path = _write_stanza_usfm(_STANZA_USFM)
    try:
        stanzas = parse_usfm_stanzas(path)
        for stanza in stanzas:
            for ch, v, text in stanza:
                assert "\\q" not in text
                assert "\\v" not in text
    finally:
        os.unlink(path)


def test_parse_usfm_stanzas_verse_tuple_structure():
    """Each verse in a stanza is a (chapter: int, verse: int, text: str) tuple."""
    path = _write_stanza_usfm(_STANZA_USFM)
    try:
        stanzas = parse_usfm_stanzas(path)
        for stanza in stanzas:
            for item in stanza:
                assert len(item) == 3
                ch, v, text = item
                assert isinstance(ch, int)
                assert isinstance(v, int)
                assert isinstance(text, str) and text
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -k "stanzas" -v
```

Expected: `ImportError: cannot import name 'parse_usfm_stanzas'`

- [ ] **Step 3: Implement `parse_usfm_stanzas`**

Add this function to `datapipeline/ingest/bible.py` immediately after `parse_usfm_file` (around line 214):

```python
def parse_usfm_stanzas(path: str) -> list[list[tuple[int, int, str]]]:
    """Parse a USFM file into stanza groups defined by \\b (blank-line) markers.

    Returns a list of stanzas; each stanza is a list of (chapter, verse, clean_text).
    A \\b line flushes the accumulated verses as a completed stanza.
    A \\c (chapter) line also flushes so stanzas never cross chapter boundaries.
    """
    stanzas: list[list[tuple[int, int, str]]] = []
    current: list[tuple[int, int, str]] = []
    current_chapter: int = 0
    current_verse: int | None = None

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n\r")

            # Stanza break: \b as its own line (optional trailing whitespace).
            if re.match(r"^\\b\s*$", line):
                if current:
                    stanzas.append(current)
                    current = []
                current_verse = None
                continue

            # Chapter marker: flush current stanza before switching chapters.
            c_match = re.match(r"^\\c\s+(\d+)", line)
            if c_match:
                if current:
                    stanzas.append(current)
                    current = []
                current_chapter = int(c_match.group(1))
                current_verse = None
                continue

            # Verse marker: start a new verse entry in the current stanza.
            v_match = re.match(r"^\\v\s+(\d+)\s*(.*)", line)
            if v_match and current_chapter > 0:
                current_verse = int(v_match.group(1))
                text = _clean_usfm_text(v_match.group(2))
                current.append((current_chapter, current_verse, text))
                continue

            # Continuation line for current verse.
            if current_verse is not None and current_chapter > 0:
                if re.match(r"^\\(id|ide|h|toc|mt|imt|ms|mr|s|sr|r|d|sp|li|lim|cls)\b", line):
                    current_verse = None
                    continue
                cleaned = _clean_usfm_text(line)
                if cleaned and current:
                    ch, v, prev = current[-1]
                    if ch == current_chapter and v == current_verse:
                        current[-1] = (ch, v, f"{prev} {cleaned}")

    if current:
        stanzas.append(current)

    return stanzas
```

- [ ] **Step 4: Run stanza tests — verify they pass**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -k "stanzas" -v
```

Expected: 5 stanza tests PASS.

- [ ] **Step 5: Run full suite — no regressions**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -v
```

Expected: all 34 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible.py
git commit -m "feat(bible): add parse_usfm_stanzas — groups verses by \\b marker boundaries"
```

---

## Task 4: Sirach — `chunk_stanza_book` function

**Files:**
- Modify: `datapipeline/ingest/bible.py` (new function after `chunk_deuterocanonical_book`)
- Modify: `datapipeline/tests/test_bible.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Add `chunk_stanza_book` to the import list at the top of `datapipeline/tests/test_bible.py`:

```python
from ingest.bible import (
    _clean_usfm_text,
    _format_reference,
    _parse_ref,
    _DEUTEROCANONICAL_BOOKS,
    BookVerses,
    Verse,
    Pericope,
    collect_pericope_verses,
    chunk_canonical_book,
    chunk_deuterocanonical_book,
    chunk_stanza_book,
    load_pericopes,
    parse_usfm_file,
    parse_usfm_stanzas,
)
```

Then add these tests at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# chunk_stanza_book
# ---------------------------------------------------------------------------

_TEST_STANZAS: list[list[tuple[int, int, str]]] = [
    [(1, 1, "All wisdom comes from the Lord"), (1, 2, "and is with him forever")],
    [(1, 3, "The fear of the Lord is glory exultation"), (1, 4, "Whoever fears the Lord")],
    [(2, 1, "My son if you come to serve the Lord"), (2, 2, "prepare your soul for temptation")],
    [(2, 3, "x")],   # too short — must be skipped
]


def test_chunk_stanza_book_skips_short_stanzas():
    """Stanzas whose joined text is below min_chars are skipped."""
    chunks = list(chunk_stanza_book("Sirach", "OT", _TEST_STANZAS, "WEB-C", min_chars=20))
    assert len(chunks) == 3


def test_chunk_stanza_book_reference_same_chapter():
    """Same-chapter stanza reference uses 'Book ch:sv–ev' format."""
    chunks = list(chunk_stanza_book("Sirach", "OT", _TEST_STANZAS, "WEB-C", min_chars=20))
    _, ref, _, _ = chunks[0]
    assert ref == "Sirach 1:1–2"


def test_chunk_stanza_book_reference_single_verse():
    """Single-verse stanza uses 'Book ch:v' (no range)."""
    single = [[(3, 5, "A" * 30)]]
    chunks = list(chunk_stanza_book("Sirach", "OT", single, "WEB-C", min_chars=20))
    _, ref, _, _ = chunks[0]
    assert ref == "Sirach 3:5"


def test_chunk_stanza_book_reference_cross_chapter():
    """Cross-chapter stanza reference spans both chapter numbers."""
    cross = [[(1, 40, "end of chapter one content here"), (2, 1, "start of chapter two content here")]]
    chunks = list(chunk_stanza_book("Sirach", "OT", cross, "WEB-C", min_chars=20))
    _, ref, _, _ = chunks[0]
    assert ref == "Sirach 1:40–2:1"


def test_chunk_stanza_book_content_joins_verses():
    """Content is all verse texts joined with spaces."""
    chunks = list(chunk_stanza_book("Sirach", "OT", _TEST_STANZAS, "WEB-C", min_chars=20))
    content, _, _, _ = chunks[0]
    assert "All wisdom comes from the Lord" in content
    assert "and is with him forever" in content


def test_chunk_stanza_book_metadata():
    """Metadata contains book, chapter (of first verse), stanza index, testament, translation."""
    chunks = list(chunk_stanza_book("Sirach", "OT", _TEST_STANZAS, "WEB-C", min_chars=20))
    _, _, meta, _ = chunks[0]
    assert meta["book"] == "Sirach"
    assert meta["chapter"] == 1
    assert "stanza" in meta
    assert meta["testament"] == "OT"
    assert meta["translation"] == "WEB-C"


def test_chunk_stanza_book_positions_sequential():
    """Position values are 0-indexed and sequential across yielded chunks."""
    chunks = list(chunk_stanza_book("Sirach", "OT", _TEST_STANZAS, "WEB-C", min_chars=20))
    positions = [c[3] for c in chunks]
    assert positions == list(range(len(chunks)))


def test_chunk_stanza_book_returns_iterator():
    """chunk_stanza_book is a generator (yields lazily)."""
    import types
    result = chunk_stanza_book("Sirach", "OT", _TEST_STANZAS, "WEB-C")
    assert isinstance(result, types.GeneratorType)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -k "stanza_book" -v
```

Expected: `ImportError: cannot import name 'chunk_stanza_book'`

- [ ] **Step 3: Implement `chunk_stanza_book`**

Add this function to `datapipeline/ingest/bible.py` immediately after `chunk_deuterocanonical_book` (around line 416):

```python
def chunk_stanza_book(
    book_name: str,
    testament: str,
    stanzas: list[list[tuple[int, int, str]]],
    translation: str,
    min_chars: int = 50,
) -> Iterator[tuple[str, str, dict, int]]:
    """Yield (content, reference, metadata, position) for a stanza-chunked book.

    One chunk per stanza. Stanzas whose joined text is shorter than min_chars
    are skipped (handles near-empty stanzas from headings or footnote-only verses).
    """
    position = 0
    for stanza_idx, stanza_verses in enumerate(stanzas):
        if not stanza_verses:
            continue
        content = " ".join(text for _, _, text in stanza_verses)
        if len(content) < min_chars:
            continue

        start_ch, start_v, _ = stanza_verses[0]
        end_ch, end_v, _ = stanza_verses[-1]
        reference = _format_reference(book_name, start_ch, start_v, end_ch, end_v)

        metadata = {
            "book": book_name,
            "chapter": start_ch,
            "stanza": stanza_idx,
            "testament": testament,
            "translation": translation,
        }
        yield content, reference, metadata, position
        position += 1
```

- [ ] **Step 4: Run stanza_book tests — verify they pass**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -k "stanza_book" -v
```

Expected: all 8 `chunk_stanza_book` tests PASS.

- [ ] **Step 5: Run full suite — no regressions**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -v
```

Expected: all 42 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible.py
git commit -m "feat(bible): add chunk_stanza_book — one chunk per USFM stanza with verse-range reference"
```

---

## Task 5: Sirach — Wire into `ingest_webc`

**Files:**
- Modify: `datapipeline/ingest/bible.py` (constants + `ingest_webc`)

Remove `"Sirach"` from `_DEUTEROCANONICAL_BOOKS`, add `_STANZA_BOOKS`, and add a third routing branch in `ingest_webc` that calls `parse_usfm_stanzas` → `chunk_stanza_book`.

- [ ] **Step 1: Write the failing test**

Add to `datapipeline/tests/test_bible.py` (also add `_STANZA_BOOKS` to the import list):

```python
from ingest.bible import (
    _clean_usfm_text,
    _format_reference,
    _parse_ref,
    _DEUTEROCANONICAL_BOOKS,
    _STANZA_BOOKS,
    BookVerses,
    Verse,
    Pericope,
    collect_pericope_verses,
    chunk_canonical_book,
    chunk_deuterocanonical_book,
    chunk_stanza_book,
    load_pericopes,
    parse_usfm_file,
    parse_usfm_stanzas,
)
```

Then add at the bottom:

```python
# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------

def test_sirach_not_in_deuterocanonical_books():
    """Sirach must be removed from _DEUTEROCANONICAL_BOOKS once _STANZA_BOOKS exists."""
    assert "Sirach" not in _DEUTEROCANONICAL_BOOKS


def test_sirach_in_stanza_books():
    """Sirach must be in _STANZA_BOOKS so ingest_webc routes it through stanza chunking."""
    assert "Sirach" in _STANZA_BOOKS


def test_stanza_books_not_overlap_deuterocanonical():
    """_STANZA_BOOKS and _DEUTEROCANONICAL_BOOKS must be disjoint."""
    assert _STANZA_BOOKS.isdisjoint(_DEUTEROCANONICAL_BOOKS)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -k "sirach or stanza_books" -v
```

Expected: 3 failures (`_STANZA_BOOKS` does not exist, Sirach is still in `_DEUTEROCANONICAL_BOOKS`).

- [ ] **Step 3: Update the constants in `bible.py`**

Replace the `_DEUTEROCANONICAL_BOOKS` block (around line 107):

```python
# Books chunked per-chapter (one chunk per chapter).
# Psalms pericopes in the JSON only define 5 "Book of Psalms" blobs, so we
# route it here for one-chunk-per-psalm (150 chunks total).
_DEUTEROCANONICAL_BOOKS: frozenset[str] = frozenset({
    "Tobit", "Judith", "1 Maccabees", "2 Maccabees", "Wisdom", "Baruch",
    "Psalms",
})

# Books chunked per USFM \b stanza marker (requires usfm_path on BookVerses).
_STANZA_BOOKS: frozenset[str] = frozenset({
    "Sirach",
})
```

- [ ] **Step 4: Update `ingest_webc` partitioning**

In `ingest_webc` (around line 449), replace the two-partition block:

```python
    canonical_books = {
        name: bv for name, bv in all_books.items()
        if name not in _DEUTEROCANONICAL_BOOKS and name not in _STANZA_BOOKS
    }
    deutero_books = {
        name: bv for name, bv in all_books.items()
        if name in _DEUTEROCANONICAL_BOOKS
    }
    stanza_books = {
        name: bv for name, bv in all_books.items()
        if name in _STANZA_BOOKS
    }

    print(
        f"  {len(canonical_books)} canonical books (pericope chunking), "
        f"{len(deutero_books)} deuterocanonical/Psalms books (chapter chunking), "
        f"{len(stanza_books)} stanza books (stanza chunking)."
    )
```

- [ ] **Step 5: Add the stanza books loop in `ingest_webc`**

After the deuterocanonical loop (around line 530, after the last `pbar.update(1)`), add:

```python
        # --- Stanza books (Sirach) ---
        for book_name, book in sorted(stanza_books.items()):
            if not book.usfm_path:
                pbar.set_postfix({"book": book_name, "chunks": 0, "note": "no usfm_path"})
                pbar.update(1)
                continue

            testament = book.testament
            doc_id = await upsert_document(
                pool,
                collection="bible",
                title=book_name,
                translation=translation,
                author=None,
                year=None,
                metadata={"testament": testament},
            )

            stanzas = parse_usfm_stanzas(book.usfm_path)
            book_chunks = 0
            for content, reference, metadata, position in chunk_stanza_book(
                book_name, testament, stanzas, translation
            ):
                await upsert_chunk(
                    pool,
                    document_id=doc_id,
                    content=content,
                    position=position,
                    reference=reference,
                    metadata=metadata,
                )
                total_chunks += 1
                book_chunks += 1

            pbar.set_postfix({"book": book_name, "chunks": book_chunks})
            pbar.update(1)
```

- [ ] **Step 6: Run all tests — verify everything passes**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/test_bible.py -v
```

Expected: all 45 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible.py
git commit -m "feat(bible): stanza-level chunking for Sirach via \\b USFM markers (~246 chunks vs 51)"
```

---

## Final Verification

- [ ] **Run the full datapipeline test suite**

```bash
cd /home/carter/repos/body-of-christ/datapipeline && python3 -m pytest tests/ -v
```

Expected: All tests PASS across all test files.

---

## Self-Review Notes

**Spec coverage:**
- Psalms → 5 blobs → 150 per-psalm chunks ✓ (Task 1)
- Sirach → per-chapter → per-stanza (~246 chunks) ✓ (Tasks 2–5)
- `parse_usfm_stanzas` handles chapter-boundary flush ✓ (algorithm + test)
- `parse_usfm_stanzas` cleans USFM markers ✓ (reuses `_clean_usfm_text`)
- `chunk_stanza_book` skips short stanzas ✓ (Task 4)
- `chunk_stanza_book` uses verse-range reference ✓ (`_format_reference`)
- `_STANZA_BOOKS` and `_DEUTEROCANONICAL_BOOKS` are disjoint ✓ (Task 5 test)
- `ingest_webc` routes stanza books through new path ✓ (Task 5)
- All existing 28 tests still pass at each step ✓

**Type consistency:**
- `parse_usfm_stanzas` returns `list[list[tuple[int, int, str]]]` — matches `_TEST_STANZAS` fixture and `chunk_stanza_book` parameter type throughout.
- `chunk_stanza_book` signature `(book_name, testament, stanzas, translation, min_chars)` is consistent across Task 4 implementation and Task 5 call site.
- `BookVerses.usfm_path: str = ""` added in Task 2; used in Task 5 loop.
