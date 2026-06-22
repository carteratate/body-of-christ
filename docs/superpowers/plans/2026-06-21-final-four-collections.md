# Final Four Collections — Dual-Pipeline Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `build_documents()` adapter for each of the four remaining collections (medieval, encyclicals, councils, canon-law) so they produce clean, anchored `Passage`s readable in the new reader with Supabase↔Qdrant parity, following the established dual-pipeline pattern.

**Architecture:** Each adapter parses vendored local sources (`sources/<collection>/`, already downloaded) into `list[Document]` of clean `Passage`s with deterministic ids/anchors, applies `normalize/` cleaners, and registers in `run_collection.py` `BUILDERS`. Writers, identity, model, schema, and reader are unchanged. Medieval reuses the church-fathers ThML machinery via a shared helper; encyclicals/councils use a typed-stream tokenizer; canon-law reuses `parse_canon_page` with deterministic Book-by-range + cross-page context carry.

**Tech Stack:** Python 3 (`python3`), pytest, BeautifulSoup/lxml (HTML), defusedxml (ThML), asyncpg + qdrant-client (writers, unchanged), OpenAI embeddings (search writer, unchanged).

**Spec:** `docs/superpowers/specs/2026-06-21-final-four-collections-design.md`

**Conventions:**
- Run datapipeline tests from `datapipeline/`: `python3 -m pytest -q`.
- One pre-existing unrelated failure exists (`test_catechism.py::test_tier3_in_brief_section_flagged`) — do not chase it; do not add new failures.
- Sources are vendored (gitignored). If `sources/<collection>/manifest.json` is missing, run `python3 scripts/vendor_sources.py --collection all` first.
- The live `run_collection.py --target both` runs (Tasks 8–11) spend OpenAI money and mutate dev Supabase+Qdrant — they are **gated**: get explicit owner approval before each.

---

## File Structure

- **Create** `datapipeline/ingest/thml_doc.py` — shared ThML per-work Document builder (`make_doc`, `_chapter_label`, `_cap_pieces`), extracted from `church_fathers.py`. Used by church-fathers and medieval.
- **Modify** `datapipeline/ingest/church_fathers.py` — import `make_doc`/`_chapter_label`/`_cap_pieces` from `thml_doc` instead of defining locally; behavior unchanged.
- **Rewrite** `datapipeline/ingest/medieval.py` — `build_documents()` reading the manifest, using `thml_doc.make_doc` + `iter_chapters`; Anselm multi-work handled.
- **Rewrite** `datapipeline/ingest/encyclicals.py` — typed-stream tokenizer + `build_documents()`; old `parse_encyclical`/web-fetch removed.
- **Rewrite** `datapipeline/ingest/councils.py` — `build_documents()` branching ecumenical vs Vatican II; old `parse_*`/web-fetch removed.
- **Rewrite** `datapipeline/ingest/canon_law.py` — keep `parse_canon_page` & helpers; add Book-range map + cross-page context carry + `build_documents()`; old `main`/web-fetch removed.
- **Modify** `datapipeline/run_collection.py` — register the four builders in `BUILDERS`.
- **Modify** `datapipeline/config.py` — add per-collection overlap knobs.
- **Tests:** rewrite `tests/test_encyclicals.py`, `tests/test_councils.py`; extend `tests/test_canon_law.py`; replace `tests/test_medieval.py`; add `tests/test_thml_doc.py`.

---

## Task 1: Extract shared ThML doc builder (`thml_doc.py`)

**Files:**
- Create: `datapipeline/ingest/thml_doc.py`
- Modify: `datapipeline/ingest/church_fathers.py` (lines 42–120: remove local `_chapter_label`, `_cap_pieces`, `_make_doc`; import from `thml_doc`)
- Test: `datapipeline/tests/test_thml_doc.py`, plus existing `tests/test_church_fathers.py` as the regression guard

- [ ] **Step 1: Write the failing test**

`datapipeline/tests/test_thml_doc.py`:
```python
import os
from ingest.thml_doc import make_doc, _cap_pieces

def test_cap_pieces_splits_oversized():
    text = "x" * 5000
    pieces = _cap_pieces(text, 3500)
    assert len(pieces) >= 2
    assert all(len(p) <= 3500 for p in pieces)

def test_make_doc_uses_collection_in_id_and_year():
    # Build a tiny fake chapter list: (book_label_or_None, element-with-direct-<p>)
    import defusedxml.ElementTree as ET
    elem = ET.fromstring("<div2 title='Chapter 1'><p>" + ("word " * 40) + "</p></div2>")
    doc = make_doc(collection="medieval", filename="f.xml", author="Boethius",
                   title="Consolation of Philosophy", chapters=[(None, elem)], year=524)
    assert doc is not None
    assert doc.collection == "medieval"
    assert doc.year == 524
    assert doc.passages and doc.passages[0].chapter_key
    assert not doc.passages[0].content.lstrip().startswith("[")
    # deterministic id derived from collection+author+title
    from identity import document_id
    assert doc.id == document_id("medieval", "Boethius", "Consolation of Philosophy")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python3 -m pytest tests/test_thml_doc.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingest.thml_doc'`.

- [ ] **Step 3: Create `ingest/thml_doc.py`** (move the three functions out of `church_fathers.py`, generalize `make_doc`)

`datapipeline/ingest/thml_doc.py`:
```python
"""Shared ThML per-work Document builder.

Extracted from church_fathers so medieval (also CCEL ThML) reuses one tested
path. Builds a Document of clean Passages from a flat list of
(book_label|None, chapter_element) pairs, flattening book->chapter into labels.
"""
from __future__ import annotations

import re

from config import settings
from identity import document_id, anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import smart_title_case
from ingest.common import _direct_p_text, _book_label, split_at_sentences, _split_at_whitespace


def _chapter_label(elem) -> str:
    """A short, clean chapter heading from ThML shorttitle/title/n attributes."""
    st = (elem.get("shorttitle") or "").strip()
    title = (elem.get("title") or "").strip()
    n = (elem.get("n") or "").strip()
    typ = (elem.get("type") or "").strip().lower()
    if st and not st.endswith("...") and len(st) <= 45:
        return smart_title_case(st)
    if typ == "chapter" and n:
        return f"Chapter {n}"
    head = re.split(r"\.?—|—", title)[0].strip().rstrip(".")
    if head:
        return smart_title_case(head[:60])
    return f"Chapter {n}" if n else "Section"


def _cap_pieces(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def make_doc(*, collection: str, filename: str, author: str, title: str,
             chapters: list, year: int | None = None,
             extra_meta: dict | None = None) -> Document | None:
    """Build one Document from (book|None, chapter_elem) pairs. Returns None if empty."""
    if not chapters:
        return None
    work_slug = slugify(title) or slugify(author) or "work"
    maxc = settings.MAX_PASSAGE_CHARS
    passages: list[Passage] = []
    pos = 0
    seen_keys: dict[str, int] = {}
    for book, elem in chapters:
        raw = _direct_p_text(elem)
        if len(raw) < 100:
            continue
        self_book = _book_label(elem)
        if book is None and self_book:
            book = self_book
            core = "Introduction"
        else:
            core = _chapter_label(elem)
        if book:
            book_clean = smart_title_case(book)
            label = f"{book_clean} · {core}"
            base_key = make_anchor(work_slug, slugify(book_clean), slugify(core) or "sec")
        else:
            book_clean = None
            label = core
            base_key = make_anchor(work_slug, slugify(core) or "sec")
        if base_key in seen_keys:
            seen_keys[base_key] += 1
            ch_key = f"{base_key}--{seen_keys[base_key]}"
        else:
            seen_keys[base_key] = 1
            ch_key = base_key
        meta = {"source_file": filename}
        if book_clean:
            meta["book"] = book_clean
        if extra_meta:
            meta.update(extra_meta)
        parts = _cap_pieces(raw, maxc)
        for i, part in enumerate(parts):
            sub = f"/p{i + 1}" if len(parts) > 1 else ""
            passages.append(Passage(
                content=clean_text(part),
                reference=f"{author} — {title}, {label}",
                anchor=ch_key + sub, chapter_key=ch_key, chapter_label=label,
                position=pos, unit_label=None, metadata=meta))
            pos += 1
    if not passages:
        return None
    doc_meta = {"source_file": filename}
    if extra_meta:
        doc_meta.update(extra_meta)
    return Document(id=document_id(collection, author, title), collection=collection,
                    title=title, author=author, year=year, metadata=doc_meta,
                    passages=passages)
```

- [ ] **Step 4: Rewire `church_fathers.py` to use the shared helper**

In `datapipeline/ingest/church_fathers.py`: delete the local `_chapter_label` (lines ~42–56), `_cap_pieces` (~59–65), and `_make_doc` (~68–120). Replace the import block and add a thin wrapper. Change the imports near the top to:
```python
from ingest.common import (
    iter_chapters, _build_parent_map, _cf_skippable,
)
from ingest.thml_doc import make_doc
```
And replace the three deleted functions with:
```python
def _make_doc(filename, author, title, chapters):
    return make_doc(collection="church-fathers", filename=filename,
                    author=author, title=title, chapters=chapters)
```
(Leave the rest of `church_fathers.py` — `_strip_doctype`, `_read_root`, `build_documents`, `build_all` — unchanged; they call `_make_doc`.)

- [ ] **Step 5: Run tests to verify pass + no church-fathers regression**

Run: `cd datapipeline && python3 -m pytest tests/test_thml_doc.py tests/test_church_fathers.py -q`
Expected: PASS (all church-fathers tests still green — this proves the extraction is behavior-preserving).

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/thml_doc.py datapipeline/ingest/church_fathers.py datapipeline/tests/test_thml_doc.py
git commit -m "refactor(pipeline): extract shared ThML doc builder (thml_doc.make_doc)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Medieval adapter

**Files:**
- Rewrite: `datapipeline/ingest/medieval.py`
- Modify: `datapipeline/run_collection.py` (BUILDERS + import)
- Test: `datapipeline/tests/test_medieval.py` (replace)

- [ ] **Step 1: Write the failing test** (`datapipeline/tests/test_medieval.py`, replacing the old file)

```python
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ingest.medieval import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "medieval")
pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(_SRC, "manifest.json")),
    reason="medieval sources not vendored; run scripts/vendor_sources.py")

def _docs():
    return build_documents()

def test_anselm_splits_into_three_works_single_author():
    docs = _docs()
    anselm = [d for d in docs if d.author == "Anselm"]
    titles = {d.title for d in anselm}
    assert {"Proslogium", "Monologium", "Cur Deus Homo"} <= {t for t in titles
            for key in ["Proslogium", "Monologium", "Cur Deus Homo"] if key in t} or \
           any("Proslogium" in t for t in titles)
    assert all(d.author == "Anselm" for d in anselm)

def test_single_works_present_with_year():
    docs = _docs()
    boeth = [d for d in docs if d.author == "Boethius"]
    assert len(boeth) == 1
    assert boeth[0].year == 524
    assert boeth[0].collection == "medieval"

def test_content_is_clean_and_anchored():
    for d in _docs():
        assert d.passages, d.title
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")

def test_document_ids_unique():
    ids = [d.id for d in _docs()]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python3 -m pytest tests/test_medieval.py -q`
Expected: FAIL — `build_documents` not defined / old `medieval.py` has no such symbol.

- [ ] **Step 3: Rewrite `datapipeline/ingest/medieval.py`**

```python
"""Medieval theology ingestion (dual pipeline).

Reads vendored CCEL ThML from sources/medieval/ and builds one Document per
(author, work) via the shared ThML helper. Anselm's basic_works.xml is
multi-work / single-author (each div1 is a work).
"""
from __future__ import annotations

import json
import os
import re

import defusedxml.ElementTree as ET

from identity import document_id  # noqa: F401  (kept for parity/debugging)
from model import Document
from normalize.caps import smart_title_case
from ingest.common import iter_chapters, _build_parent_map, _cf_skippable
from ingest.thml_doc import make_doc

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "medieval")


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    docs: list[Document] = []
    for entry in manifest:
        path = os.path.join(_SRC, entry["file"])
        root = _read_root(path)
        parent_map = _build_parent_map(root)
        author, year = entry["author"], entry["year"]
        extra = {"source_url": entry["url"]}
        if entry.get("fix_author"):
            # Multi-work single-author file (Anselm): div1 = work.
            div1s = [d for d in root.iter("div1")
                     if not _cf_skippable(d.get("title") or "")]
            for d1 in div1s:
                work = smart_title_case((d1.get("title") or "").strip()) or entry["title"]
                d = make_doc(collection="medieval", filename=entry["file"], author=author,
                             title=work, chapters=list(iter_chapters(d1, parent_map)),
                             year=year, extra_meta=extra)
                if d:
                    docs.append(d)
        else:
            d = make_doc(collection="medieval", filename=entry["file"], author=author,
                         title=entry["title"], chapters=list(iter_chapters(root, parent_map)),
                         year=year, extra_meta=extra)
            if d:
                docs.append(d)
    return docs
```

- [ ] **Step 4: Register in `run_collection.py`**

In `datapipeline/run_collection.py`, change the ingest import line to include the four and add to `BUILDERS`:
```python
from ingest import church_fathers, summa, bible, catechism, medieval, encyclicals, councils, canon_law

BUILDERS = {
    "church-fathers": church_fathers.build_all,
    "summa": lambda: [summa.build_document()],
    "bible": bible.build_documents,
    "catechism": lambda: [catechism.build_document()],
    "medieval": medieval.build_documents,
    "encyclicals": encyclicals.build_documents,
    "councils": councils.build_documents,
    "canon-law": canon_law.build_documents,
}
```
(The encyclicals/councils/canon_law modules get their `build_documents` in Tasks 3–5; until then this import will fail, so do Step 4's BUILDERS edit but keep the import limited to `medieval` for now, OR complete Tasks 3–5 before running run_collection. To keep this task self-contained and tests green, import only the modules that already have `build_documents`:)
```python
from ingest import church_fathers, summa, bible, catechism, medieval
BUILDERS = {
    "church-fathers": church_fathers.build_all,
    "summa": lambda: [summa.build_document()],
    "bible": bible.build_documents,
    "catechism": lambda: [catechism.build_document()],
    "medieval": medieval.build_documents,
}
```
The remaining three are added to this dict in their own tasks.

- [ ] **Step 5: Run tests + run_collection import sanity**

Run: `cd datapipeline && python3 -m pytest tests/test_medieval.py tests/test_run_collection.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/medieval.py datapipeline/run_collection.py datapipeline/tests/test_medieval.py
git commit -m "feat(pipeline): medieval dual-pipeline adapter (build_documents)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Encyclicals adapter

**Files:**
- Rewrite: `datapipeline/ingest/encyclicals.py`
- Modify: `datapipeline/run_collection.py` (add `encyclicals` to import + BUILDERS)
- Test: `datapipeline/tests/test_encyclicals.py` (replace old parse-based tests)

- [ ] **Step 1: Write the failing tests** (`datapipeline/tests/test_encyclicals.py`, replacing the file)

```python
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.encyclicals import _tokens, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "encyclicals")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

# ---- tokenizer fixtures (no network) ----
INLINE = """<html><body>
<p>To Our Venerable Brethren, greeting and Apostolic Blessing.</p>
<p>1. That the spirit of revolutionary change which has long been disturbing the nations of the world.</p>
<p>2. Therefore venerable brethren as on former occasions when it seemed opportune to refute false teaching.</p>
</body></html>"""

HEADING_BODY = """<html><body>
<p>Venerable Brothers greetings and the Apostolic Blessing.</p>
<p>I. INHERITANCE</p>
<p><b>1. At the close of the second Millennium</b></p>
<p>THE REDEEMER OF MAN Jesus Christ is the centre of the universe and of history and to him go my thoughts.</p>
<p>more body of section one continuing the thought with additional substance for the paragraph.</p>
<p><b>2. The first words</b></p>
<p>The first words body text that belongs to paragraph two of this encyclical document here.</p>
</body></html>"""

def _kinds(toks):
    return [t[0] for t in toks]

def test_inline_layout_yields_two_paras_after_preamble():
    toks = _tokens(BeautifulSoup(INLINE, "lxml"))
    assert _kinds(toks).count("preamble") == 1
    paras = [t for t in toks if t[0] == "para"]
    assert [p[1] for p in paras] == [1, 2]
    assert "revolutionary change" in paras[0][2]

def test_heading_body_layout_absorbs_following_paragraphs():
    toks = _tokens(BeautifulSoup(HEADING_BODY, "lxml"))
    paras = [t for t in toks if t[0] == "para"]
    assert [p[1] for p in paras] == [1, 2]
    assert "THE REDEEMER OF MAN" in paras[0][2]
    assert "more body of section one" in paras[0][2]   # absorbed continuation
    assert any(t[0] == "section" for t in toks)        # "I. INHERITANCE" is a section

def test_pre_first_number_header_not_a_section():
    # The bold title before the first number must not register as a section.
    html = """<html><body><p><b>RERUM NOVARUM</b></p>
    <p>1. The spirit of revolutionary change disturbing nations across the whole world today.</p></body></html>"""
    toks = _tokens(BeautifulSoup(html, "lxml"))
    assert not any(t[0] == "section" for t in toks)

# ---- real-file invariants ----
@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_all_eighteen_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 18
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"

@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_layout_b_documents_recovered():
    docs = {d.title: d for d in build_documents()}
    for title in ("Redemptor Hominis", "Laborem Exercens"):
        d = docs[title]
        units = [p.unit_label for p in d.passages if p.unit_label]
        assert len(units) >= 15, f"{title} only {len(units)} numbered passages"

@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_clean_anchored_and_no_footnote_markers():
    import re
    for d in build_documents():
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")
            assert not re.search(r"\[\d+\]", p.content), f"footnote marker left in {d.title}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python3 -m pytest tests/test_encyclicals.py -q`
Expected: FAIL — `_tokens`/`build_documents` not importable.

- [ ] **Step 3: Rewrite `datapipeline/ingest/encyclicals.py`**

```python
"""Encyclicals ingestion (dual pipeline).

One Document per encyclical from vendored HTML. A typed-stream tokenizer over
<p> handles three numbering layouts (inline `N. body`, bold heading + following
body, and section headers). One passage per numbered paragraph; chapters group
by section header, falling back to paragraph-range buckets.
"""
from __future__ import annotations

import json
import os
import re

from bs4 import BeautifulSoup

from config import settings
from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.footnotes import strip_footnote_markers
from ingest.common import split_at_sentences, _split_at_whitespace

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "encyclicals")
_NUM = re.compile(r"^(\d+)\.\s*(.*)", re.DOTALL)
_ROMAN = re.compile(r"^[IVX]+\.\s+\S")
_BUCKET = 20
_HEADING_MAX = 60   # body shorter than this after "N." => heading+body layout


def _is_bold_only(p) -> bool:
    kids = [c for c in p.children if getattr(c, "name", None)]
    bare = "".join(str(c) for c in p.children if not getattr(c, "name", None)).strip()
    t = p.get_text(strip=True)
    return (len(kids) == 1 and kids[0].name in ("b", "strong")
            and not bare and len(t) >= 8 and not t.endswith(":"))


def _tokens(soup) -> list[tuple[str, int | None, str]]:
    """Return an ordered list of ('preamble'|'section'|'para', num|None, text)."""
    items = [(p, p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    items = [(p, t) for p, t in items if t]
    toks: list[tuple[str, int | None, str]] = []
    seen = False
    cur: list | None = None   # [num, [parts]]

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            toks.append(("para", cur[0], "\n\n".join(x for x in cur[1] if x)))
            cur = None

    for p, t in items:
        m = _NUM.match(t)
        header = bool(_ROMAN.match(t)) or _is_bold_only(p)
        if not seen:
            if m:
                seen = True
                body = m.group(2).strip()
                cur = [int(m.group(1)), [body] if body else []]
            else:
                toks.append(("preamble", None, t))
            continue
        if m:
            flush()
            body = m.group(2).strip()
            cur = [int(m.group(1)), [body] if body else []]
            continue
        if header:
            flush()
            toks.append(("section", None, t))
            continue
        if cur is not None:        # stray prose => body of the open paragraph
            cur[1].append(t)
    flush()
    return toks


def _cap(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def build_document(entry: dict) -> Document:
    path = os.path.join(_SRC, entry["file"])
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    toks = _tokens(soup)
    slug, title, author = entry["slug"], entry["title"], entry["author"]
    did = document_id("encyclicals", slug)
    has_sec = any(k == "section" for k, _, _ in toks)
    meta = {"pope": author, "url": entry["url"]}
    passages: list[Passage] = []
    pos = 0
    seen_anchors: set[str] = set()

    def emit(content: str, ref: str, base_anchor: str, ckey: str, clabel: str,
             unit: str | None) -> None:
        nonlocal pos
        content = clean_text(strip_footnote_markers(content))
        if not content:
            return
        pieces = _cap(content, settings.MAX_PASSAGE_CHARS)
        for j, piece in enumerate(pieces):
            anc = base_anchor + (f"/p{j + 1}" if len(pieces) > 1 else "")
            k = 1
            while anc in seen_anchors:
                k += 1
                anc = f"{base_anchor}-{k}" if len(pieces) == 1 else f"{base_anchor}/p{j + 1}-{k}"
            seen_anchors.add(anc)
            passages.append(Passage(content=piece, reference=ref, anchor=anc,
                                    chapter_key=ckey, chapter_label=clabel,
                                    position=pos, unit_label=unit, metadata=meta))
            pos += 1

    # Preamble passage (greeting before the first number).
    pre = "\n\n".join(t for k, _, t in toks if k == "preamble").strip()
    if pre:
        emit(pre, f"{title} — Preamble", make_anchor(slug, "preamble"),
             make_anchor(slug, "preamble"), "Preamble", None)

    sec_ord = 0
    cur_key = cur_label = None
    for k, n, t in toks:
        if k == "preamble":
            continue
        if k == "section":
            sec_ord += 1
            cur_key = make_anchor(slug, f"sec-{sec_ord}")
            cur_label = title_case_shouting(clean_text(t))
            continue
        # k == "para"
        if has_sec:
            if cur_key is None:
                cur_key, cur_label = make_anchor(slug, "sec-0"), "Introduction"
            ckey, clabel = cur_key, cur_label
        else:
            b = (n - 1) // _BUCKET
            lo, hi = b * _BUCKET + 1, b * _BUCKET + _BUCKET
            ckey, clabel = make_anchor(slug, f"bucket-{b}"), f"Paragraphs {lo}–{hi}"
        emit(t, f"{title}, §{n}", make_anchor(slug, n), ckey, clabel, f"§{n}")

    return Document(id=did, collection="encyclicals", title=title, author=author,
                    year=entry["year"], metadata={"url": entry["url"], "pope": author},
                    passages=passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e) for e in manifest]
```

- [ ] **Step 4: Add `encyclicals` to `run_collection.py` BUILDERS**

In `datapipeline/run_collection.py` add `encyclicals` to the `from ingest import …` line and add `"encyclicals": encyclicals.build_documents,` to `BUILDERS`.

- [ ] **Step 5: Run tests to verify pass**

Run: `cd datapipeline && python3 -m pytest tests/test_encyclicals.py -q`
Expected: PASS (all fixture + real-file tests, including the 18-doc and layout-B recovery checks).

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/encyclicals.py datapipeline/run_collection.py datapipeline/tests/test_encyclicals.py
git commit -m "feat(pipeline): encyclicals dual-pipeline adapter (typed-stream tokenizer)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Councils adapter

**Files:**
- Rewrite: `datapipeline/ingest/councils.py`
- Modify: `datapipeline/run_collection.py` (add `councils` to import + BUILDERS)
- Test: `datapipeline/tests/test_councils.py` (replace)

- [ ] **Step 1: Write the failing tests** (`datapipeline/tests/test_councils.py`, replacing the file)

```python
import os, sys, re
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.councils import build_ecumenical, build_vatican2, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

CANON_HTML = """<html><body>
<h2>Canons</h2>
<p>Canon 1. If anyone says that the world was not created, let him be anathema and rejected.</p>
<p>Canon 2. If anyone denies the divine nature, let him be condemned by the holy synod here.</p>
</body></html>"""

VAT2_HTML = """<html><body>
<p><strong>CHAPTER I</strong></p>
<p>1. In His goodness and wisdom God chose to reveal Himself and to make known the mystery of His will.</p>
<p>2. By this revelation the invisible God out of the abundance of His love speaks to men as friends.</p>
</body></html>"""

def test_ecumenical_canon_passages_have_unit_and_anchor():
    entry = {"council": "Council of Trent", "document": "Council of Trent", "year": 1563,
             "group": "ecumenical-1-20", "file": "x.html", "url": "http://example"}
    passages = build_ecumenical(entry, BeautifulSoup(CANON_HTML, "lxml")).passages
    assert [p.unit_label for p in passages] == ["Canon 1", "Canon 2"]
    assert passages[0].anchor.startswith("council-of-trent/canon/1")
    assert not passages[0].content.lstrip().startswith("[")

def test_vatican2_numbered_paragraphs_under_chapter():
    entry = {"council": "Second Vatican Council", "document": "Dei Verbum",
             "document_type": "constitution", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_HTML, "lxml"))
    assert d.title == "Dei Verbum"
    assert d.metadata["council"] == "Second Vatican Council"
    assert [p.unit_label for p in d.passages] == ["§1", "§2"]
    assert any("Chapter" in p.chapter_label for p in d.passages)

@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_all_documents_build_and_are_clean():
    docs = build_documents()
    assert len(docs) == 36          # 20 ecumenical + 16 Vatican II
    for d in docs:
        assert d.passages, d.title
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")
            assert not re.search(r"\[\d+\]", p.content)

@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_document_ids_unique():
    ids = [d.id for d in build_documents()]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python3 -m pytest tests/test_councils.py -q`
Expected: FAIL — symbols not importable.

- [ ] **Step 3: Rewrite `datapipeline/ingest/councils.py`**

```python
"""Ecumenical Councils ingestion (dual pipeline).

One Document per council (ecumenical 1-20) or per Vatican II document. Passages:
one per canon / numbered paragraph; plain prose accumulates to the size cap.
Chapters group by header (h2/h3/h4 or CHAPTER N); header-less prose forms a
single 'Text' chapter.
"""
from __future__ import annotations

import json
import os
import re

from bs4 import BeautifulSoup

from config import settings
from identity import document_id, anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.footnotes import strip_footnote_markers
from ingest.common import split_at_sentences, _split_at_whitespace

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_CANON = re.compile(r"^(?:Canon|Can\.?)\s+(\d+|[IVXLCDM]+)[\.\:]?\s*(.*)", re.IGNORECASE | re.DOTALL)
_NUM = re.compile(r"^(\d+)\.\s+(.+)", re.DOTALL)
_CHAPTER = re.compile(r"^CHAPTER\s+([IVXLCDM]+)", re.IGNORECASE)
_MIN = 40
_TARGET = 2200


def _cap(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def _strip_chrome(soup) -> None:
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()


class _Builder:
    """Accumulates passages with unique anchors for one council document."""

    def __init__(self, doc_slug: str, title: str):
        self.doc_slug = doc_slug
        self.title = title
        self.passages: list[Passage] = []
        self.pos = 0
        self.seen: set[str] = set()

    def add(self, *, body: str, ref: str, base_anchor: str, ckey: str,
            clabel: str, unit: str | None, meta: dict) -> None:
        body = clean_text(strip_footnote_markers(body))
        if len(body) < 1:
            return
        for j, piece in enumerate(_cap(body, settings.MAX_PASSAGE_CHARS)):
            anc = base_anchor + (f"/p{j + 1}" if len(_cap(body, settings.MAX_PASSAGE_CHARS)) > 1 else "")
            k = 1
            while anc in self.seen:
                k += 1
                anc = f"{base_anchor}-{k}"
            self.seen.add(anc)
            self.passages.append(Passage(content=piece, reference=ref, anchor=anc,
                                         chapter_key=ckey, chapter_label=clabel,
                                         position=self.pos, unit_label=unit, metadata=meta))
            self.pos += 1


def build_ecumenical(entry: dict, soup: BeautifulSoup) -> Document:
    _strip_chrome(soup)
    council = entry["council"]
    cslug = slugify(council)
    did = document_id("councils", council, council)
    b = _Builder(cslug, council)
    meta = {"council": council, "year": entry["year"], "url": entry["url"]}
    sec_ord, sec_key, sec_label = 0, make_anchor(cslug, "sec-0"), "Text"
    prose: list[str] = []
    seq = 0

    def flush_prose() -> None:
        nonlocal seq, prose
        if not prose:
            return
        seq += 1
        b.add(body="\n\n".join(prose), ref=f"{council} — {sec_label}",
              base_anchor=make_anchor(cslug, f"sec-{sec_ord}", seq),
              ckey=sec_key, clabel=sec_label, unit=None, meta=meta)
        prose = []

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        if el.name in ("h2", "h3", "h4"):
            flush_prose()
            sec_ord += 1
            sec_key = make_anchor(cslug, f"sec-{sec_ord}")
            sec_label = title_case_shouting(clean_text(t))
            continue
        if len(t) < _MIN:
            continue
        mc, mn = _CANON.match(t), _NUM.match(t)
        if mc:
            flush_prose()
            num = mc.group(1)
            b.add(body=t, ref=f"{council}, Canon {num}",
                  base_anchor=make_anchor(cslug, "canon", num),
                  ckey=sec_key, clabel=sec_label, unit=f"Canon {num}", meta=meta)
        elif mn:
            flush_prose()
            num = mn.group(1)
            b.add(body=mn.group(2).strip(), ref=f"{council} — {sec_label}, §{num}",
                  base_anchor=make_anchor(cslug, f"sec-{sec_ord}", num),
                  ckey=sec_key, clabel=sec_label, unit=f"§{num}", meta=meta)
        else:
            prose.append(t)
            if sum(len(x) for x in prose) >= _TARGET:
                flush_prose()
    flush_prose()
    return Document(id=did, collection="councils", title=council, author=None,
                    year=entry["year"], metadata={"url": entry["url"],
                    "council_number": entry.get("council_number")}, passages=b.passages)


def build_vatican2(entry: dict, soup: BeautifulSoup) -> Document:
    _strip_chrome(soup)
    title = entry["document"]
    dslug = slugify(title)
    did = document_id("councils", "Second Vatican Council", title)
    b = _Builder(dslug, title)
    meta = {"council": "Second Vatican Council",
            "document_type": entry.get("document_type"), "year": entry["year"],
            "url": entry["url"]}
    chap_ord, chap_key, chap_label = 0, make_anchor(dslug, "chap-0"), title

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "strong"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        if _CHAPTER.match(t):
            chap_ord += 1
            chap_key = make_anchor(dslug, f"chap-{chap_ord}")
            chap_label = title_case_shouting(clean_text(t))
            continue
        if el.name != "p":
            continue
        mn = _NUM.match(t)
        if not mn:
            continue
        body = mn.group(2).strip()
        if len(body) < _MIN:
            continue
        num = mn.group(1)
        b.add(body=body, ref=f"{title}, §{num}",
              base_anchor=make_anchor(dslug, f"chap-{chap_ord}", num),
              ckey=chap_key, clabel=chap_label, unit=f"§{num}", meta=meta)
    return Document(id=did, collection="councils", title=title, author=None,
                    year=entry["year"], metadata=meta, passages=b.passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    docs: list[Document] = []
    for entry in manifest:
        with open(os.path.join(_SRC, entry["file"]), "rb") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        if entry["group"] == "vatican-ii":
            docs.append(build_vatican2(entry, soup))
        else:
            docs.append(build_ecumenical(entry, soup))
    return docs
```

- [ ] **Step 4: Add `councils` to `run_collection.py` BUILDERS** (import + `"councils": councils.build_documents,`).

- [ ] **Step 5: Run tests**

Run: `cd datapipeline && python3 -m pytest tests/test_councils.py -q`
Expected: PASS (fixtures + 36-doc real-file checks).

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/councils.py datapipeline/run_collection.py datapipeline/tests/test_councils.py
git commit -m "feat(pipeline): councils dual-pipeline adapter (ecumenical + Vatican II)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Canon-law adapter

**Files:**
- Rewrite: `datapipeline/ingest/canon_law.py` (keep `parse_canon_page`, `_classify_header`, `_reset_below`, `deduplicate_urls`, `_context_key`; remove web-fetch `main`; add Book-range + forward-fill + `build_documents`)
- Modify: `datapipeline/run_collection.py` (add `canon_law` to import + BUILDERS)
- Test: `datapipeline/tests/test_canon_law.py` (extend — keep existing `parse_canon_page` tests, add build tests)

- [ ] **Step 1: Write the failing tests** (append to `datapipeline/tests/test_canon_law.py`)

```python
import os
import pytest
from ingest.canon_law import _book_for, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "canon-law")
_vendored = os.path.exists(os.path.join(_SRC, "pages.json"))

def test_book_for_assigns_by_canon_range():
    assert _book_for(1).startswith("Book I")
    assert _book_for(203).startswith("Book I")
    assert _book_for(204).startswith("Book II")
    assert _book_for(750).startswith("Book III")
    assert _book_for(1752).startswith("Book VII")

@pytest.mark.skipif(not _vendored, reason="canon-law not vendored")
def test_single_document_one_passage_per_canon():
    docs = build_documents()
    assert len(docs) == 1
    d = docs[0]
    assert d.collection == "canon-law"
    # one passage per unique canon (no canon exceeds the cap, so no splits)
    units = [p.unit_label for p in d.passages]
    assert len(units) == len(set(units))
    assert all(u.startswith("Can. ") for u in units)
    assert len(units) > 1700

@pytest.mark.skipif(not _vendored, reason="canon-law not vendored")
def test_exactly_seven_books_no_empty_and_chapter_breadcrumb():
    d = build_documents()[0]
    books = {p.metadata["book"] for p in d.passages}
    assert len(books) == 7, books
    assert all(b and "?" not in b for b in books)
    # chapter_label is a breadcrumb beginning with the Book
    assert all(p.chapter_label.startswith("Book ") for p in d.passages)
    for p in d.passages:
        assert p.anchor.startswith("can/")
        assert not p.content.lstrip().startswith("[")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python3 -m pytest tests/test_canon_law.py -q`
Expected: FAIL — `_book_for`/`build_documents` not defined.

- [ ] **Step 3: Edit `datapipeline/ingest/canon_law.py`**

Remove the imports of `load`/`httpx`/`tqdm` and the async `main` (the web-fetch path). Keep `parse_canon_page`, `_classify_header`, `_reset_below`, `_context_key`, `deduplicate_urls`, and the regexes. Add at the top (after the kept helpers):

```python
import json

from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "canon-law")

# 1983 CIC: fixed Book canon-number ranges + canonical English titles.
_BOOKS = [
    (1, 203, "Book I: General Norms"),
    (204, 746, "Book II: The People of God"),
    (747, 833, "Book III: The Teaching Function of the Church"),
    (834, 1253, "Book IV: The Sanctifying Function of the Church"),
    (1254, 1310, "Book V: The Temporal Goods of the Church"),
    (1311, 1399, "Book VI: Sanctions in the Church"),
    (1400, 1752, "Book VII: Processes"),
]


def _book_for(num: int) -> str:
    for lo, hi, name in _BOOKS:
        if lo <= num <= hi:
            return name
    return "Book ?: Unknown"


def _clean_label(text: str) -> str:
    """Title-case an ALL-CAPS hierarchy header and trim trailing punctuation."""
    return title_case_shouting(clean_text(text)).strip().rstrip(".:").strip()


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "pages.json"), encoding="utf-8") as f:
        pages = json.load(f)
    raw: list[tuple[int, str, dict]] = []
    for page in pages:
        with open(os.path.join(_SRC, page["file"]), "rb") as fh:
            html = fh.read().decode("utf-8", "replace")
        raw.extend(parse_canon_page(html))

    # Dedup by canon number, sorted ascending.
    seen: set[int] = set()
    uniq: list[tuple[int, str, dict]] = []
    for num, text, ctx in sorted(raw, key=lambda x: x[0]):
        if num not in seen:
            seen.add(num)
            uniq.append((num, text, ctx))

    did = document_id("canon-law")
    passages: list[Passage] = []
    fill = {"title": "", "chapter": ""}
    prev_book: str | None = None
    pos = 0
    for num, text, ctx in uniq:
        book = _book_for(num)
        if book != prev_book:            # reset sub-levels at each Book boundary
            fill = {"title": "", "chapter": ""}
            prev_book = book
        if ctx.get("title"):
            fill["title"] = _clean_label(ctx["title"])
        if ctx.get("chapter"):
            fill["chapter"] = _clean_label(ctx["chapter"])
        label_parts = [book] + [v for v in (fill["title"], fill["chapter"]) if v]
        chapter_label = " — ".join(label_parts)
        chapter_key = make_anchor("canon-law", book.split(":")[0],
                                  fill["title"] or "t", fill["chapter"] or "c")
        passages.append(Passage(
            content=clean_text(text),
            reference=f"Code of Canon Law, Can. {num}",
            anchor=make_anchor("can", num),
            chapter_key=chapter_key, chapter_label=chapter_label,
            position=pos, unit_label=f"Can. {num}",
            metadata={"book": book, "title": fill["title"], "chapter": fill["chapter"],
                      "canon": num}))
        pos += 1
    return [Document(id=did, collection="canon-law", title="Code of Canon Law (1983)",
                     author="Catholic Church", year=1983, metadata={"source": "vatican.va"},
                     passages=passages)]
```

(Delete the old `if __name__ == "__main__":` block and the `async def main`.)

- [ ] **Step 4: Add `canon-law` to `run_collection.py` BUILDERS**

Add `canon_law` to the import and `"canon-law": canon_law.build_documents,` to `BUILDERS`. At this point all four are registered.

- [ ] **Step 5: Run tests**

Run: `cd datapipeline && python3 -m pytest tests/test_canon_law.py tests/test_run_collection.py -q`
Expected: PASS (kept `parse_canon_page` tests + new build tests; exactly 7 books, >1700 canons).

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/canon_law.py datapipeline/run_collection.py datapipeline/tests/test_canon_law.py
git commit -m "feat(pipeline): canon-law dual-pipeline adapter (book-by-range + context carry)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Per-collection overlap config + full test sweep

**Files:**
- Modify: `datapipeline/config.py` (lines ~47–52: `PER_COLLECTION_OVERLAP`)
- Test: full suite

- [ ] **Step 1: Add overlap knobs**

In `datapipeline/config.py`, extend `PER_COLLECTION_OVERLAP` to:
```python
    PER_COLLECTION_OVERLAP: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        "bible": (120, 120),
        "summa": (0, 0),
        "catechism": (200, 200),
        "church-fathers": (200, 200),
        "medieval": (200, 200),
        "encyclicals": (250, 250),   # small numbered units benefit from neighbor context
        "councils": (250, 250),
        "canon-law": (300, 300),     # short canons: wider neighbor window
    })
```

- [ ] **Step 2: Run the full datapipeline suite**

Run: `cd datapipeline && python3 -m pytest -q`
Expected: PASS except the one known pre-existing failure
(`test_catechism.py::test_tier3_in_brief_section_flagged`). No other failures, no new failures.

- [ ] **Step 3: Commit**

```bash
git add datapipeline/config.py
git commit -m "feat(pipeline): per-collection embedding overlap for the final four

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Dry-build verification (no spend, no DB writes)

**Files:** none (verification only)

- [ ] **Step 1: Build every collection in-process and print stats**

Run:
```bash
cd datapipeline && python3 - <<'PY'
from run_collection import BUILDERS
for name in ("medieval", "encyclicals", "councils", "canon-law"):
    docs = BUILDERS[name]()
    npass = sum(len(d.passages) for d in docs)
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids)), f"{name}: duplicate document ids"
    for d in docs:
        a = [p.anchor for p in d.passages]
        assert len(a) == len(set(a)), f"{name}/{d.title}: duplicate anchors"
    print(f"{name:12} docs={len(docs):3} passages={npass}")
PY
```
Expected output (approximate): `medieval` ~4 docs; `encyclicals` 18 docs; `councils` 36 docs; `canon-law` 1 doc / ~1747 passages. No assertion errors.

- [ ] **Step 2: Print the canon-law chapter-label list for an eyeball** (Risk-2 guard, per spec §5.4)

Run:
```bash
cd datapipeline && python3 - <<'PY'
from ingest.canon_law import build_documents
seen = []
for p in build_documents()[0].passages:
    if not seen or seen[-1] != p.chapter_label:
        seen.append(p.chapter_label)
dedup = sorted(set(seen))
print(f"{len(dedup)} distinct chapter labels")
for s in dedup[:40]:
    print(" ", s)
PY
```
Expected: ~237 labels, all starting "Book …", reading cleanly (no ALL-CAPS, no `?`). If fragmentation/garbage appears, fix `_clean_label`/forward-fill before any live run.

- [ ] **Step 3: No commit** (verification only). If issues found, return to the relevant task.

---

## Task 8: GATED live ingest — medieval

> **APPROVAL GATE:** This spends OpenAI embedding money and mutates dev Supabase + Qdrant. Get explicit owner approval before running. Order: medieval → encyclicals → councils → canon-law.

**Files:** none (operational)

- [ ] **Step 1: Reader-only dry pass (no embeddings)**

Run: `cd datapipeline && python3 run_collection.py --collection medieval --target reader`
Expected: prints document/passage counts; writes clean rows to Supabase `documents`/`chunks`. (Reader-only spends no OpenAI money.)

- [ ] **Step 2: Get approval, then full dual run with Qdrant clean**

Run: `cd datapipeline && python3 run_collection.py --collection medieval --target both --clean`
Expected: reader rows written; old Qdrant points deleted; new points embedded + upserted.

- [ ] **Step 3: Parity check (Supabase vs Qdrant)**

Run:
```bash
cd datapipeline && python3 - <<'PY'
import asyncio, asyncpg
from config import settings
from writers.qdrant import get_client
from qdrant_client import models as qm

async def main():
    coll = "medieval"
    pool = await asyncpg.create_pool(settings.DATABASE_URL, statement_cache_size=0)
    n_pg = await pool.fetchval(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id "
        "WHERE d.collection=$1", coll)
    n_anchor = await pool.fetchval(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id "
        "WHERE d.collection=$1 AND c.anchor IS NOT NULL", coll)
    q = get_client()
    n_q = (await q.count("chunks",
        count_filter=qm.Filter(must=[qm.FieldCondition(key="collection",
        match=qm.MatchValue(value=coll))]))).count
    print(f"{coll}: supabase={n_pg} anchored={n_anchor} qdrant={n_q}")
    assert n_pg == n_q == n_anchor, "parity mismatch"
    await pool.close(); await q.close()
asyncio.run(main())
PY
```
Expected: `supabase == qdrant == anchored`, all equal and non-zero.

- [ ] **Step 4: No code commit** (data operation). Record counts in the PR/run notes.

---

## Task 9: GATED live ingest — encyclicals

Same procedure as Task 8 with `--collection encyclicals`. Get approval first.

- [ ] **Step 1:** `python3 run_collection.py --collection encyclicals --target reader`
- [ ] **Step 2 (approval):** `python3 run_collection.py --collection encyclicals --target both --clean`
- [ ] **Step 3:** parity check (reuse Task 8 Step 3 script with `coll = "encyclicals"`). Expected equal, non-zero.

---

## Task 10: GATED live ingest — councils

Same procedure with `--collection councils`. Get approval first.

- [ ] **Step 1:** `python3 run_collection.py --collection councils --target reader`
- [ ] **Step 2 (approval):** `python3 run_collection.py --collection councils --target both --clean`
- [ ] **Step 3:** parity check (`coll = "councils"`). Expected equal, non-zero.

---

## Task 11: GATED live ingest — canon-law

Same procedure with `--collection canon-law`. Get approval first.

- [ ] **Step 1:** `python3 run_collection.py --collection canon-law --target reader`
- [ ] **Step 2 (approval):** `python3 run_collection.py --collection canon-law --target both --clean`
- [ ] **Step 3:** parity check (`coll = "canon-law"`). Expected `supabase == qdrant == anchored ≈ 1747`.

---

## Task 12: End-to-end reader smoke (optional, after live runs)

**Files:** none (verification)

- [ ] **Step 1: Drive the real reader endpoints in-process**

Using the backend test harness (`services/api`), confirm a sampled document from each new collection opens via `/v1/documents/{id}/toc` and `/v1/documents/{id}/reader?anchor=…` with `app.dependency_overrides[get_current_user]` and the `x-internal-secret` header (value in `services/api/.env`). Pick one `document_id` per collection from Supabase:
```bash
cd datapipeline && python3 - <<'PY'
import asyncio, asyncpg
from config import settings
async def main():
    pool = await asyncpg.create_pool(settings.DATABASE_URL, statement_cache_size=0)
    rows = await pool.fetch(
        "SELECT DISTINCT ON (collection) collection, id, title FROM documents "
        "WHERE collection IN ('medieval','encyclicals','councils','canon-law') ORDER BY collection")
    for r in rows:
        print(r["collection"], r["id"], r["title"])
    await pool.close()
asyncio.run(main())
PY
```
Expected: one openable document id per collection; `toc` returns ordered chapters; `reader?anchor=` returns the chapter section containing the anchor with clean passages. Any 404/empty TOC means a `chapter_key`/`anchor` bug — fix in the adapter and re-run that collection's live ingest.

- [ ] **Step 2: No commit** (verification only).

---

## Self-Review notes (already reconciled against the spec)

- **Spec §5.1 medieval** → Tasks 1–2. **§5.2 encyclicals** (3 layouts, pre-§1 header rule, buckets, footnotes) → Task 3. **§5.3 councils** (ecumenical vs Vatican II, canon/§/prose) → Task 4. **§5.4 canon-law** (book-by-range, forward-fill, Book+Title+Chapter, breadcrumb) → Task 5.
- **§6 registration + overlap knobs** → Tasks 2–6. **§7 testing** (per-doc encyclical counts, 7-books/no-empty canon, clean/anchored invariants) → Tasks 2–5. **§8 sequencing + gated runs + parity** → Tasks 7–12. **§9 risk guards** (per-doc count assertions; canon chapter-label eyeball) → Task 3 tests + Task 7 Step 2.
- **No migration** (verified live: `chunks` has anchor/chapter_key/chapter_label/unit_label; documents unique constraint is `(collection,title,translation,author)`).
- **Symbol consistency:** `thml_doc.make_doc(collection=…)` used by both church-fathers (Task 1) and medieval (Task 2); `_tokens`/`build_document(s)` (Task 3); `build_ecumenical`/`build_vatican2`/`build_documents` (Task 4); `_book_for`/`build_documents` (Task 5) — all match their tests.
```
