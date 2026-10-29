# RAG Ingestion Chunking Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign chunking for Church Fathers, Encyclicals, and Canon Law to maximize RAG retrieval quality, and fix the reranker's 600-char truncation bug.

**Architecture:** Four independent changes: (1) a one-line reranker fix; (2) Church Fathers depth-adaptive ThML chunking via `common.py`; (3) section-boundary encyclical chunking; (4) hierarchy-grouped canon law chunking. Each change is independently testable with no schema migrations required.

**Tech Stack:** Python 3.12, BeautifulSoup4/lxml, defusedxml, pytest, asyncpg, anthropic SDK. All datapipeline tests run via `pytest datapipeline/tests/` from the repo root.

---

## File Map

| File | Change |
|---|---|
| `services/api/app/rag/rerank.py` | Remove `[:600]` truncation (1 line) |
| `datapipeline/ingest/common.py` | Full `_chunk_standard` rewrite + new helpers + 4-tuple interface |
| `datapipeline/ingest/church_fathers.py` | Unpack 4-tuple, inject `source_file` to metadata |
| `datapipeline/ingest/summa.py` | Unpack 4-tuple (ignore metadata) |
| `datapipeline/ingest/encyclicals.py` | Replace `parse_encyclical_paragraphs` + `group_paragraphs` with `parse_encyclical` |
| `datapipeline/ingest/canon_law.py` | Hierarchy tracking in parser + grouping + balanced split in `main()` |
| `services/api/tests/test_rerank.py` | Add full-content test |
| `datapipeline/tests/test_common.py` | Update all tests for 4-tuple and new reference format; add depth-adaptive tests |
| `datapipeline/tests/test_encyclicals.py` | Full rewrite for new `parse_encyclical` API |
| `datapipeline/tests/test_canon_law.py` | Update for 3-tuple parser return; add grouping tests |

---

## Task 1: Reranker — Remove 600-char truncation

**Files:**
- Modify: `services/api/app/rag/rerank.py:66`
- Test: `services/api/tests/test_rerank.py`

- [ ] **Step 1: Write the failing test**

Add to `services/api/tests/test_rerank.py`:

```python
def test_format_passages_includes_full_content():
    """Reranker must see the full chunk, not just the first 600 chars."""
    from app.rag.rerank import _format_passages
    c = ChunkCandidate(
        chunk_id="00000000-0000-0000-0000-000000000020",
        content="A" * 1000,
        reference="Test Ref",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Test",
        author=None,
        rrf_score=0.5,
    )
    result = _format_passages([c])
    assert "A" * 1000 in result
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd services/api && python -m pytest tests/test_rerank.py::test_format_passages_includes_full_content -v
```
Expected: FAIL (assertion error — only 600 A's in result)

- [ ] **Step 3: Make the change**

In `services/api/app/rag/rerank.py`, line 66:
```python
# Before:
snippet = c.content[:600]
# After:
snippet = c.content
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd services/api && python -m pytest tests/test_rerank.py -v
```
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/rerank.py services/api/tests/test_rerank.py
git commit -m "fix(rerank): pass full chunk content to Haiku — removes 600-char truncation"
```

---

## Task 2: common.py — 4-tuple interface for chunks

**Files:**
- Modify: `datapipeline/ingest/common.py`
- Modify: `datapipeline/ingest/summa.py`
- Modify: `datapipeline/ingest/church_fathers.py`
- Modify: `datapipeline/tests/test_common.py`

The `ThmlDocument.chunks` type changes from `list[tuple[str, str, int]]` to `list[tuple[str, str, int, dict | None]]`. This task makes the interface change while keeping all existing tests passing.

- [ ] **Step 1: Update `ThmlDocument` dataclass**

In `datapipeline/ingest/common.py`, update the class:

```python
@dataclass
class ThmlDocument:
    title: str
    author: str | None
    year: int | None
    chunks: list[tuple[str, str, int, dict | None]] = field(default_factory=list)
```

- [ ] **Step 2: Update `_chunk_summa` to return 4-tuples**

In `common.py`, change `_chunk_summa`'s append line:

```python
# Before:
chunks.append((content, reference, position))
# After:
chunks.append((content, reference, position, None))
```

- [ ] **Step 3: Update `_chunk_standard` to return 4-tuples**

In `common.py`, change both append lines inside `_chunk_standard`:

```python
# In the "fits in ceiling" path (currently: chunks.append((content, ref, position))):
chunks.append((content, ref, position, None))

# In the split path (currently: chunks.append((part, part_ref, position))):
chunks.append((part, part_ref, position, None))
```

- [ ] **Step 4: Update `summa.py` consumer**

In `datapipeline/ingest/summa.py`, line 44:
```python
# Before:
for content, reference, position in doc.chunks:
# After:
for content, reference, position, _meta in doc.chunks:
```

- [ ] **Step 5: Update `church_fathers.py` consumer**

In `datapipeline/ingest/church_fathers.py`, line 59:
```python
# Before:
for content, reference, position in doc.chunks:
    await upsert_chunk(pool, doc_id, content, position, reference)
# After:
for content, reference, position, _meta in doc.chunks:
    await upsert_chunk(pool, doc_id, content, position, reference)
```

- [ ] **Step 6: Update test unpacking**

In `datapipeline/tests/test_common.py`, update every line that unpacks `doc.chunks[N]` as a 3-tuple. Find all occurrences of `content, ref, pos = doc.chunks` and replace:

```python
# Replace all:
content, ref, pos = doc.chunks[0]
# With:
content, ref, pos, meta = doc.chunks[0]
```

Lines to update: `test_parse_thml_chapter_content_joined` (line 89), `test_parse_thml_reference_format` (lines 95-96), and `test_parse_thml_summa_reference_format` (line 117), `test_parse_thml_summa_article_content_complete` (line 122). Check all usages.

- [ ] **Step 7: Run tests — verify all pass**

```bash
cd datapipeline && python -m pytest tests/test_common.py -v
```
Expected: All tests PASS (same values, just 4-tuple unpacking)

- [ ] **Step 8: Commit**

```bash
git add datapipeline/ingest/common.py datapipeline/ingest/summa.py datapipeline/ingest/church_fathers.py datapipeline/tests/test_common.py
git commit -m "refactor(common): extend ThmlDocument chunks to 4-tuple (content, ref, pos, metadata)"
```

---

## Task 3: common.py — Add depth-adaptive helpers

**Files:**
- Modify: `datapipeline/ingest/common.py`
- Modify: `datapipeline/tests/test_common.py`

Add new constants and helper functions to `common.py` above `_chunk_standard`. Add tests for each helper.

- [ ] **Step 1: Add constants and `_build_parent_map`**

Insert after `_OVERLAP_CHARS = 200` (existing line):

```python
_SKIP_TITLES: frozenset[str] = frozenset({
    "title page", "contents", "table of contents", "preface",
    "editor's preface", "introductory notice", "introductory note",
    "elucidations", "indexes",
})

_GENERIC_CHAPTER_RE = re.compile(r"^Chapter [IVXLCDM]+$", re.IGNORECASE)

_CEILING = 3500
_CF_SPLIT_TARGET = 1800


def _build_parent_map(root) -> dict:
    """Return {child: parent} for every element in the tree."""
    parent_map: dict = {}
    for parent in root.iter():
        for child in parent:
            parent_map[child] = parent
    return parent_map
```

- [ ] **Step 2: Add `_detect_chunk_level`**

```python
def _detect_chunk_level(root) -> int:
    """Detect deepest div level (1-4) where most divs have direct <p> children.
    Special case: if any div1 carries type='chapter', return 1 (incarnation.xml).
    """
    for d in root.iter("div1"):
        if d.get("type") == "chapter":
            return 1

    level_total: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    level_with_p: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}

    for level in range(1, 5):
        for elem in root.iter(f"div{level}"):
            if (elem.get("title") or "").strip().lower() in _SKIP_TITLES:
                continue
            level_total[level] += 1
            if any(child.tag == "p" for child in elem):
                level_with_p[level] += 1

    for level in range(4, 0, -1):
        total = level_total[level]
        if total > 0 and level_with_p[level] / total > 0.5:
            return level
    return 1
```

- [ ] **Step 3: Add author/label helpers**

```python
def _detect_is_multi_author(root) -> bool:
    """True when the file groups content by multiple authors at div1 level."""
    titles = {(d.get("title") or "").strip() for d in root.iter("div1")}
    titles.discard("")
    return len(titles) > 1


def _maybe_title_case(s: str) -> str:
    return s.title() if s.isupper() else s


def _short_author_name(full_name: str) -> str:
    """'Augustine, Saint, Bishop of Hippo' → 'Augustine'."""
    return full_name.split(",")[0].strip()


def _parent_label(elem) -> str:
    """Short breadcrumb label for a div: shorttitle, then title[:30]."""
    st = (elem.get("shorttitle") or "").strip()
    if st:
        return st
    return (elem.get("title") or "").strip()[:30]


def _chunk_label(elem) -> str:
    """Short reference label for a chunk-level div."""
    st = (elem.get("shorttitle") or "").strip()
    if st:
        return st
    n = (elem.get("n") or "").strip()
    if n:
        return f"Chapter {n.upper()}"
    return (elem.get("title") or "").strip()[:50]
```

- [ ] **Step 4: Add `_build_reference`**

```python
def _build_reference(
    doc: ThmlDocument,
    is_multi_author: bool,
    chunk_elem,
    ancestors: list,
) -> str:
    """Build the full ancestry citation string for a chunk.

    Single-author: 'Augustine — The Confessions, Book I, Chapter I'
    Multi-author:  'Clement Of Rome — First Epistle to the Corinthians, Chapter I'
    """
    chunk_lbl = _chunk_label(chunk_elem)

    if is_multi_author:
        # ancestors[0] = div1 (author grouping), ancestors[1] = work, rest = path
        if not ancestors:
            return _maybe_title_case((chunk_elem.get("title") or "Unknown").strip())
        author_lbl = _maybe_title_case((ancestors[0].get("title") or "").strip())
        path = []
        for anc in ancestors[1:]:
            lbl = (anc.get("title") or "").strip()
            if lbl:
                path.append(lbl)
        if chunk_lbl:
            path.append(chunk_lbl)
        return f"{author_lbl} — {', '.join(path)}" if path else author_lbl
    else:
        short_author = _short_author_name(doc.author or "") or "Unknown"
        work = doc.title or "Unknown"
        path = []
        for anc in ancestors:
            lbl = _parent_label(anc)
            if lbl:
                path.append(lbl)
        if chunk_lbl:
            path.append(chunk_lbl)
        return f"{short_author} — {work}, {', '.join(path)}" if path else f"{short_author} — {work}"
```

- [ ] **Step 5: Write tests for all helpers**

Add to `datapipeline/tests/test_common.py`:

```python
# ── depth detection ──────────────────────────────────────────────────────────

import defusedxml.ElementTree as ET
from ingest.common import (
    _detect_chunk_level, _detect_is_multi_author,
    _short_author_name, _maybe_title_case, _build_reference,
)

_CONFESSIONS_THML = STANDARD_THML  # div1=Book, div2=Chapter → level 2

_CITY_THML = """<?xml version="1.0"?>
<ThML>
  <ThML.head><DC><DC.Title>City of God</DC.Title>
  <DC.Creator sub="Author" scheme="file-as">Augustine, Saint (354-430)</DC.Creator></DC></ThML.head>
  <ThML.body>
    <div1 title="Volume I" n="i">
      <div2 title="Book I" shorttitle="Book I" n="i">
        <div3 title="Of the enemies of Christ" n="i"><p id="p1">When the barbarians sacked Rome, they spared all those who fled for refuge.</p></div3>
        <div3 title="Of those who complain" n="ii"><p id="p2">But those complain of Christian times.</p></div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

_MULTI_AUTHOR_THML = """<?xml version="1.0"?>
<ThML>
  <ThML.head><DC><DC.Title>Apostolic Fathers</DC.Title>
  <DC.Creator sub="Author" scheme="file-as">Roberts, Alexander (1826-1901)</DC.Creator></DC></ThML.head>
  <ThML.body>
    <div1 title="CLEMENT OF ROME" n="i">
      <div2 title="First Epistle of Clement to the Corinthians" n="i">
        <div3 title="Chapter I. The salutation." n="i" shorttitle="Chapter I"><p id="p1">The Church of God which sojourns at Rome.</p></div3>
      </div2>
    </div1>
    <div1 title="IGNATIUS OF ANTIOCH" n="ii">
      <div2 title="Epistle to the Ephesians" n="i">
        <div3 title="Chapter I. Praise of the Ephesians." n="i" shorttitle="Chapter I"><p id="p2">Ignatius, who is also Theophorus.</p></div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

_INCARNATION_THML = """<?xml version="1.0"?>
<ThML>
  <ThML.head><DC><DC.Title>On the Incarnation</DC.Title>
  <DC.Creator sub="Author" scheme="file-as">Athanasius, Saint (c.296-c.373)</DC.Creator></DC></ThML.head>
  <ThML.body>
    <div1 title="Chapter 1. Creation and the Fall" type="chapter" n="i">
      <p id="p1">The Word of God, incorporeal and incorruptible.</p>
    </div1>
    <div1 title="Chapter 2. The Divine Dilemma" type="chapter" n="ii">
      <p id="p2">For God had made man thus.</p>
    </div1>
  </ThML.body>
</ThML>"""


def _root(xml_str: str):
    xml_str = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml_str, flags=re.DOTALL)
    return ET.fromstring(xml_str)


def test_detect_chunk_level_confessions():
    assert _detect_chunk_level(_root(STANDARD_THML)) == 2


def test_detect_chunk_level_city_of_god():
    assert _detect_chunk_level(_root(_CITY_THML)) == 3


def test_detect_chunk_level_incarnation_special_case():
    assert _detect_chunk_level(_root(_INCARNATION_THML)) == 1


def test_detect_is_multi_author_single():
    assert _detect_is_multi_author(_root(STANDARD_THML)) is False


def test_detect_is_multi_author_multi():
    assert _detect_is_multi_author(_root(_MULTI_AUTHOR_THML)) is True


def test_short_author_name():
    assert _short_author_name("Augustine, Saint, Bishop of Hippo") == "Augustine"
    assert _short_author_name("Athanasius") == "Athanasius"


def test_maybe_title_case_allcaps():
    assert _maybe_title_case("CLEMENT OF ROME") == "Clement Of Rome"
    assert _maybe_title_case("Clement of Rome") == "Clement of Rome"
```

- [ ] **Step 6: Run helper tests — verify all pass**

```bash
cd datapipeline && python -m pytest tests/test_common.py -v -k "detect or short_author or maybe_title"
```
Expected: All helper tests PASS

- [ ] **Step 7: Commit**

```bash
git add datapipeline/ingest/common.py datapipeline/tests/test_common.py
git commit -m "feat(common): add depth-adaptive helpers — detect chunk level, ancestry reference, author labels"
```

---

## Task 4: common.py — Rewrite `_chunk_standard`

**Files:**
- Modify: `datapipeline/ingest/common.py`
- Modify: `datapipeline/tests/test_common.py`

- [ ] **Step 1: Update existing tests to assert new expected behavior**

In `datapipeline/tests/test_common.py`, update these tests (they will FAIL until the implementation is done):

```python
def test_parse_thml_standard_chunks_by_chapter():
    doc = parse_thml_string(STANDARD_THML)
    # New behavior: no merge-up logic. Book I Ch I, Book I Ch II, Book II Ch I = 3 chunks.
    assert len(doc.chunks) == 3


def test_parse_thml_reference_format():
    doc = parse_thml_string(STANDARD_THML)
    _, ref0, _, _ = doc.chunks[0]
    _, ref1, _, _ = doc.chunks[1]
    _, ref2, _, _ = doc.chunks[2]
    # New format: Author — Work, Book, Chapter
    assert ref0 == "Augustine — The Confessions of Saint Augustine, Book I, Chapter I"
    assert ref1 == "Augustine — The Confessions of Saint Augustine, Book I, Chapter II"
    assert ref2 == "Augustine — The Confessions of Saint Augustine, Book II, Chapter I"


def test_parse_thml_chapter_content_joined():
    doc = parse_thml_string(STANDARD_THML)
    content, _, _, _ = doc.chunks[0]
    assert "Great art Thou" in content
    assert "Thee would man praise" in content


def test_parse_thml_strips_xml_tags():
    thml = STANDARD_THML.replace('<p id="p1">', '<p id="p1"><i>Great</i> art Thou,')
    doc = parse_thml_string(thml)
    assert "<i>" not in doc.chunks[0][0]


def test_parse_thml_positions_sequential():
    doc = parse_thml_string(STANDARD_THML)
    positions = [c[2] for c in doc.chunks]
    assert positions == list(range(len(doc.chunks)))


def test_parse_thml_skips_short_chapters():
    short_thml = STANDARD_THML.replace(
        '<p id="p3">And how shall I call upon my God...</p>',
        '<p id="p3">Short.</p>'
    )
    doc = parse_thml_string(short_thml)
    refs = [c[1] for c in doc.chunks]
    assert not any("Chapter II" in r and "Book I" in r for r in refs)


def test_chunk_standard_falls_back_to_div1_when_no_div2():
    from ingest.common import parse_thml_string
    doc = parse_thml_string(_INCARNATION_THML)
    assert len(doc.chunks) == 2
    _, ref0, _, _ = doc.chunks[0]
    _, ref1, _, _ = doc.chunks[1]
    assert "Chapter 1" in ref0 or "Chapter I" in ref0
    assert "Chapter 2" in ref1 or "Chapter II" in ref1
    assert "Word of God" in doc.chunks[0][0]
```

Also add a new test for the content header format and metadata:

```python
def test_parse_thml_confessions_generic_title_format():
    doc = parse_thml_string(STANDARD_THML)
    content, _, _, meta = doc.chunks[0]
    # Confessions: generic chapter titles → [Book I, Chapter I] breadcrumb format
    assert content.startswith("[Book I, Chapter I]")
    assert "Great art Thou" in content
    assert meta is not None
    assert meta["div_depth"] == 2


def test_parse_thml_city_of_god_depth_adaptive():
    doc = parse_thml_string(_CITY_THML)
    assert len(doc.chunks) == 2  # two div3 chapters
    content, ref, _, meta = doc.chunks[0]
    assert "Augustine — City of God, Book I" in ref
    assert meta["div_depth"] == 3
    # Content header: [Book I] chapter title (not generic)
    assert content.startswith("[Book I]")


def test_parse_thml_multi_author_reference():
    doc = parse_thml_string(_MULTI_AUTHOR_THML)
    _, ref0, _, _ = doc.chunks[0]
    assert ref0.startswith("Clement Of Rome")
    assert "First Epistle of Clement to the Corinthians" in ref0


def test_parse_thml_summa_reference_format():
    doc = parse_thml_string(SUMMA_THML)
    _, ref0, _, _ = doc.chunks[0]
    assert "Article 1" in ref0
    assert "Question 1" in ref0


def test_parse_thml_summa_article_content_complete():
    doc = parse_thml_string(SUMMA_THML)
    content, _, _, _ = doc.chunks[0]
    assert "Objection 1" in content
    assert "I answer that" in content
    assert "Reply to Objection" in content
```

- [ ] **Step 2: Run tests — confirm failures**

```bash
cd datapipeline && python -m pytest tests/test_common.py -v
```
Expected: Several tests FAIL (old `_chunk_standard` returns old format)

- [ ] **Step 3: Replace `_chunk_standard` with depth-adaptive implementation**

In `datapipeline/ingest/common.py`, replace the entire `_chunk_standard` function and remove the old `_MIN_MERGE_CHARS`, `_MAX_SECTION_CHARS`, `_TARGET_CHUNK_CHARS` constants (now replaced by `_CEILING` and `_CF_SPLIT_TARGET` added in Task 3). Add these two helper functions first, then the main function:

```python
def _build_content_header(
    chunk_elem,
    ancestors: list,
    generic_titles: bool,
) -> str:
    """Return the [breadcrumb] header line for a chunk's content field."""
    if generic_titles:
        parts = [_parent_label(a) for a in ancestors if _parent_label(a)]
        chunk_lbl = _chunk_label(chunk_elem)
        if chunk_lbl:
            parts.append(chunk_lbl)
        return f"[{', '.join(parts)}]" if parts else ""
    else:
        parent = ancestors[-1] if ancestors else None
        parent_lbl = _parent_label(parent) if parent else ""
        chunk_title = (chunk_elem.get("title") or "").strip()[:120]
        return f"[{parent_lbl}] {chunk_title}" if parent_lbl else chunk_title


def _chunk_standard(root, doc: ThmlDocument, min_length: int = 100) -> list[tuple[str, str, int, dict | None]]:
    """Depth-adaptive chapter-level chunking with ancestry references."""
    parent_map = _build_parent_map(root)
    chunk_level = _detect_chunk_level(root)
    is_multi_author = _detect_is_multi_author(root)

    chunk_elems = [
        e for e in root.iter(f"div{chunk_level}")
        if (e.get("title") or "").strip().lower() not in _SKIP_TITLES
    ]

    # Detect generic chapter titles (e.g., Confessions: "Chapter I", "Chapter II")
    content_titles = [(e.get("title") or "").strip() for e in chunk_elems if (e.get("title") or "").strip()]
    generic_titles = bool(content_titles) and all(
        _GENERIC_CHAPTER_RE.match(t) for t in content_titles
    )

    head_elem = root.find(".//electronicEdInfo")
    author_id = (head_elem.findtext("authorID") if head_elem else "") or ""
    book_id = (head_elem.findtext("bookID") if head_elem else "") or ""

    chunks: list[tuple[str, str, int, dict | None]] = []
    position = 0

    for elem in chunk_elems:
        content_text = _extract_p_text(elem)
        if len(content_text) < min_length:
            continue

        # Collect ancestors root→parent
        ancestors: list = []
        current = parent_map.get(elem)
        while current is not None and current.tag.startswith("div"):
            ancestors.insert(0, current)
            current = parent_map.get(current)

        reference = _build_reference(doc, is_multi_author, elem, ancestors)
        header = _build_content_header(elem, ancestors, generic_titles)
        content = f"{header}\n\n{content_text}" if header else content_text

        parent = ancestors[-1] if ancestors else None
        metadata: dict = {
            "author_id": author_id,
            "book_id": book_id,
            "div_depth": chunk_level,
            "parent_shorttitle": _parent_label(parent) if parent else "",
            "chapter_title": (elem.get("title") or "").strip(),
        }

        if len(content) <= _CEILING:
            chunks.append((content, reference, position, metadata))
            position += 1
        else:
            parts = split_at_sentences(content_text, target=_CF_SPLIT_TARGET, overlap=_OVERLAP_CHARS)
            total = len(parts)
            for idx, part in enumerate(parts):
                part_content = f"{header}\n\n{part}" if header else part
                part_ref = f"{reference} ({idx + 1}/{total})" if total > 1 else reference
                chunks.append((part_content, part_ref, position, metadata))
                position += 1

    return chunks
```

- [ ] **Step 4: Update `parse_thml_string` to pass `doc` to `_chunk_standard`**

In `common.py`, update the `parse_thml_string` function:

```python
def parse_thml_string(xml_string: str) -> ThmlDocument:
    xml_string = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml_string, flags=re.DOTALL)
    root = ET.fromstring(xml_string)

    title = (root.findtext(".//DC.Title") or root.findtext(".//title") or "Unknown").strip()

    creator = ""
    for el in root.findall(".//DC.Creator"):
        if el.get("scheme") == "file-as":
            creator = (el.text or "").strip()
            break

    author: str | None = None
    year: int | None = None
    if creator:
        author, year = _parse_author(creator)

    # Partial doc for reference building (no chunks yet)
    partial_doc = ThmlDocument(title=title, author=author, year=year)

    if _is_summa(root):
        chunks = _chunk_summa(root)
    else:
        chunks = _chunk_standard(root, partial_doc)

    return ThmlDocument(title=title, author=author, year=year, chunks=chunks)
```

- [ ] **Step 5: Update `church_fathers.py` to inject `source_file` into metadata**

In `datapipeline/ingest/church_fathers.py`, update the chunk loop:

```python
for content, reference, position, meta in doc.chunks:
    chunk_meta = (meta or {}) | {"source_file": filename}
    await upsert_chunk(pool, doc_id, content, position, reference, metadata=chunk_meta)
```

- [ ] **Step 6: Run all common.py tests — verify they pass**

```bash
cd datapipeline && python -m pytest tests/test_common.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add datapipeline/ingest/common.py datapipeline/ingest/church_fathers.py datapipeline/tests/test_common.py
git commit -m "feat(common): depth-adaptive _chunk_standard — chapter-level chunking with ancestry references"
```

---

## Task 5: Encyclicals — Rewrite parse + chunk logic

**Files:**
- Modify: `datapipeline/ingest/encyclicals.py`
- Modify: `datapipeline/tests/test_encyclicals.py`

- [ ] **Step 1: Write failing tests first**

Replace the contents of `datapipeline/tests/test_encyclicals.py` entirely:

```python
import sys, os, re

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.encyclicals import parse_encyclical

# ── Fixtures ─────────────────────────────────────────────────────────────────

SIMPLE_HTML = """<html><body>
<p>To Our Venerable Brethren... greeting and Apostolic Blessing.</p>
<p>1. That the spirit of revolutionary change, which has long been disturbing the nations, should have passed beyond the sphere of politics and made its influence felt in the cognate sphere of practical economics.</p>
<p>2. It is not surprising that, with the growth of new industries settling in new lands, and with the surge of new economic forces, a spirit of strident controversy should have grown up as well.</p>
<p>3. To remedy these wrongs the socialists, working on the poor man's envy of the rich, are striving to do away with private property, and contend that individual possessions should become the common property of all.</p>
<p>4. But all agree, and there can be no question whatever, that some remedy must be found, and found quickly.</p>
<p>5. We approach the subject with confidence, and in the exercise of the rights which manifestly appertain to Us, We make no pretence to deal with the question from an economic point of view.</p>
</body></html>"""

SECTION_HTML = """<html><body>
<p>1. Opening paragraph of the encyclical document with substantial content here.</p>
<p>2. Second paragraph continues the theme and adds more substance to the opening.</p>
<p><b>I. The Rights of Workers</b></p>
<p>3. Every man has by nature the right to possess property as his own and to make use of it for this purpose.</p>
<p>4. It is a most sacred law of nature that a father should provide food and necessities for those whom he has begotten.</p>
<p><b>II. The Role of the State</b></p>
<p>5. The State should not absorb the individual or the family. It is an injustice and a grave evil.</p>
</body></html>"""

LONG_SECTION_HTML = """<html><body>
<p><b>I. Introduction</b></p>
""" + "\n".join(
    f"<p>{i}. {'This is a substantial paragraph with enough content to matter for chunking purposes. ' * 8}</p>"
    for i in range(1, 30)
) + """
</body></html>"""


# ── Basic extraction ─────────────────────────────────────────────────────────

def test_parse_encyclical_returns_chunks():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    assert len(chunks) >= 1


def test_parse_encyclical_chunk_is_4_tuple():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    content, ref, pos, meta = chunks[0]
    assert isinstance(content, str)
    assert isinstance(ref, str)
    assert isinstance(pos, int)
    assert isinstance(meta, dict)


def test_parse_encyclical_intro_chunk_at_position_0():
    """First chunk should be the overview chunk when a preamble or sections exist."""
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    content, ref, pos, _ = chunks[0]
    assert pos == 0
    assert "Rerum Novarum" in content
    assert "Overview" in ref


def test_parse_encyclical_intro_includes_preamble():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    content, _, _, _ = chunks[0]
    assert "Venerable Brethren" in content


def test_parse_encyclical_document_prefix_in_every_chunk():
    """Every non-intro chunk must begin with 'In {Title} ({Author}, {Year})'."""
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body_chunks = [(c, r, p, m) for c, r, p, m in chunks if "Overview" not in r]
    assert body_chunks, "Expected at least one body chunk"
    for content, _, _, _ in body_chunks:
        assert content.startswith("In Rerum Novarum (Pope Leo XIII, 1891)")


def test_parse_encyclical_reference_format():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    ref = body[0][1]
    assert ref.startswith("Rerum Novarum, §")


def test_parse_encyclical_positions_sequential():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    positions = [c[2] for c in chunks]
    assert positions == list(range(len(chunks)))


def test_parse_encyclical_metadata_fields():
    chunks = parse_encyclical(SIMPLE_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    _, _, _, meta = body[0]
    assert meta["year"] == 1891
    assert meta["pope"] == "Pope Leo XIII"
    assert "para_range" in meta
    assert "scripture_refs" in meta
    assert "section" in meta


# ── Section boundaries ───────────────────────────────────────────────────────

def test_parse_encyclical_section_flush():
    """A section header must flush the current chunk before starting a new one."""
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    refs = [c[1] for c in chunks]
    # §§1-2 and §§3-4 should be in separate chunks (section boundary between §2 and §3)
    body_refs = [r for r in refs if "Overview" not in r]
    assert len(body_refs) >= 2


def test_parse_encyclical_section_label_in_content():
    """When a section header is active, it appears in the chunk content."""
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    contents = [c[0] for c in body]
    assert any("Rights of Workers" in c for c in contents)


def test_parse_encyclical_section_in_metadata():
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    body = [c for c in chunks if "Overview" not in c[1]]
    metas = [c[3] for c in body]
    assert any(m["section"] and "Rights of Workers" in m["section"] for m in metas)


def test_parse_encyclical_intro_lists_sections():
    chunks = parse_encyclical(SECTION_HTML, "Rerum Novarum", "Pope Leo XIII", 1891)
    intro_content = chunks[0][0]
    assert "Rights of Workers" in intro_content or "Role of the State" in intro_content


# ── Overlap ─────────────────────────────────────────────────────────────────

def test_parse_encyclical_overlap_within_section():
    """When a long section produces multiple chunks, the last para of chunk N
    appears as the first para of chunk N+1 (within same section)."""
    chunks = parse_encyclical(LONG_SECTION_HTML, "Test Doc", "Pope Test", 2024)
    body = [c for c in chunks if "Overview" not in c[1]]
    if len(body) >= 2:
        c0, c1 = body[0][0], body[1][0]
        # Last meaningful paragraph of chunk 0 should appear in chunk 1
        last_para_of_c0 = [p for p in c0.split("\n\n") if p.strip()][-1]
        assert last_para_of_c0[:50] in c1


# ── Ceiling ──────────────────────────────────────────────────────────────────

def test_parse_encyclical_no_chunk_exceeds_ceiling():
    chunks = parse_encyclical(LONG_SECTION_HTML, "Test Doc", "Pope Test", 2024)
    for content, _, _, _ in chunks:
        assert len(content) <= 3500, f"Chunk exceeds 3500 chars: {len(content)}"
```

- [ ] **Step 2: Run tests — confirm failures**

```bash
cd datapipeline && python -m pytest tests/test_encyclicals.py -v
```
Expected: Most tests FAIL (old API: `parse_encyclical` doesn't exist yet)

- [ ] **Step 3: Replace encyclicals.py with new implementation**

Replace `datapipeline/ingest/encyclicals.py` entirely:

```python
from __future__ import annotations
import asyncio
import os
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document

_DELAY = 1.0
_MIN_LENGTH = 50
_TARGET = 1200
_CEILING = 3500

_SCRIPTURE_RE = re.compile(
    r'\b(?:[1-3]\s*[A-Z][a-z]+|[A-Z][a-z]+)\s+\d+:\d+(?:[–\-]\d+)?'
)

ENCYCLICALS: list[tuple[str, str, int, str]] = [
    ("Rerum Novarum",       "Pope Leo XIII",       1891, "https://www.papalencyclicals.net/leo13/l13rerum.htm"),
    ("Quadragesimo Anno",   "Pope Pius XI",        1931, "https://www.papalencyclicals.net/pius11/p11quadr.htm"),
    ("Humani Generis",      "Pope Pius XII",       1950, "https://www.papalencyclicals.net/pius12/p12human.htm"),
    ("Mater et Magistra",   "Pope John XXIII",     1961, "https://www.papalencyclicals.net/john23/j23mater.htm"),
    ("Pacem in Terris",     "Pope John XXIII",     1963, "https://www.papalencyclicals.net/john23/j23pacem.htm"),
    ("Humanae Vitae",       "Pope Paul VI",        1968, "https://www.papalencyclicals.net/paul06/p6humana.htm"),
    ("Evangelii Nuntiandi", "Pope Paul VI",        1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19751208_evangelii-nuntiandi.html"),
    ("Redemptor Hominis",   "Pope John Paul II",   1979, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_04031979_redemptor-hominis.html"),
    ("Laborem Exercens",    "Pope John Paul II",   1981, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091981_laborem-exercens.html"),
    ("Veritatis Splendor",  "Pope John Paul II",   1993, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_06081993_veritatis-splendor.html"),
    ("Evangelium Vitae",    "Pope John Paul II",   1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031995_evangelium-vitae.html"),
    ("Fides et Ratio",      "Pope John Paul II",   1998, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091998_fides-et-ratio.html"),
    ("Deus Caritas Est",    "Pope Benedict XVI",   2005, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20051225_deus-caritas-est_en.html"),
    ("Spe Salvi",           "Pope Benedict XVI",   2007, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20071130_spe-salvi_en.html"),
    ("Caritas in Veritate", "Pope Benedict XVI",   2009, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20090629_caritas-in-veritate_en.html"),
    ("Evangelii Gaudium",   "Pope Francis",        2013, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20131124_evangelii-gaudium.html"),
    ("Laudato Si",          "Pope Francis",        2015, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20150524_enciclica-laudato-si.html"),
    ("Magnifica Humanitas", "Pope Leo XIV",        2026, "https://www.vatican.va/content/leo-xiv/en/encyclicals/documents/20260515-magnifica-humanitas.html"),
]


def _detect_section_header(p_tag) -> str | None:
    """Return the section label if the <p> element is a section header; else None."""
    text = p_tag.get_text(strip=True)
    if not text or len(text) < 3:
        return None
    # Roman numeral pattern: "I. Title text" or "IV. Something"
    if re.match(r'^[IVX]+\.\s+\w', text):
        return text
    # Entire content is a single <b> or <strong> child with no surrounding text
    real_children = [c for c in p_tag.children if hasattr(c, 'name') and c.name is not None]
    bare_text = "".join(str(c) for c in p_tag.children if not hasattr(c, 'name')).strip()
    if (len(real_children) == 1
            and real_children[0].name in ('b', 'strong')
            and not bare_text):
        return text
    return None


def parse_encyclical(
    html: str,
    title: str,
    author: str,
    year: int,
) -> list[tuple[str, str, int, dict]]:
    """Parse an encyclical HTML page into chunks.

    Returns list of (content, reference, position, metadata).
    Position 0 is the intro/overview chunk when preamble or sections exist.
    """
    soup = BeautifulSoup(html, "lxml")

    # ── Pass 1: tokenise ─────────────────────────────────────────────────────
    # Token kinds: "preamble", "section", "para"
    tokens: list[dict] = []
    first_numbered = False
    all_sections: list[str] = []

    for p in soup.find_all("p"):
        section_label = _detect_section_header(p)
        if section_label:
            tokens.append({"kind": "section", "num": None, "text": section_label})
            all_sections.append(section_label)
            continue

        raw = p.get_text(separator=" ", strip=True)
        m = re.match(r"^(\d+)\.\s*(.+)", raw, re.DOTALL)
        if m:
            first_numbered = True
            num = int(m.group(1))
            body = m.group(2).strip()
            if len(body) >= _MIN_LENGTH:
                tokens.append({"kind": "para", "num": num, "text": body})
        elif not first_numbered and len(raw) >= _MIN_LENGTH:
            tokens.append({"kind": "preamble", "num": None, "text": raw})

    # ── Intro chunk ───────────────────────────────────────────────────────────
    chunks: list[tuple[str, str, int, dict]] = []
    position = 0

    preamble = "\n\n".join(t["text"] for t in tokens if t["kind"] == "preamble")[:600]
    sections_summary = ", ".join(all_sections)[:400]

    if preamble or sections_summary:
        lines = [f"{title} — {author}, {year}"]
        if preamble:
            lines.append(preamble)
        if sections_summary:
            lines.append(f"Sections: {sections_summary}")
        chunks.append((
            "\n\n".join(lines),
            f"{title} — Overview",
            0,
            {"section": None, "para_range": None, "scripture_refs": [], "year": year, "pope": author},
        ))
        position = 1

    # ── Pass 2: accumulate chunks ────────────────────────────────────────────
    prefix = f"In {title} ({author}, {year})"
    active_section: str | None = None
    acc: list[tuple[int, str]] = []   # (para_num, text); overlap uses num=-1
    acc_len = 0
    overlap_text: str | None = None

    def _build_chunk(section: str | None, paras: list[tuple[int, str]]) -> tuple[str, str, dict]:
        section_part = f", §{section}" if section else ""
        body = "\n\n".join(text for _, text in paras)
        content = f"{prefix}{section_part}:\n\n{body}"
        real = [(n, t) for n, t in paras if n != -1]
        first_num = real[0][0] if real else 0
        last_num = real[-1][0] if real else 0
        ref = (f"{title}, §§{first_num}–{last_num}"
               if first_num != last_num else f"{title}, §{first_num}")
        scripture_refs = list(dict.fromkeys(
            m for _, t in real for m in _SCRIPTURE_RE.findall(t)
        ))
        meta = {
            "section": section,
            "para_range": [first_num, last_num],
            "scripture_refs": scripture_refs,
            "year": year,
            "pope": author,
        }
        return content, ref, meta

    def flush() -> None:
        nonlocal position, overlap_text
        if not acc:
            return
        content, ref, meta = _build_chunk(active_section, acc)
        # Safety ceiling: single paragraph > 3500 chars edge case
        if len(content) <= _CEILING:
            chunks.append((content, ref, position, meta))
            position += 1
        else:
            # Balanced split at paragraph boundary nearest midpoint
            real = [(n, t) for n, t in acc if n != -1]
            total_len = sum(len(t) for _, t in real)
            running = 0
            split_at = max(1, len(real) // 2)
            for i, (_, t) in enumerate(real):
                running += len(t)
                if running >= total_len // 2:
                    split_at = i + 1
                    break
            for half in [real[:split_at], real[split_at:]]:
                if half:
                    c, r, m = _build_chunk(active_section, half)
                    chunks.append((c, r, position, m))
                    position += 1
        real_paras = [(n, t) for n, t in acc if n != -1]
        overlap_text = real_paras[-1][1] if real_paras else None

    for token in tokens:
        if token["kind"] == "preamble":
            continue

        if token["kind"] == "section":
            flush()
            active_section = token["text"]
            acc = []
            acc_len = 0
            overlap_text = None   # no overlap across section boundaries
            continue

        # "para" kind
        num, text = token["num"], token["text"]

        if acc_len + len(text) > _TARGET and acc:
            flush()
            acc = []
            acc_len = 0
            if overlap_text is not None:
                acc.append((-1, overlap_text))
                acc_len = len(overlap_text)

        acc.append((num, text))
        acc_len += len(text)

    flush()
    return chunks


async def main(pool) -> None:
    skipped: list[str] = []
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    ) as client:
        with tqdm(total=len(ENCYCLICALS), unit="doc", desc="Encyclicals") as pbar:
            for title, author, year, url in ENCYCLICALS:
                time.sleep(_DELAY)
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except Exception as exc:
                    print(f"\n  WARNING: Failed to fetch {title}: {exc}", file=sys.stderr)
                    skipped.append(title)
                    pbar.update(1)
                    continue

                chunks = parse_encyclical(resp.text, title, author, year)

                if not chunks:
                    print(f"\n  WARNING: No chunks extracted for {title}", file=sys.stderr)
                    skipped.append(title)
                    pbar.update(1)
                    continue

                doc_id = await upsert_document(
                    pool,
                    collection="encyclicals",
                    title=title,
                    translation="",
                    author=author,
                    year=year,
                    metadata={"url": url, "pope": author},
                )

                for content, reference, position, meta in chunks:
                    await upsert_chunk(
                        pool,
                        document_id=doc_id,
                        content=content,
                        position=position,
                        reference=reference,
                        metadata=meta,
                    )

                pbar.set_postfix({"doc": title, "chunks": len(chunks)})
                pbar.update(1)

    if skipped:
        print(f"\n  WARNING: {len(skipped)} documents failed: {skipped}", file=sys.stderr)
    print(f"  Done. {len(ENCYCLICALS) - len(skipped)} encyclicals written.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd datapipeline && python -m pytest tests/test_encyclicals.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add datapipeline/ingest/encyclicals.py datapipeline/tests/test_encyclicals.py
git commit -m "feat(encyclicals): section-boundary chunking with overlap, intro chunk, scripture metadata"
```

---

## Task 6: Canon Law — Hierarchy tracking in parser

**Files:**
- Modify: `datapipeline/ingest/canon_law.py`
- Modify: `datapipeline/tests/test_canon_law.py`

- [ ] **Step 1: Write failing tests for new parser behavior**

Add to `datapipeline/tests/test_canon_law.py`:

```python
from ingest.canon_law import parse_canon_page, deduplicate_urls

HIERARCHY_HTML = """<html><body><table><tbody><tr><td>
<p>BOOK II. THE PEOPLE OF GOD</p>
<p>TITLE I. THE OBLIGATIONS AND RIGHTS OF ALL THE CHRISTIAN FAITHFUL</p>
<p>Can. 208 In virtue of their rebirth in Christ, there exists among all the Christian faithful a true equality.</p>
<p>Can. 209 §1. The Christian faithful, even in their own manner of acting, are always obliged to maintain communion with the Church.</p>
<p>§2. With great diligence they are to lead a holy life.</p>
<p>CHAPTER I. OBLIGATIONS AND RIGHTS OF THE CHRISTIAN FAITHFUL</p>
<p>Can. 210 All the faithful must direct their efforts to lead a holy life.</p>
</td></tr></tbody></table></body></html>"""


def test_parse_canon_page_returns_3_tuple():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4
    num, text, ctx = canons[0]
    assert isinstance(num, int)
    assert isinstance(text, str)
    assert isinstance(ctx, dict)


def test_parse_canon_page_context_has_required_keys():
    canons = parse_canon_page(SAMPLE_HTML)
    _, _, ctx = canons[0]
    assert "book" in ctx
    assert "part" in ctx
    assert "title" in ctx
    assert "chapter" in ctx
    assert "article" in ctx


def test_parse_canon_header_updates_context():
    canons = parse_canon_page(HIERARCHY_HTML)
    # Can. 208 comes after BOOK II and TITLE I headers
    can208 = next(c for c in canons if c[0] == 208)
    ctx = can208[2]
    assert "BOOK II" in ctx["book"] or "THE PEOPLE OF GOD" in ctx["book"]
    assert "TITLE I" in ctx["title"] or "OBLIGATIONS" in ctx["title"]


def test_parse_canon_chapter_header_updates_chapter_context():
    canons = parse_canon_page(HIERARCHY_HTML)
    can210 = next(c for c in canons if c[0] == 210)
    ctx = can210[2]
    assert ctx["chapter"] != ""


def test_parse_canon_header_resets_lower_levels():
    """When a TITLE header appears, chapter and article must reset to ''."""
    canons = parse_canon_page(HIERARCHY_HTML)
    can208 = next(c for c in canons if c[0] == 208)
    ctx = can208[2]
    # At TITLE I level, chapter should be empty (reset when title changed)
    assert ctx["chapter"] == ""
    assert ctx["article"] == ""


def test_parse_canon_skips_headers():
    canons = parse_canon_page(SAMPLE_HTML)
    texts = [c[1] for c in canons]
    assert not any("CODE OF CANON LAW" in t for t in texts)


def test_parse_canon_page_extracts_canons():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4


def test_parse_canon_strips_can_prefix():
    canons = parse_canon_page(SAMPLE_HTML)
    num, text, _ = canons[0]
    assert num == 1
    assert not text.startswith("Can.")
    assert text.startswith("The canons")


def test_parse_canon_appends_subparagraphs():
    canons = parse_canon_page(SAMPLE_HTML)
    can5 = next(c for c in canons if c[0] == 5)
    assert "§1." in can5[1]
    assert "§2." in can5[1]


def test_parse_canon_appends_numbered_items():
    canons = parse_canon_page(SAMPLE_HTML)
    can6 = next(c for c in canons if c[0] == 6)
    assert "1/" in can6[1]
    assert "2/" in can6[1]


def test_deduplicate_urls_strips_fragments():
    urls = [
        "/archive/cic_lib1-cann1-6_en.html",
        "/archive/cic_lib1-cann1-6_en.html#Art._1.",
        "/archive/cic_lib1-cann7-22_en.html",
    ]
    result = deduplicate_urls(urls, base="http://www.vatican.va")
    assert len(result) == 2
```

- [ ] **Step 2: Run tests — confirm failures**

```bash
cd datapipeline && python -m pytest tests/test_canon_law.py -v
```
Expected: New 3-tuple tests FAIL; existing tests may also fail on unpack

- [ ] **Step 3: Update `parse_canon_page` to track hierarchy and return 3-tuples**

Replace the entire `parse_canon_page` function in `datapipeline/ingest/canon_law.py`:

```python
_LEVEL_ORDER = ["book", "part", "title", "chapter", "article"]

_HEADER_KEYWORDS: dict[str, str] = {
    "BOOK": "book",
    "PART": "part",
    "TITLE": "title",
    "CHAPTER": "chapter",
    "ARTICLE": "article",
    "SECTION": "chapter",
}

_ARTICLE_RE = re.compile(r"^ART\.\s*", re.IGNORECASE)


def _classify_header(text: str) -> str | None:
    """Return context key if text is a structural header; else None."""
    stripped = text.strip()
    if _ARTICLE_RE.match(stripped):
        return "article"
    upper = stripped.upper()
    for keyword, level in _HEADER_KEYWORDS.items():
        if upper.startswith(keyword + " ") or upper == keyword:
            return level
    # Fallback: short or ALL-CAPS text not starting with a digit
    if stripped.isupper() and len(stripped) > 3 and not stripped[0].isdigit():
        return "title"
    return None


def _reset_below(context: dict, level: str) -> None:
    """Clear all context levels lower than the given level."""
    idx = _LEVEL_ORDER.index(level)
    for key in _LEVEL_ORDER[idx + 1:]:
        context[key] = ""


def parse_canon_page(html: str) -> list[tuple[int, str, dict]]:
    """Parse a Vatican canon law HTML page.
    Returns list of (canon_number, full_text, context_snapshot) tuples.
    """
    soup = BeautifulSoup(html, "lxml")
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]

    canons: list[tuple[int, str, dict]] = []
    current_num: int | None = None
    current_parts: list[str] = []
    context: dict = {"book": "", "part": "", "title": "", "chapter": "", "article": ""}

    can_re = re.compile(r"^Can\.\s*(\d+)\s*(.*)", re.DOTALL)
    sub_re = re.compile(r"^§\d+\.")
    num_re = re.compile(r"^\d+/")

    def flush() -> None:
        if current_num is not None and current_parts:
            canons.append((current_num, "\n".join(current_parts), dict(context)))

    for text in paragraphs:
        if not text or len(text) < 3:
            continue

        m = can_re.match(text)
        if m:
            flush()
            current_num = int(m.group(1))
            body = m.group(2).strip()
            current_parts = [body] if body else []
            continue

        # Sub-paragraphs always attach to current canon
        if sub_re.match(text) or num_re.match(text):
            if current_num is not None:
                current_parts.append(text)
            continue

        # Check for hierarchy header
        header_level = _classify_header(text)
        if header_level:
            flush()
            current_num = None
            current_parts = []
            context[header_level] = text.strip()
            _reset_below(context, header_level)
            continue

        # Regular paragraph text
        if current_num is not None:
            current_parts.append(text)

    flush()
    return canons
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd datapipeline && python -m pytest tests/test_canon_law.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add datapipeline/ingest/canon_law.py datapipeline/tests/test_canon_law.py
git commit -m "feat(canon-law): hierarchy context tracking in parser — book/part/title/chapter/article"
```

---

## Task 7: Canon Law — Grouping, balanced split, and `main()` update

**Files:**
- Modify: `datapipeline/ingest/canon_law.py`
- Modify: `datapipeline/tests/test_canon_law.py`

- [ ] **Step 1: Write failing tests for grouping behavior**

Add to `datapipeline/tests/test_canon_law.py`:

```python
from ingest.canon_law import (
    parse_canon_page, deduplicate_urls,
    _context_key, _format_group_content, _build_canon_reference,
    _balanced_split_canons, _emit_group_chunks,
)


def test_context_key_includes_all_levels():
    ctx = {"book": "Book I", "part": "", "title": "Title I", "chapter": "Chapter I", "article": ""}
    key = _context_key(ctx)
    assert key == ("Book I", "", "Title I", "Chapter I", "")


def test_format_group_content_header_and_canons():
    ctx = {"book": "Book II", "part": "", "title": "Title I", "chapter": "", "article": ""}
    canons = [(208, "In virtue of their rebirth in Christ."), (209, "The faithful must act.")]
    content = _format_group_content(ctx, canons)
    assert "Book II" in content
    assert "Title I" in content
    assert "Can. 208:" in content
    assert "Can. 209:" in content


def test_format_group_content_omits_empty_levels():
    ctx = {"book": "Book I", "part": "", "title": "", "chapter": "", "article": ""}
    canons = [(1, "The canons regard only the Latin Church.")]
    content = _format_group_content(ctx, canons)
    assert "Book I" in content
    # No double dash or empty line from missing title
    assert " — \n" not in content


def test_build_canon_reference_multi_canon():
    ctx = {"book": "Book II", "part": "", "title": "Title I", "chapter": "", "article": ""}
    ref = _build_canon_reference(ctx, 208, 223)
    assert "Code of Canon Law" in ref
    assert "Book II" in ref
    assert "208" in ref
    assert "223" in ref


def test_build_canon_reference_single_canon():
    ctx = {"book": "Book I", "part": "", "title": "", "chapter": "", "article": ""}
    ref = _build_canon_reference(ctx, 1, 1)
    assert "Can. 1" in ref
    assert "Cann." not in ref


def test_balanced_split_canons_near_midpoint():
    canons = [(i, "x" * 100) for i in range(1, 11)]  # 10 canons, 100 chars each → 1000 total
    left, right = _balanced_split_canons(canons)
    # Split at ~500 chars → ~5 canons per half
    assert abs(len(left) - len(right)) <= 2


def test_emit_group_chunks_within_ceiling():
    ctx = {"book": "Book I", "part": "", "title": "Title I", "chapter": "", "article": ""}
    canons = [(1, "Short canon text."), (2, "Another short canon.")]
    chunks: list = []
    counter = [0]
    _emit_group_chunks(canons, ctx, chunks, counter)
    assert len(chunks) == 1
    content, ref, pos, meta = chunks[0]
    assert "Can. 1:" in content
    assert "Can. 2:" in content
    assert pos == 0
    assert meta["canon_range"] == [1, 2]


def test_emit_group_chunks_splits_at_ceiling():
    ctx = {"book": "Book I", "part": "", "title": "Title I", "chapter": "", "article": ""}
    # Create canons that together exceed 3500 chars
    big_text = "x " * 800  # ~1600 chars per canon
    canons = [(i, big_text) for i in range(1, 4)]
    chunks: list = []
    counter = [0]
    _emit_group_chunks(canons, ctx, chunks, counter, ceiling=3500)
    assert len(chunks) >= 2
    for content, _, _, _ in chunks:
        assert len(content) <= 3500


def test_emit_group_chunks_cross_refs_extracted():
    ctx = {"book": "Book I", "part": "", "title": "", "chapter": "", "article": ""}
    canons = [(1, "See can. 5 and can. 208 for details.")]
    chunks: list = []
    counter = [0]
    _emit_group_chunks(canons, ctx, chunks, counter)
    _, _, _, meta = chunks[0]
    assert 5 in meta["cross_refs"]
    assert 208 in meta["cross_refs"]
```

- [ ] **Step 2: Run tests — confirm failures**

```bash
cd datapipeline && python -m pytest tests/test_canon_law.py -v -k "context_key or format_group or build_canon or balanced_split or emit_group"
```
Expected: All new tests FAIL (functions don't exist yet)

- [ ] **Step 3: Add grouping helpers to `canon_law.py`**

Add these functions to `datapipeline/ingest/canon_law.py` after `_reset_below`:

```python
_CROSS_REF_RE = re.compile(r"can(?:on)?\.?\s*(\d+)", re.IGNORECASE)
_CANON_CEILING = 3500


def _context_key(ctx: dict) -> tuple:
    return (ctx["book"], ctx["part"], ctx["title"], ctx["chapter"], ctx["article"])


def _format_group_content(ctx: dict, canons: list[tuple[int, str]]) -> str:
    """Build the 2-line header + canon paragraphs content block."""
    top_parts = [p for p in [ctx["book"], ctx["title"]] if p]
    bottom_parts = [p for p in [ctx["chapter"], ctx["article"]] if p]
    header_lines = []
    if top_parts:
        header_lines.append(" — ".join(top_parts))
    if bottom_parts:
        header_lines.append(" — ".join(bottom_parts))
    header = "\n".join(header_lines)
    canon_strs = "\n\n".join(f"Can. {n}: {t}" for n, t in canons)
    return f"{header}\n\n{canon_strs}" if header else canon_strs


def _build_canon_reference(ctx: dict, first_num: int, last_num: int) -> str:
    location_parts = [p for p in [ctx["book"], ctx["title"]] if p]
    location = ", ".join(location_parts)
    base = "Code of Canon Law"
    if first_num == last_num:
        loc_str = f" — {location}" if location else ""
        return f"{base}{loc_str} (Can. {first_num})"
    loc_str = f" — {location}" if location else ""
    return f"{base}{loc_str} (Cann. {first_num}–{last_num})"


def _balanced_split_canons(
    canons: list[tuple[int, str]],
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Split canons at the boundary closest to the midpoint by total text length."""
    total = sum(len(t) for _, t in canons)
    running = 0
    best_idx = max(1, len(canons) // 2)
    best_diff = abs(total)
    for i, (_, t) in enumerate(canons):
        running += len(t)
        diff = abs(running - total // 2)
        if diff < best_diff:
            best_diff = diff
            best_idx = i + 1
    split = max(1, min(best_idx, len(canons) - 1))
    return canons[:split], canons[split:]


def _emit_group_chunks(
    canons: list[tuple[int, str]],
    ctx: dict,
    chunks: list,
    position_counter: list,
    ceiling: int = _CANON_CEILING,
) -> None:
    """Recursively emit one or more chunks for a canon group, splitting if needed."""
    content = _format_group_content(ctx, canons)
    if len(content) <= ceiling or len(canons) == 1:
        first_num, last_num = canons[0][0], canons[-1][0]
        ref = _build_canon_reference(ctx, first_num, last_num)
        cross_refs = list(dict.fromkeys(
            int(m)
            for _, t in canons
            for m in _CROSS_REF_RE.findall(t)
        ))
        meta = {
            "book": ctx.get("book", ""),
            "part": ctx.get("part", ""),
            "title": ctx.get("title", ""),
            "chapter": ctx.get("chapter", ""),
            "article": ctx.get("article", ""),
            "canon_range": [first_num, last_num],
            "cross_refs": cross_refs,
        }
        chunks.append((content, ref, position_counter[0], meta))
        position_counter[0] += 1
    else:
        left, right = _balanced_split_canons(canons)
        _emit_group_chunks(left, ctx, chunks, position_counter, ceiling)
        _emit_group_chunks(right, ctx, chunks, position_counter, ceiling)
```

- [ ] **Step 4: Update `main()` to use grouping**

Replace the deduplication and chunk-writing section in `main()` (from `seen_nums` through the final `for position, ...` loop):

```python
    # Deduplicate by canon number (some canons appear on multiple pages)
    seen_nums: set[int] = set()
    unique_canons: list[tuple[int, str, dict]] = []
    for num, text, ctx in sorted(all_canons, key=lambda x: x[0]):
        if num not in seen_nums:
            seen_nums.add(num)
            unique_canons.append((num, text, ctx))

    print(f"  Grouping {len(unique_canons)} unique canons...")

    # Group consecutive canons by hierarchy context
    groups: list[tuple[dict, list[tuple[int, str]]]] = []
    current_key: tuple | None = None
    current_ctx: dict = {}
    current_group: list[tuple[int, str]] = []

    for num, text, ctx in unique_canons:
        key = _context_key(ctx)
        if key != current_key:
            if current_group:
                groups.append((current_ctx, current_group))
            current_key = key
            current_ctx = ctx
            current_group = [(num, text)]
        else:
            current_group.append((num, text))

    if current_group:
        groups.append((current_ctx, current_group))

    print(f"  Emitting {len(groups)} canon groups...")
    all_chunks: list[tuple[str, str, int, dict]] = []
    position_counter = [0]
    for ctx, canons in groups:
        _emit_group_chunks(canons, ctx, all_chunks, position_counter)

    for content, ref, position, meta in all_chunks:
        await upsert_chunk(
            pool,
            document_id=doc_id,
            content=content,
            position=position,
            reference=ref,
            metadata=meta,
        )
```

Also update the scraping loop to collect 3-tuples:

```python
        all_canons: list[tuple[int, str, dict]] = []
        ...
                    canons = parse_canon_page(r.text)
                    all_canons.extend(canons)
```

- [ ] **Step 5: Run all canon law tests — verify they pass**

```bash
cd datapipeline && python -m pytest tests/test_canon_law.py -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/canon_law.py datapipeline/tests/test_canon_law.py
git commit -m "feat(canon-law): article-level grouping with balanced split and cross-ref metadata"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
cd datapipeline && python -m pytest tests/ -v
cd services/api && python -m pytest tests/ -v
```
Expected: All tests PASS across both suites

- [ ] **Commit if clean**

```bash
git add -A
git status  # verify nothing unexpected
git commit -m "chore: final test sweep — all suites green after chunking redesign" --allow-empty
```

---

## Self-Review Notes

**Spec coverage verified:**
- Reranker truncation fix ✓ (Task 1)
- Church Fathers depth-adaptive level detection ✓ (Task 3+4)
- Church Fathers ancestry reference + shorttitle breadcrumb ✓ (Task 3+4)
- Confessions/generic-title exception ✓ (Task 4, `generic_titles` flag)
- incarnation.xml special case ✓ (Task 3, `type="chapter"` detection)
- Church Fathers skip list ✓ (Task 3, `_SKIP_TITLES`)
- Church Fathers 3500-char ceiling + 1800-char split target ✓ (Task 4)
- Church Fathers chunk metadata ✓ (Task 4)
- Encyclicals section-boundary detection ✓ (Task 5, `_detect_section_header`)
- Encyclicals variable window with 1200-char target ✓ (Task 5)
- Encyclicals leading overlap within section ✓ (Task 5)
- Encyclicals intro chunk at position 0 ✓ (Task 5)
- Encyclicals scripture ref metadata ✓ (Task 5, `_SCRIPTURE_RE`)
- Encyclicals content format with document prefix ✓ (Task 5)
- Canon Law hierarchy tracking ✓ (Task 6)
- Canon Law article-level grouping with `part` included in key ✓ (Task 7)
- Canon Law balanced split at ceiling ✓ (Task 7, `_balanced_split_canons`)
- Canon Law content format with 2-line header ✓ (Task 7)
- Canon Law cross-ref metadata ✓ (Task 7, `_CROSS_REF_RE`)
- Tests updated for all three sources ✓ (Tasks 2, 4, 5, 6, 7)
