# Datapipeline Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all six collection ingest scripts, embed.py, and run_all.py so that `python run_all.py` fully populates documents, chunks, and content_embedding for all collections.

**Architecture:** Independent scripts (Approach A) — each `ingest/*.py` reads its source, parses to documents+chunks, calls `load.py` helpers. Shared ThML parsing lives in `ingest/common.py`. `embed.py` batch-embeds all NULL chunks after ingest. `run_all.py` sequences everything.

**Tech Stack:** Python 3.12, asyncpg, httpx, beautifulsoup4+lxml, openai, tqdm, pytest

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `datapipeline/ingest/common.py` | CREATE | ThML XML parser — metadata + chapter/article chunking |
| `datapipeline/ingest/bible.py` | REWRITE | Read CPDV from JSON + DR from local text file |
| `datapipeline/ingest/catechism.py` | CREATE | Parse ccc.json page_nodes |
| `datapipeline/ingest/canon_law.py` | CREATE | Scrape Vatican HTML, state-machine canon parser |
| `datapipeline/ingest/encyclicals.py` | CREATE | Scrape 18 hardcoded URLs, paragraph grouping |
| `datapipeline/ingest/church_fathers.py` | CREATE | Walk sources/church-fathers/*.xml via common.py |
| `datapipeline/ingest/saints.py` | CREATE | Scrape New Advent CE A-Z, filter saint articles |
| `datapipeline/embed.py` | CREATE | Batch embed all chunks where content_embedding IS NULL |
| `datapipeline/run_all.py` | CREATE | Sequence all scripts, timing, --collection flag |
| `datapipeline/tests/test_bible.py` | CREATE | Unit tests for CPDV parser + chunking |
| `datapipeline/tests/test_catechism.py` | CREATE | Unit tests for CCC paragraph parser |
| `datapipeline/tests/test_common.py` | CREATE | Unit tests for ThML parser (standard + Summa) |
| `datapipeline/tests/test_canon_law.py` | CREATE | Unit tests for canon state machine + URL dedup |
| `datapipeline/tests/test_encyclicals.py` | CREATE | Unit tests for encyclical paragraph grouping |
| `datapipeline/tests/test_saints.py` | CREATE | Unit tests for saint link filtering + chunking |
| `datapipeline/requirements.txt` | MODIFY | Add pytest>=8.0.0 |

---

## Task 1: Test infrastructure

**Files:**
- Modify: `datapipeline/requirements.txt`
- Create: `datapipeline/tests/__init__.py`
- Create: `datapipeline/tests/conftest.py`

- [ ] **Add pytest to requirements**

```
# datapipeline/requirements.txt — append:
pytest>=8.0.0
pytest-asyncio>=0.23.0
defusedxml>=0.7.1
```

- [ ] **Create tests package**

```bash
mkdir -p /home/carter/repos/body-of-christ/datapipeline/tests
touch /home/carter/repos/body-of-christ/datapipeline/tests/__init__.py
```

- [ ] **Create conftest.py**

```python
# datapipeline/tests/conftest.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Install deps and verify pytest works**

```bash
cd datapipeline
pip install -r requirements.txt
pytest tests/ -v
# Expected: "no tests ran" or similar — no errors
```

- [ ] **Commit**

```bash
git add datapipeline/requirements.txt datapipeline/tests/
git commit -m "test(datapipeline): add pytest infrastructure"
```

---

## Task 2: bible.py — CPDV JSON parser (TDD)

**Files:**
- Create: `datapipeline/tests/test_bible.py`
- Modify: `datapipeline/ingest/bible.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_bible.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.bible import parse_cpdv_json, chunk_book, _make_reference, BookVerses, Verse

def test_parse_cpdv_extracts_books():
    data = {
        "charset": "UTF-8",
        "Genesis": {"1": {"1": "In the beginning", "2": "The earth was empty"}},
        "Exodus": {"1": {"1": "These are the names"}},
    }
    books = parse_cpdv_json(data)
    assert len(books) == 2
    assert books[0].name == "Genesis"
    assert books[1].name == "Exodus"

def test_parse_cpdv_skips_charset_key():
    data = {"charset": "UTF-8", "Genesis": {"1": {"1": "text"}}}
    books = parse_cpdv_json(data)
    assert len(books) == 1

def test_parse_cpdv_extracts_verses():
    data = {"Genesis": {"1": {"1": "verse one", "2": "verse two", "3": "verse three"}}}
    books = parse_cpdv_json(data)
    assert len(books[0].verses) == 3
    assert books[0].verses[0].text == "verse one"
    assert books[0].verses[0].chapter == 1
    assert books[0].verses[0].verse == 1

def test_parse_cpdv_assigns_testament():
    data = {"Genesis": {"1": {"1": "text"}}, "Matthew": {"1": {"1": "text"}}}
    books = parse_cpdv_json(data)
    by_name = {b.name: b for b in books}
    assert by_name["Genesis"].testament == "OT"
    assert by_name["Matthew"].testament == "NT"

def test_parse_cpdv_skips_unknown_books():
    data = {"UnknownBook": {"1": {"1": "text"}}, "Genesis": {"1": {"1": "text"}}}
    books = parse_cpdv_json(data)
    assert len(books) == 1
    assert books[0].name == "Genesis"

def test_chunk_book_groups_four_verses():
    verses = [Verse("Genesis", 1, i, f"Verse {i} text here") for i in range(1, 9)]
    book = BookVerses("Genesis", "", "OT", verses)
    chunks = list(chunk_book(book, 4, 10))
    assert len(chunks) == 2
    content0, ref0, pos0 = chunks[0]
    assert ref0 == "Genesis 1:1-4"
    assert pos0 == 0
    assert "Verse 1" in content0

def test_chunk_book_never_crosses_chapters():
    ch1 = [Verse("Gen", 1, i, f"ch1 v{i}") for i in range(1, 4)]
    ch2 = [Verse("Gen", 2, i, f"ch2 v{i}") for i in range(1, 4)]
    book = BookVerses("Gen", "", "OT", ch1 + ch2)
    chunks = list(chunk_book(book, 4, 5))
    refs = [c[1] for c in chunks]
    assert all("1:" not in r or "2:" not in r for r in refs)

def test_chunk_book_skips_short_content():
    verses = [Verse("Gen", 1, 1, "hi")]
    book = BookVerses("Gen", "", "OT", verses)
    chunks = list(chunk_book(book, 4, 50))
    assert len(chunks) == 0
```

- [ ] **Run tests to confirm failure**

```bash
cd datapipeline
pytest tests/test_bible.py -v
# Expected: ImportError or AttributeError — parse_cpdv_json not yet defined
```

- [ ] **Add `parse_cpdv_json` to bible.py**

In `datapipeline/ingest/bible.py`, replace the `ingest_cpdv()` function (which downloaded from eBible) with a disk-based reader. Keep all existing dataclasses (`Verse`, `BookVerses`), `chunk_book()`, `_make_reference()`, `_ingest_books()`, `_verify_deuterocanonicals()`, and `DR_PG_BOOK_NAME_MAP`. Remove `parse_usfm_book()`, `_clean_usfm_text()`, `_download()`, and `USFM_BOOK_MAP` (keep the dict values for testament lookup — see below).

Add this function:

```python
# Add near top of bible.py after imports:
_BOOK_TESTAMENT: dict[str, str] = {
    # OT protocanonical
    "Genesis": "OT", "Exodus": "OT", "Leviticus": "OT", "Numbers": "OT",
    "Deuteronomy": "OT", "Joshua": "OT", "Judges": "OT", "Ruth": "OT",
    "1 Samuel": "OT", "2 Samuel": "OT", "1 Kings": "OT", "2 Kings": "OT",
    "1 Chronicles": "OT", "2 Chronicles": "OT", "Ezra": "OT", "Nehemiah": "OT",
    "Esther": "OT", "Job": "OT", "Psalms": "OT", "Proverbs": "OT",
    "Ecclesiastes": "OT", "Song of Solomon": "OT", "Isaiah": "OT",
    "Jeremiah": "OT", "Lamentations": "OT", "Ezekiel": "OT", "Daniel": "OT",
    "Hosea": "OT", "Joel": "OT", "Amos": "OT", "Obadiah": "OT",
    "Jonah": "OT", "Micah": "OT", "Nahum": "OT", "Habakkuk": "OT",
    "Zephaniah": "OT", "Haggai": "OT", "Zechariah": "OT", "Malachi": "OT",
    # OT deuterocanonical
    "Tobit": "OT", "Judith": "OT", "1 Maccabees": "OT", "2 Maccabees": "OT",
    "Wisdom": "OT", "Sirach": "OT", "Baruch": "OT",
    # NT
    "Matthew": "NT", "Mark": "NT", "Luke": "NT", "John": "NT", "Acts": "NT",
    "Romans": "NT", "1 Corinthians": "NT", "2 Corinthians": "NT",
    "Galatians": "NT", "Ephesians": "NT", "Philippians": "NT",
    "Colossians": "NT", "1 Thessalonians": "NT", "2 Thessalonians": "NT",
    "1 Timothy": "NT", "2 Timothy": "NT", "Titus": "NT", "Philemon": "NT",
    "Hebrews": "NT", "James": "NT", "1 Peter": "NT", "2 Peter": "NT",
    "1 John": "NT", "2 John": "NT", "3 John": "NT", "Jude": "NT",
    "Revelation": "NT",
}


def parse_cpdv_json(data: dict) -> list[BookVerses]:
    """Parse the CPDV JSON structure {book: {chapter: {verse: text}}} into BookVerses."""
    books: list[BookVerses] = []
    for book_name, chapters in data.items():
        if book_name == "charset":
            continue
        testament = _BOOK_TESTAMENT.get(book_name)
        if testament is None:
            continue
        verses: list[Verse] = []
        for ch_str, verse_dict in chapters.items():
            ch = int(ch_str)
            for v_str, text in verse_dict.items():
                verses.append(Verse(book_name, ch, int(v_str), text))
        books.append(BookVerses(name=book_name, book_code="", testament=testament, verses=verses))
    return books
```

Replace `ingest_cpdv()` with a disk-reading version:

```python
async def ingest_cpdv(pool) -> None:
    """Read CPDV from sources/bible/cpdv.json and ingest."""
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "bible", "cpdv.json")
    print(f"Reading CPDV from {src}...")
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    books = parse_cpdv_json(data)
    print(f"  Found {len(books)} books in CPDV JSON.")
    _verify_deuterocanonicals(books, "CPDV")
    await _ingest_books(pool, books, translation="CPDV")
```

Add `import json` and `import os` at the top if not present.

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_bible.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible.py
git commit -m "feat(datapipeline): rewrite CPDV ingest to read from local JSON"
```

---

## Task 3: bible.py — Douay-Rheims local file path

- [ ] **Add DR disk-read test**

Add to `datapipeline/tests/test_bible.py`:

```python
import tempfile, json, os

def test_read_dr_from_local_file():
    """ingest_douay_rheims_from_file should call parse_douay_rheims on local content."""
    from ingest.bible import parse_douay_rheims
    # Minimal DR-format text with one chapter header and one verse
    sample = (
        "*** START OF THIS PROJECT GUTENBERG EBOOK ***\n"
        "Genesis Chapter 1\n"
        "\n"
        "1:1. In the beginning God created heaven and earth.\n"
        "\n"
        "*** END OF THIS PROJECT GUTENBERG EBOOK ***\n"
    )
    books = parse_douay_rheims(sample)
    assert len(books) == 1
    assert books[0].name == "Genesis"
    assert books[0].verses[0].text == "In the beginning God created heaven and earth."
```

- [ ] **Run test to confirm it passes** (parse_douay_rheims already exists and handles this format)

```bash
pytest tests/test_bible.py::test_read_dr_from_local_file -v
# Expected: PASS — function already works
```

- [ ] **Replace DR download call with local file read in bible.py**

Replace the `ingest_douay_rheims()` function body:

```python
async def ingest_douay_rheims(pool) -> None:
    """Read Douay-Rheims from sources/bible/gutenberg-bible.txt and ingest."""
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "bible", "gutenberg-bible.txt")
    print(f"Reading Douay-Rheims from {src}...")
    with open(src, encoding="utf-8", errors="replace") as f:
        text = f.read()
    books = parse_douay_rheims(text)
    print(f"  Found {len(books)} books in Douay-Rheims text.")
    if len(books) < 60:
        print(f"  WARNING: Expected ~73 books but only found {len(books)}.", file=sys.stderr)
    _verify_deuterocanonicals(books, "Douay-Rheims")
    await _ingest_books(pool, books, translation="douay-rheims")
```

Remove the `CPDV_URL` and `DOUAY_RHEIMS_URL` constants and the `httpx` import if no longer used. Keep `sys` import.

- [ ] **Run all bible tests**

```bash
pytest tests/test_bible.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible.py
git commit -m "feat(datapipeline): read Douay-Rheims from local file instead of downloading"
```

---

## Task 4: catechism.py (TDD)

**Files:**
- Create: `datapipeline/tests/test_catechism.py`
- Create: `datapipeline/ingest/catechism.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_catechism.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.catechism import parse_ccc_paragraphs

SAMPLE_DATA = {
    "page_nodes": {
        "toc-1": {
            "paragraphs": [
                {
                    "elements": [
                        {"type": "ref-ccc", "ref_number": 1},
                        {"type": "text", "text": "God, infinitely perfect and blessed in himself, in a plan of sheer goodness freely created man."},
                        {"type": "ref", "number": 1},
                    ]
                },
                {
                    "elements": [
                        {"type": "ref-ccc", "ref_number": 2},
                        {"type": "text", "text": "The Father willed that his eternal Son should become man and save all men from sin."},
                    ]
                },
            ]
        },
        "toc-2": {
            "paragraphs": [
                {
                    "elements": [
                        {"type": "text", "text": "Section title with no paragraph number"}
                    ]
                },
                {
                    "elements": [
                        {"type": "ref-ccc", "ref_number": 3},
                        {"type": "text", "text": "Short."},
                    ]
                },
            ]
        },
    }
}

def test_parse_ccc_extracts_paragraphs():
    paras = parse_ccc_paragraphs(SAMPLE_DATA)
    assert len(paras) == 2  # §3 too short, no-ref-ccc skipped

def test_parse_ccc_correct_ref_number():
    paras = parse_ccc_paragraphs(SAMPLE_DATA)
    assert paras[0][0] == 1
    assert paras[1][0] == 2

def test_parse_ccc_concatenates_text_elements():
    data = {
        "page_nodes": {"t": {"paragraphs": [{
            "elements": [
                {"type": "ref-ccc", "ref_number": 10},
                {"type": "text", "text": "First part. "},
                {"type": "ref", "number": 5},
                {"type": "text", "text": "Second part."},
            ]
        }]}}
    }
    paras = parse_ccc_paragraphs(data)
    assert paras[0][1] == "First part.  Second part."

def test_parse_ccc_skips_no_ref_ccc():
    paras = parse_ccc_paragraphs(SAMPLE_DATA)
    para_nums = [p[0] for p in paras]
    assert 3 not in para_nums  # §3 too short
    # No para for the section-title-only node

def test_parse_ccc_sorted_by_para_num():
    data = {
        "page_nodes": {
            "b": {"paragraphs": [{"elements": [{"type": "ref-ccc", "ref_number": 20}, {"type": "text", "text": "x" * 40}]}]},
            "a": {"paragraphs": [{"elements": [{"type": "ref-ccc", "ref_number": 5}, {"type": "text", "text": "x" * 40}]}]},
        }
    }
    paras = parse_ccc_paragraphs(data)
    assert paras[0][0] == 5
    assert paras[1][0] == 20
```

- [ ] **Run tests to confirm failure**

```bash
pytest tests/test_catechism.py -v
# Expected: ImportError — catechism.py not yet created
```

- [ ] **Implement catechism.py**

```python
# datapipeline/ingest/catechism.py
from __future__ import annotations
import asyncio
import json
import os
import sys
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document

_MIN_LENGTH = 30
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "catechism", "ccc.json")


def parse_ccc_paragraphs(data: dict) -> list[tuple[int, str]]:
    """Return sorted list of (para_num, content) from the ccc.json page_nodes structure."""
    result: list[tuple[int, str]] = []
    for node in data.get("page_nodes", {}).values():
        for para in node.get("paragraphs", []):
            elements = para.get("elements", [])
            ref_num: int | None = None
            text_parts: list[str] = []
            for el in elements:
                if el.get("type") == "ref-ccc":
                    ref_num = el.get("ref_number")
                elif el.get("type") == "text":
                    text_parts.append(el.get("text", ""))
            if ref_num is None:
                continue
            content = " ".join(text_parts).strip()
            if len(content) < _MIN_LENGTH:
                continue
            result.append((ref_num, content))
    result.sort(key=lambda x: x[0])
    return result


async def main(pool) -> None:
    print("Reading CCC JSON...")
    with open(_SRC, encoding="utf-8") as f:
        data = json.load(f)

    paragraphs = parse_ccc_paragraphs(data)
    print(f"  Found {len(paragraphs)} CCC paragraphs.")

    doc_id = await upsert_document(
        pool,
        collection="catechism",
        title="Catechism of the Catholic Church",
        translation="",
        author="Catholic Church",
        year=1992,
        metadata={"source": "nossbigg/catechism-ccc-json"},
    )

    with tqdm(total=len(paragraphs), unit="para", desc="Catechism") as pbar:
        for position, (para_num, content) in enumerate(paragraphs):
            await upsert_chunk(
                pool,
                document_id=doc_id,
                content=content,
                position=position,
                reference=f"CCC §{para_num}",
            )
            pbar.update(1)

    print(f"  Done. {len(paragraphs)} chunks written for catechism.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_catechism.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/catechism.py datapipeline/tests/test_catechism.py
git commit -m "feat(datapipeline): add catechism ingest script"
```

---

## Task 5: common.py — ThML parser (TDD)

**Files:**
- Create: `datapipeline/tests/test_common.py`
- Create: `datapipeline/ingest/common.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_common.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.common import parse_thml_string, ThmlDocument

STANDARD_THML = """<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo>
      <authorID>augustine</authorID>
      <bookID>confess</bookID>
    </electronicEdInfo>
    <DC>
      <DC.Title>The Confessions of Saint Augustine</DC.Title>
      <DC.Creator sub="Author" scheme="file-as">Augustine, Saint, Bishop of Hippo (345-430)</DC.Creator>
    </DC>
  </ThML.head>
  <ThML.body>
    <div1 title="Book I" n="i" id="bk1">
      <div2 title="Chapter I" n="i" id="bk1.ch1">
        <p id="p1">Great art Thou, O Lord, and greatly to be praised; great is Thy power, and Thy wisdom infinite. And Thee would man praise; man, but a particle of Thy creation.</p>
        <p id="p2">And Thee would man praise; he, but a particle of Thy creation. Thou awakest us to delight in Thy praise.</p>
      </div2>
      <div2 title="Chapter II" n="ii" id="bk1.ch2">
        <p id="p3">And how shall I call upon my God, my God and Lord, since, when I call for Him, I shall be calling Him to myself? and what room is there within me, whither my God can come into me?</p>
      </div2>
    </div1>
    <div1 title="Book II" n="ii" id="bk2">
      <div2 title="Chapter I" n="i" id="bk2.ch1">
        <p id="p4">I will now call to mind my past foulness, and the carnal corruptions of my soul; not because I love them, but that I may love Thee, O my God.</p>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

SUMMA_THML = """<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo>
      <authorID>aquinas</authorID>
      <bookID>summa</bookID>
    </electronicEdInfo>
    <DC>
      <DC.Title>Summa Theologica</DC.Title>
      <DC.Creator sub="Author" scheme="file-as">Thomas Aquinas, Saint (1225?-1274)</DC.Creator>
    </DC>
  </ThML.head>
  <ThML.body>
    <div1 title="First Part" n="i" id="FP">
      <div2 title="Treatise on Sacred Doctrine" n="i" id="FP.i">
        <div3 title="Question 1" n="i" id="FP_Q1">
          <div4 title="Article 1 - Whether sacred doctrine is necessary?" n="i" id="FP_Q1_A1">
            <p id="a1p1">Objection 1: It seems that it is not necessary.</p>
            <p id="a1p2">On the contrary, It is written: "Instruction in every gracious art."</p>
            <p id="a1p3">I answer that, It was necessary for man's salvation that there should be a knowledge revealed by God.</p>
            <p id="a1p4">Reply to Objection 1: Sciences are differentiated according to the various means through which knowledge is obtained.</p>
          </div4>
          <div4 title="Article 2 - Whether sacred doctrine is a science?" n="ii" id="FP_Q1_A2">
            <p id="a2p1">Objection 1: It seems that sacred doctrine is not a science.</p>
            <p id="a2p2">I answer that, Sacred doctrine is a science because it proceeds from principles established by the light of a higher science.</p>
          </div4>
        </div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""


def test_parse_thml_title():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.title == "The Confessions of Saint Augustine"

def test_parse_thml_author_cleaned():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.author == "Augustine, Saint, Bishop of Hippo"

def test_parse_thml_year_from_death():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.year == 430

def test_parse_thml_standard_chunks_by_chapter():
    doc = parse_thml_string(STANDARD_THML)
    assert len(doc.chunks) == 3  # Book I Ch I, Book I Ch II, Book II Ch I

def test_parse_thml_chapter_content_joined():
    doc = parse_thml_string(STANDARD_THML)
    content, ref, pos = doc.chunks[0]
    assert "Great art Thou" in content
    assert "Thee would man praise" in content  # both paragraphs merged

def test_parse_thml_reference_format():
    doc = parse_thml_string(STANDARD_THML)
    _, ref0, _ = doc.chunks[0]
    _, ref1, _ = doc.chunks[1]
    assert ref0 == "Book I, Chapter I"
    assert ref1 == "Book I, Chapter II"

def test_parse_thml_positions_sequential():
    doc = parse_thml_string(STANDARD_THML)
    positions = [c[2] for c in doc.chunks]
    assert positions == list(range(len(doc.chunks)))

def test_parse_thml_strips_xml_tags():
    thml = STANDARD_THML.replace("<p id=\"p1\">", "<p id=\"p1\"><i>Great</i> art Thou,")
    doc = parse_thml_string(thml)
    assert "<i>" not in doc.chunks[0][0]

def test_parse_thml_summa_chunks_at_article():
    doc = parse_thml_string(SUMMA_THML)
    assert len(doc.chunks) == 2  # 2 articles

def test_parse_thml_summa_reference_format():
    doc = parse_thml_string(SUMMA_THML)
    _, ref0, _ = doc.chunks[0]
    assert "Article 1" in ref0
    assert "Question 1" in ref0

def test_parse_thml_summa_article_content_complete():
    doc = parse_thml_string(SUMMA_THML)
    content, _, _ = doc.chunks[0]
    assert "Objection 1" in content
    assert "I answer that" in content
    assert "Reply to Objection" in content

def test_parse_thml_skips_short_chunks():
    thml = STANDARD_THML.replace(
        "<p id=\"p3\">And how shall I call upon my God",
        "<p id=\"p3\">Short."
    )
    doc = parse_thml_string(thml)
    refs = [c[1] for c in doc.chunks]
    assert "Book I, Chapter II" not in refs
```

- [ ] **Run tests to confirm failure**

```bash
pytest tests/test_common.py -v
# Expected: ImportError
```

- [ ] **Implement common.py**

```python
# datapipeline/ingest/common.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import tostring as et_tostring  # serialization only — no parsing
import defusedxml.ElementTree as ET  # safe parsing: blocks XXE and billion-laughs attacks


@dataclass
class ThmlDocument:
    title: str
    author: str | None
    year: int | None
    chunks: list[tuple[str, str, int]] = field(default_factory=list)  # (content, reference, position)


def _strip_tags(text: str) -> str:
    """Remove XML/HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return " ".join(text.split())


def _extract_text(elem: ET.Element) -> str:
    """Get all text content from an element and its children, stripped."""
    return _strip_tags(et_tostring(elem, encoding="unicode", method="xml"))


def _parse_author(creator: str) -> tuple[str, int | None]:
    """
    Parse 'Augustine, Saint, Bishop of Hippo (345-430)' into
    ('Augustine, Saint, Bishop of Hippo', 430).
    """
    m = re.search(r"\((\d{3,4}\??)-(\d{3,4})\)\s*$", creator)
    year: int | None = None
    if m:
        try:
            year = int(m.group(2))
        except ValueError:
            pass
        creator = creator[: m.start()].strip().rstrip(",").strip()
    return creator, year


def _is_summa(root: ET.Element) -> bool:
    head = root.find(".//electronicEdInfo")
    if head is None:
        return False
    author_id = head.findtext("authorID", "")
    book_id = head.findtext("bookID", "")
    return author_id == "aquinas" and book_id == "summa"


def _extract_p_text(elem: ET.Element) -> str:
    """Concatenate text from all <p> children of elem."""
    parts = []
    for p in elem.iter("p"):
        t = _strip_tags(ET.tostring(p, encoding="unicode", method="xml"))
        if t:
            parts.append(t)
    return " ".join(parts)


def _chunk_standard(root: ET.Element, min_length: int = 100) -> list[tuple[str, str, int]]:
    """Chunk at div2 (chapter) level: one chunk per chapter."""
    chunks: list[tuple[str, str, int]] = []
    position = 0
    for div1 in root.iter("div1"):
        div1_title = div1.get("title", "").strip()
        for div2 in div1:
            if not div2.tag.startswith("div2"):
                continue
            div2_title = div2.get("title", "").strip()
            content = _extract_p_text(div2)
            if len(content) < min_length:
                continue
            reference = f"{div1_title}, {div2_title}" if div1_title else div2_title
            chunks.append((content, reference, position))
            position += 1
    return chunks


def _chunk_summa(root: ET.Element, min_length: int = 50) -> list[tuple[str, str, int]]:
    """Chunk at div4 (Article) level for the Summa."""
    chunks: list[tuple[str, str, int]] = []
    position = 0
    for div1 in root.iter("div1"):
        for div2 in div1:
            if not div2.tag.startswith("div2"):
                continue
            for div3 in div2:
                if not div3.tag.startswith("div3"):
                    continue
                div3_title = div3.get("title", "").strip()
                for div4 in div3:
                    if not div4.tag.startswith("div4"):
                        continue
                    div4_title = div4.get("title", "").strip()
                    content = _extract_p_text(div4)
                    if len(content) < min_length:
                        continue
                    reference = f"{div3_title}, {div4_title}" if div3_title else div4_title
                    chunks.append((content, reference, position))
                    position += 1
    return chunks


def parse_thml_string(xml_string: str) -> ThmlDocument:
    """Parse a ThML XML string into a ThmlDocument."""
    # Strip DOCTYPE to avoid network fetch
    xml_string = re.sub(r"<!DOCTYPE[^>]*>", "", xml_string)
    root = ET.fromstring(xml_string)

    # Metadata
    title = root.findtext(".//DC.Title") or root.findtext(".//title") or "Unknown"
    title = title.strip()

    creator = ""
    for el in root.findall(".//DC.Creator"):
        if el.get("scheme") == "file-as":
            creator = (el.text or "").strip()
            break

    author: str | None = None
    year: int | None = None
    if creator:
        author, year = _parse_author(creator)

    # Chunking strategy depends on whether this is the Summa
    if _is_summa(root):
        chunks = _chunk_summa(root)
    else:
        chunks = _chunk_standard(root)

    return ThmlDocument(title=title, author=author, year=year, chunks=chunks)


def parse_thml(path: str) -> ThmlDocument:
    """Parse a ThML XML file into a ThmlDocument."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_thml_string(f.read())
```

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_common.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/common.py datapipeline/tests/test_common.py
git commit -m "feat(datapipeline): add ThML parser for church fathers (common.py)"
```

---

## Task 6: church_fathers.py

**Files:**
- Create: `datapipeline/ingest/church_fathers.py`

No new tests needed — common.py is the logic layer and is already tested. This script is a thin orchestrator.

- [ ] **Implement church_fathers.py**

```python
# datapipeline/ingest/church_fathers.py
from __future__ import annotations
import asyncio
import os
import sys
from glob import glob
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document
from ingest.common import parse_thml

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")


async def main(pool) -> None:
    xml_files = sorted(
        f for f in glob(os.path.join(_SRC_DIR, "*.xml"))
        if not f.endswith(".Zone.Identifier")
    )
    print(f"Found {len(xml_files)} ThML files in {_SRC_DIR}")

    total_chunks = 0
    with tqdm(total=len(xml_files), unit="file", desc="Church Fathers") as pbar:
        for path in xml_files:
            filename = os.path.basename(path)
            try:
                doc = parse_thml(path)
            except Exception as exc:
                print(f"  WARNING: Failed to parse {filename}: {exc}", file=sys.stderr)
                pbar.update(1)
                continue

            if not doc.chunks:
                print(f"  WARNING: No chunks extracted from {filename}", file=sys.stderr)
                pbar.update(1)
                continue

            doc_id = await upsert_document(
                pool,
                collection="church-fathers",
                title=doc.title,
                translation="",
                author=doc.author,
                year=doc.year,
                metadata={"source_file": filename},
            )

            for content, reference, position in doc.chunks:
                await upsert_chunk(pool, doc_id, content, position, reference)

            total_chunks += len(doc.chunks)
            pbar.set_postfix({"file": filename, "chunks": len(doc.chunks)})
            pbar.update(1)

    print(f"  Done. {total_chunks} total chunks written for church-fathers.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Smoke test against actual files**

```bash
cd datapipeline
python -c "
import asyncio
from ingest.common import parse_thml
doc = parse_thml('sources/church-fathers/confessions.xml')
print(f'Title: {doc.title}')
print(f'Author: {doc.author}')
print(f'Year: {doc.year}')
print(f'Chunks: {len(doc.chunks)}')
print(f'First ref: {doc.chunks[0][1]}')
print(f'First 100 chars: {doc.chunks[0][0][:100]}')
"
# Expected: Title: The Confessions..., 100+ chunks
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/church_fathers.py
git commit -m "feat(datapipeline): add church_fathers ingest script"
```

---

## Task 7: canon_law.py (TDD)

**Files:**
- Create: `datapipeline/tests/test_canon_law.py`
- Create: `datapipeline/ingest/canon_law.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_canon_law.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.canon_law import parse_canon_page, deduplicate_urls

SAMPLE_HTML = """<html><body><table><tbody><tr><td>
<p align="center"><b>CODE OF CANON LAW</b></p>
<p>Can. 1 The canons of this Code regard only the Latin Church.</p>
<p>Can. 2 For the most part the Code does not define the rites which must be observed.</p>
<p>Can. 5 §1. Universal or particular customs presently in force which are contrary to the prescripts.</p>
<p>§2. Universal or particular customs beyond the law are preserved.</p>
<p>Can. 6 §1. When this Code takes force, the following are abrogated:</p>
<p>1/ the Code of Canon Law promulgated in 1917;</p>
<p>2/ other universal or particular laws contrary to the prescripts;</p>
</td></tr></tbody></table></body></html>"""

def test_parse_canon_page_extracts_canons():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4  # Can. 1, 2, 5, 6

def test_parse_canon_strips_can_prefix():
    canons = parse_canon_page(SAMPLE_HTML)
    num, text = canons[0]
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

def test_parse_canon_skips_headers():
    canons = parse_canon_page(SAMPLE_HTML)
    texts = [c[1] for c in canons]
    assert not any("CODE OF CANON LAW" in t for t in texts)

def test_deduplicate_urls_strips_fragments():
    urls = [
        "/archive/cic_lib1-cann1-6_en.html",
        "/archive/cic_lib1-cann1-6_en.html#Art._1.",
        "/archive/cic_lib1-cann1-6_en.html#Art._2.",
        "/archive/cic_lib1-cann7-22_en.html",
    ]
    result = deduplicate_urls(urls, base="http://www.vatican.va")
    assert len(result) == 2
    assert "http://www.vatican.va/archive/cic_lib1-cann1-6_en.html" in result
    assert "http://www.vatican.va/archive/cic_lib1-cann7-22_en.html" in result
```

- [ ] **Run tests to confirm failure**

```bash
pytest tests/test_canon_law.py -v
# Expected: ImportError
```

- [ ] **Implement canon_law.py**

```python
# datapipeline/ingest/canon_law.py
from __future__ import annotations
import asyncio
import re
import sys
import time
import os

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document

_BASE = "http://www.vatican.va"
_INDEX_URL = f"{_BASE}/archive/cod-iuris-canonici/cic_index_en.html"
_DELAY = 1.0


def deduplicate_urls(hrefs: list[str], base: str = _BASE) -> list[str]:
    """Strip fragments, prepend base for relative URLs, deduplicate preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for href in hrefs:
        # Strip fragment
        url = href.split("#")[0]
        # Make absolute
        if url.startswith("http"):
            abs_url = url
        else:
            abs_url = base + url
        if abs_url not in seen:
            seen.add(abs_url)
            result.append(abs_url)
    return result


def parse_canon_page(html: str) -> list[tuple[int, str]]:
    """
    Parse a Vatican canon law HTML page.
    Returns list of (canon_number, full_text) tuples.
    """
    soup = BeautifulSoup(html, "lxml")
    # Find all <p> tags in the main content area
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]

    canons: list[tuple[int, str]] = []
    current_num: int | None = None
    current_parts: list[str] = []

    can_re = re.compile(r"^Can\.\s*(\d+)\s*(.*)", re.DOTALL)
    sub_re = re.compile(r"^§\d+\.")
    num_re = re.compile(r"^\d+/")

    def flush():
        if current_num is not None and current_parts:
            canons.append((current_num, "\n".join(current_parts)))

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
        if current_num is None:
            continue
        if sub_re.match(text) or num_re.match(text):
            current_parts.append(text)
        elif text.isupper() or (len(text) < 15 and not text[0].isdigit()):
            # Section header — skip
            continue
        else:
            current_parts.append(text)

    flush()
    return canons


def _discover_page_urls(index_html: str) -> list[str]:
    soup = BeautifulSoup(index_html, "lxml")
    hrefs = [
        a["href"] for a in soup.find_all("a", href=True)
        if "cic_lib" in a["href"] and "_en.html" in a["href"]
    ]
    return deduplicate_urls(hrefs)


async def main(pool) -> None:
    print("Fetching Canon Law index...")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(_INDEX_URL)
        resp.raise_for_status()
        page_urls = _discover_page_urls(resp.text)
        print(f"  Found {len(page_urls)} canon pages.")

        doc_id = await upsert_document(
            pool,
            collection="canon-law",
            title="Code of Canon Law (1983)",
            translation="",
            author="Catholic Church",
            year=1983,
            metadata={"source": "vatican.va"},
        )

        all_canons: list[tuple[int, str]] = []
        skipped: list[str] = []

        with tqdm(total=len(page_urls), unit="page", desc="Canon Law") as pbar:
            for url in page_urls:
                time.sleep(_DELAY)
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    canons = parse_canon_page(r.text)
                    all_canons.extend(canons)
                except Exception as exc:
                    print(f"\n  WARNING: Failed {url}: {exc}", file=sys.stderr)
                    skipped.append(url)
                pbar.update(1)

    # Deduplicate by canon number (some canons appear on multiple pages)
    seen_nums: set[int] = set()
    unique_canons: list[tuple[int, str]] = []
    for num, text in sorted(all_canons, key=lambda x: x[0]):
        if num not in seen_nums:
            seen_nums.add(num)
            unique_canons.append((num, text))

    print(f"  Ingesting {len(unique_canons)} unique canons...")
    for position, (canon_num, content) in enumerate(unique_canons):
        await upsert_chunk(
            pool,
            document_id=doc_id,
            content=content,
            position=position,
            reference=f"Can. {canon_num}",
        )

    if skipped:
        print(f"  WARNING: {len(skipped)} pages failed: {skipped}", file=sys.stderr)
    print(f"  Done. {len(unique_canons)} canons written.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_canon_law.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/canon_law.py datapipeline/tests/test_canon_law.py
git commit -m "feat(datapipeline): add canon law ingest script"
```

---

## Task 8: encyclicals.py (TDD)

**Files:**
- Create: `datapipeline/tests/test_encyclicals.py`
- Create: `datapipeline/ingest/encyclicals.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_encyclicals.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.encyclicals import parse_encyclical_paragraphs, group_paragraphs

SAMPLE_HTML_PPN = """<html><body>
<p>To Our Venerable Brethren... [intro not numbered]</p>
<p>1. That the spirit of revolutionary change, which has long been disturbing the nations of the world, should have passed beyond the sphere of politics.</p>
<p>2. It is not surprising that, with the growth of new industries settling in new lands, and with the surge of new economic forces.</p>
<p>3. To remedy these wrongs the socialists, working on the poor man's envy of the rich, are striving to do away with private property.</p>
<p>4. But all agree, and there can be no question whatever, that some remedy must be found, and found quickly.</p>
<p>5. We approach the subject with confidence, and in the exercise of the rights which manifestly appertain to Us.</p>
</body></html>"""

def test_parse_encyclical_extracts_numbered_paragraphs():
    paras = parse_encyclical_paragraphs(SAMPLE_HTML_PPN)
    assert len(paras) == 5
    assert paras[0][0] == 1
    assert "revolutionary change" in paras[0][1]

def test_parse_encyclical_skips_unnumbered_intro():
    paras = parse_encyclical_paragraphs(SAMPLE_HTML_PPN)
    assert all(p[0] is not None for p in paras)

def test_group_paragraphs_groups_three():
    paras = [(i, f"content of paragraph {i} " * 10) for i in range(1, 6)]
    groups = group_paragraphs(paras, chunk_size=3)
    assert len(groups) == 2
    content0, ref0, pos0 = groups[0]
    assert "§1-3" in ref0
    assert pos0 == 0
    content1, ref1, pos1 = groups[1]
    assert "§4-5" in ref1
    assert pos1 == 1

def test_group_paragraphs_skips_short():
    paras = [(1, "short"), (2, "x" * 100), (3, "x" * 100), (4, "x" * 100)]
    groups = group_paragraphs(paras, chunk_size=3, min_length=50)
    # §1 skipped, remaining 3 form one group
    assert len(groups) == 1

def test_parse_encyclical_strips_number_prefix():
    paras = parse_encyclical_paragraphs(SAMPLE_HTML_PPN)
    assert not paras[0][1].startswith("1.")
    assert "revolutionary change" in paras[0][1]
```

- [ ] **Run tests to confirm failure**

```bash
pytest tests/test_encyclicals.py -v
# Expected: ImportError
```

- [ ] **Implement encyclicals.py**

```python
# datapipeline/ingest/encyclicals.py
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
_CHUNK_SIZE = 3

# (title, author, year, url)
# papalencyclicals.net used where available; vatican.va for JP2+, Francis
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
    ("Amoris Laetitia",     "Pope Francis",        2016, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20160319_amoris-laetitia.html"),
]

_NUM_PREFIX_RE = re.compile(r"^\d+\.\s*")


def parse_encyclical_paragraphs(html: str) -> list[tuple[int, str]]:
    """
    Extract numbered paragraphs from encyclical HTML.
    Returns list of (para_num, text) — text has the number prefix stripped.
    """
    soup = BeautifulSoup(html, "lxml")
    result: list[tuple[int, str]] = []
    for p in soup.find_all("p"):
        text = p.get_text(separator=" ", strip=True)
        m = re.match(r"^(\d+)\.\s*(.+)", text, re.DOTALL)
        if m:
            num = int(m.group(1))
            body = m.group(2).strip()
            result.append((num, body))
    return result


def group_paragraphs(
    paras: list[tuple[int, str]],
    chunk_size: int = _CHUNK_SIZE,
    min_length: int = _MIN_LENGTH,
) -> list[tuple[str, str, int]]:
    """
    Group paragraphs into chunks of chunk_size.
    Returns list of (content, reference, position).
    """
    filtered = [(num, text) for num, text in paras if len(text) >= min_length]
    chunks: list[tuple[str, str, int]] = []
    for i in range(0, len(filtered), chunk_size):
        group = filtered[i : i + chunk_size]
        content = "\n\n".join(text for _, text in group)
        first_num = group[0][0]
        last_num = group[-1][0]
        ref = f"§{first_num}-{last_num}" if first_num != last_num else f"§{first_num}"
        chunks.append((content, ref, len(chunks)))
    return chunks


async def main(pool) -> None:
    skipped: list[str] = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
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

                paras = parse_encyclical_paragraphs(resp.text)
                chunks = group_paragraphs(paras)

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

                for content, reference, position in chunks:
                    await upsert_chunk(
                        pool,
                        document_id=doc_id,
                        content=content,
                        position=position,
                        reference=f"{title}, {reference}",
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

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_encyclicals.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/encyclicals.py datapipeline/tests/test_encyclicals.py
git commit -m "feat(datapipeline): add encyclicals ingest script (18 landmark documents)"
```

---

## Task 9: saints.py (TDD)

**Files:**
- Create: `datapipeline/tests/test_saints.py`
- Create: `datapipeline/ingest/saints.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_saints.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.saints import filter_saint_links, parse_saint_article, chunk_text

SAMPLE_INDEX = """<html><body>
<a href="13794a.htm">Francis of Assisi, Saint</a>
<a href="02050a.htm">Thomas Aquinas, Saint</a>
<a href="01015a.htm">Blessed Margaret of Castello</a>
<a href="01016a.htm">Architecture</a>
<a href="07654a.htm">St. Augustine of Hippo</a>
<a href="09999a.htm">Canon Law</a>
<a href="00001a.htm">Venerable Bede</a>
</body></html>"""

BASE = "https://www.newadvent.org/cathen/"

SAMPLE_ARTICLE = """<html><body>
<h1>Francis of Assisi, Saint</h1>
<div id="bodycontents">
<p>Francis of Assisi was born in 1181 or 1182 to Pietro di Bernardone, a prosperous cloth merchant.</p>
<p>As a young man, Francis participated in Assisi's social life and looked forward to a career as a knight.</p>
<p>After being captured in a battle between Assisi and Perugia in 1202, Francis was held for ransom for about a year.</p>
<p>In 1205 Francis had the famous mystical experience in the ruined church of San Damiano near Assisi, in which Christ on the Crucifix spoke to him: "Francis, go and repair my Church."</p>
<p>Francis devoted himself to a life of poverty, preaching, and care for the poor and sick, especially lepers.</p>
<p>He founded the Order of Friars Minor, commonly called the Franciscans, in 1209.</p>
</div>
</body></html>"""

def test_filter_finds_saints():
    links = filter_saint_links(SAMPLE_INDEX, BASE)
    titles = [t for _, t in links]
    assert "Francis of Assisi, Saint" in titles
    assert "Thomas Aquinas, Saint" in titles
    assert "St. Augustine of Hippo" in titles
    assert "Blessed Margaret of Castello" in titles
    assert "Venerable Bede" in titles

def test_filter_excludes_non_saints():
    links = filter_saint_links(SAMPLE_INDEX, BASE)
    titles = [t for _, t in links]
    assert "Architecture" not in titles
    assert "Canon Law" not in titles

def test_filter_builds_absolute_urls():
    links = filter_saint_links(SAMPLE_INDEX, BASE)
    urls = [u for u, _ in links]
    assert all(u.startswith("https://") for u in urls)
    assert f"{BASE}13794a.htm" in urls

def test_parse_saint_article_extracts_text():
    text = parse_saint_article(SAMPLE_ARTICLE)
    assert "Francis of Assisi" in text
    assert "Pietro di Bernardone" in text
    assert len(text) > 100

def test_chunk_text_splits_on_words():
    long_text = " ".join([f"word{i}" for i in range(200)])
    chunks = chunk_text(long_text, max_words=50)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 50 for c in chunks)

def test_chunk_text_no_empty_chunks():
    text = "Hello world."
    chunks = chunk_text(text, max_words=50)
    assert len(chunks) == 1
    assert chunks[0] == "Hello world."
```

- [ ] **Run tests to confirm failure**

```bash
pytest tests/test_saints.py -v
# Expected: ImportError
```

- [ ] **Implement saints.py**

```python
# datapipeline/ingest/saints.py
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

_BASE = "https://www.newadvent.org/cathen/"
_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_DELAY = 1.0
_SAINT_KEYWORDS = re.compile(r"\bsaint\b|\bst\.\s|\bblessed\b|\bvenerable\b", re.IGNORECASE)
_MAX_WORDS = 400
_MIN_ARTICLE_LENGTH = 100


def filter_saint_links(html: str, base: str) -> list[tuple[str, str]]:
    """
    From a CE letter index page, return (url, title) pairs for saint articles.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)
        if not title or not href.endswith(".htm"):
            continue
        if not _SAINT_KEYWORDS.search(title):
            continue
        # Build absolute URL
        if href.startswith("http"):
            url = href
        else:
            url = base + href
        results.append((url, title))
    return results


def parse_saint_article(html: str) -> str:
    """Extract main article text from a New Advent CE article page."""
    soup = BeautifulSoup(html, "lxml")
    # Try the main content div first
    content_div = soup.find("div", id="bodycontents") or soup.find("div", class_="bodycontents")
    if content_div:
        target = content_div
    else:
        # Fallback: grab all <p> tags after the <h1>
        target = soup.find("body") or soup

    paragraphs = [p.get_text(separator=" ", strip=True) for p in target.find_all("p")]
    text = " ".join(p for p in paragraphs if len(p) > 20)
    return text


def chunk_text(text: str, max_words: int = _MAX_WORDS) -> list[str]:
    """Split text into chunks of at most max_words, splitting on word boundaries."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i : i + max_words])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


async def main(pool) -> None:
    print("Collecting saint article URLs from New Advent CE...")
    all_links: list[tuple[str, str]] = []
    skipped_pages: list[str] = []
    skipped_articles: list[str] = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        # Step 1: collect all saint URLs from A-Z index pages
        for letter in _LETTERS:
            time.sleep(_DELAY)
            url = f"{_BASE}{letter}.htm"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                links = filter_saint_links(resp.text, _BASE)
                all_links.extend(links)
            except Exception as exc:
                print(f"\n  WARNING: Failed index page {url}: {exc}", file=sys.stderr)
                skipped_pages.append(url)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_links: list[tuple[str, str]] = []
        for url, title in all_links:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_links.append((url, title))

        print(f"  Found {len(unique_links)} saint article URLs.")

        # Step 2: scrape each article
        with tqdm(total=len(unique_links), unit="saint", desc="Saints") as pbar:
            for art_url, title in unique_links:
                time.sleep(_DELAY)
                try:
                    resp = client.get(art_url)
                    resp.raise_for_status()
                except Exception as exc:
                    print(f"\n  WARNING: Failed {title}: {exc}", file=sys.stderr)
                    skipped_articles.append(title)
                    pbar.update(1)
                    continue

                article_text = parse_saint_article(resp.text)
                if len(article_text) < _MIN_ARTICLE_LENGTH:
                    skipped_articles.append(title)
                    pbar.update(1)
                    continue

                text_chunks = chunk_text(article_text)
                if not text_chunks:
                    pbar.update(1)
                    continue

                doc_id = await upsert_document(
                    pool,
                    collection="saints",
                    title=title,
                    translation="",
                    author="Catholic Encyclopedia",
                    year=1913,
                    metadata={"url": art_url},
                )

                for position, content in enumerate(text_chunks):
                    await upsert_chunk(
                        pool,
                        document_id=doc_id,
                        content=content,
                        position=position,
                        reference=f"{title} — Catholic Encyclopedia",
                    )

                pbar.set_postfix({"saint": title[:30]})
                pbar.update(1)

    total_skipped = len(skipped_pages) + len(skipped_articles)
    if total_skipped:
        print(f"\n  WARNING: {total_skipped} items skipped.", file=sys.stderr)
    print(f"  Done. {len(unique_links) - len(skipped_articles)} saints written.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_saints.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/ingest/saints.py datapipeline/tests/test_saints.py
git commit -m "feat(datapipeline): add saints ingest script (New Advent Catholic Encyclopedia)"
```

---

## Task 10: embed.py (TDD)

**Files:**
- Create: `datapipeline/tests/test_embed.py`
- Create: `datapipeline/embed.py`

- [ ] **Write failing tests**

```python
# datapipeline/tests/test_embed.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from embed import make_batches, vec_to_pg

def test_make_batches_splits_correctly():
    items = list(range(250))
    batches = list(make_batches(items, 100))
    assert len(batches) == 3
    assert len(batches[0]) == 100
    assert len(batches[1]) == 100
    assert len(batches[2]) == 50

def test_make_batches_single_item():
    batches = list(make_batches([42], 100))
    assert len(batches) == 1
    assert batches[0] == [42]

def test_make_batches_empty():
    batches = list(make_batches([], 100))
    assert batches == []

def test_vec_to_pg_formats_correctly():
    vec = [0.1, -0.2, 0.3]
    result = vec_to_pg(vec)
    assert result == "[0.1,-0.2,0.3]"

def test_vec_to_pg_handles_integers():
    vec = [1, 0, -1]
    result = vec_to_pg(vec)
    assert result.startswith("[")
    assert result.endswith("]")
```

- [ ] **Run tests to confirm failure**

```bash
pytest tests/test_embed.py -v
# Expected: ImportError
```

- [ ] **Implement embed.py**

```python
# datapipeline/embed.py
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import time
from typing import Iterator

import openai
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import settings
from load import close_pool, get_pool

_BATCH_SIZE = 100
_MAX_RETRIES = 3


def make_batches(items: list, size: int) -> Iterator[list]:
    """Yield successive chunks of `size` from items."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def vec_to_pg(vec: list[float]) -> str:
    """Format a float list as pgvector literal: [f1,f2,...]"""
    return "[" + ",".join(str(v) for v in vec) + "]"


async def embed_batch(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API with retry on rate limit."""
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.embeddings.create(
                input=texts,
                model=settings.EMBEDDING_MODEL,
                dimensions=settings.EMBEDDING_DIMS,
            )
            sorted_data = sorted(response.data, key=lambda r: r.index)
            return [r.embedding for r in sorted_data]
        except openai.RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"\n  Rate limited — waiting {wait}s...", file=sys.stderr)
            await asyncio.sleep(wait)
    raise RuntimeError("embed_batch: unreachable")


async def run(dry_run: bool = False) -> None:
    pool = await get_pool()
    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        rows = await pool.fetch(
            "SELECT id, content FROM chunks WHERE content_embedding IS NULL ORDER BY id"
        )

        if dry_run:
            print(f"[dry-run] {len(rows)} chunks need embedding. Exiting.")
            return

        if not rows:
            print("All chunks already embedded.")
            return

        print(f"Embedding {len(rows)} chunks in batches of {_BATCH_SIZE}...")
        embedded = 0
        failed_ids: list[str] = []

        with tqdm(total=len(rows), unit="chunk", desc="Embed") as pbar:
            for batch in make_batches(list(rows), _BATCH_SIZE):
                texts = [r["content"] for r in batch]
                try:
                    vectors = await embed_batch(client, texts)
                except Exception as exc:
                    ids = [str(r["id"]) for r in batch]
                    print(f"\n  WARNING: Batch failed ({exc}). IDs: {ids[:3]}...", file=sys.stderr)
                    failed_ids.extend(ids)
                    pbar.update(len(batch))
                    continue

                async with pool.acquire() as conn:
                    async with conn.transaction():
                        for row, vec in zip(batch, vectors):
                            await conn.execute(
                                "UPDATE chunks SET content_embedding = $1::vector WHERE id = $2",
                                vec_to_pg(vec),
                                row["id"],
                            )
                embedded += len(batch)
                pbar.update(len(batch))

        print(f"  Done. {embedded} chunks embedded.")
        if failed_ids:
            print(f"  WARNING: {len(failed_ids)} chunks failed — re-run embed.py to retry.", file=sys.stderr)
    finally:
        await client.close()
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed all un-embedded chunks via OpenAI.")
    parser.add_argument("--dry-run", action="store_true", help="Print count and exit without calling OpenAI.")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
```

- [ ] **Run tests to confirm pass**

```bash
pytest tests/test_embed.py -v
# Expected: all PASS
```

- [ ] **Commit**

```bash
git add datapipeline/embed.py datapipeline/tests/test_embed.py
git commit -m "feat(datapipeline): add embed.py for batch OpenAI embedding"
```

---

## Task 11: run_all.py

**Files:**
- Create: `datapipeline/run_all.py`

No unit tests — this is a thin sequencer. Verified by running it.

- [ ] **Implement run_all.py**

```python
# datapipeline/run_all.py
"""Orchestrator: runs all ingest scripts then embed.py."""
from __future__ import annotations
import argparse
import asyncio
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load import close_pool, get_pool

from ingest import bible, catechism, canon_law, encyclicals, church_fathers, saints
import embed as embed_mod

PIPELINE: list[tuple[str, object]] = [
    ("bible",          bible),
    ("catechism",      catechism),
    ("canon-law",      canon_law),
    ("encyclicals",    encyclicals),
    ("church-fathers", church_fathers),
    ("saints",         saints),
]


async def run(collection: str | None = None, skip_embed: bool = False) -> None:
    pool = await get_pool()
    try:
        steps = [(name, mod) for name, mod in PIPELINE
                 if collection is None or name == collection]

        if not steps:
            print(f"ERROR: Unknown collection '{collection}'. "
                  f"Valid: {[n for n, _ in PIPELINE]}", file=sys.stderr)
            return

        total_start = time.time()
        for name, mod in steps:
            print(f"\n{'='*50}")
            print(f"  Running: {name}")
            print(f"{'='*50}")
            step_start = time.time()
            await mod.main(pool)
            elapsed = time.time() - step_start
            print(f"  [{name}] completed in {elapsed:.1f}s")

        if not skip_embed:
            print(f"\n{'='*50}")
            print(f"  Running: embed")
            print(f"{'='*50}")
            embed_start = time.time()
            await embed_mod.run(dry_run=False)
            print(f"  [embed] completed in {time.time() - embed_start:.1f}s")

        print(f"\nTotal pipeline time: {time.time() - total_start:.1f}s")
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Body of Christ data pipeline.")
    parser.add_argument("--collection", help="Run only this collection (bible, catechism, canon-law, encyclicals, church-fathers, saints)")
    parser.add_argument("--skip-embed", action="store_true", help="Skip the embedding step.")
    args = parser.parse_args()
    asyncio.run(run(collection=args.collection, skip_embed=args.skip_embed))
```

- [ ] **Verify imports resolve**

```bash
cd datapipeline
python -c "import run_all; print('OK')"
# Expected: OK
```

- [ ] **Commit**

```bash
git add datapipeline/run_all.py
git commit -m "feat(datapipeline): add run_all.py orchestrator"
```

---

## Task 12: Run full test suite

- [ ] **Run all tests**

```bash
cd datapipeline
pytest tests/ -v
# Expected: all tests PASS
```

- [ ] **Dry-run embed to verify DB connectivity**

```bash
cd datapipeline
python embed.py --dry-run
# Expected: prints chunk count (likely 0 since ingest hasn't run yet) and exits
```

- [ ] **Smoke-run bible ingest against real DB (skip embed)**

```bash
cd datapipeline
python run_all.py --collection bible --skip-embed
# Expected: ~35,000 chunks written across 146 documents (73 books × 2 translations)
```

- [ ] **Verify bible in DB**

```sql
SELECT collection, count(*) as docs FROM documents GROUP BY collection;
-- Expected: bible | 146

SELECT d.collection, count(c.id) as chunks, count(c.content_embedding) as embedded
FROM chunks c JOIN documents d ON c.document_id = d.id
GROUP BY d.collection;
-- Expected: bible | ~35000 | 0

SELECT content, reference FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.collection = 'bible' AND c.reference = 'Genesis 1:1-4'
LIMIT 1;
-- Expected: first 4 verses of Genesis
```

- [ ] **Run catechism**

```bash
python run_all.py --collection catechism --skip-embed
# Expected: ~2800 chunks
```

- [ ] **Verify catechism**

```sql
SELECT content FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.collection = 'catechism' AND c.reference = 'CCC §1';
-- Expected: "God, infinitely perfect and blessed in himself..."
```

- [ ] **Run church-fathers**

```bash
python run_all.py --collection church-fathers --skip-embed
# Expected: 11 documents, ~3000+ chunks
```

- [ ] **Run canon-law**

```bash
python run_all.py --collection canon-law --skip-embed
# Expected: 1752 canons
```

- [ ] **Verify canon**

```sql
SELECT content FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.collection = 'canon-law' AND c.reference = 'Can. 1';
-- Expected: "The canons of this Code regard only the Latin Church."
```

- [ ] **Run encyclicals**

```bash
python run_all.py --collection encyclicals --skip-embed
# Expected: 18 documents, ~2500 chunks
```

- [ ] **Run saints**

```bash
python run_all.py --collection saints --skip-embed
# Expected: ~500+ documents scraped from New Advent CE
```

- [ ] **Run embed across all collections**

```bash
python embed.py
# Expected: embeds all chunks, prints total count
# Note: this will take significant time (~35000+ chunks × OpenAI API calls)
# Cost estimate: ~$0.13 per million tokens at $0.13/M for text-embedding-3-large
```

- [ ] **Final verification**

```sql
SELECT d.collection,
       count(c.id) as total_chunks,
       count(c.content_embedding) as embedded_chunks,
       count(c.id) - count(c.content_embedding) as missing
FROM chunks c
JOIN documents d ON c.document_id = d.id
GROUP BY d.collection
ORDER BY d.collection;
-- Expected: missing = 0 for all collections
```

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat(datapipeline): complete all collection ingest scripts and embed pipeline"
```
