# Papal Documents Collection Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `papal-documents` as a new collection containing 15 curated apostolic letters and major papal bulls not already covered in other collections.

**Architecture:** Same pattern as apostolic-exhortations — mirrors the encyclicals pipeline. Ineffabilis Deus is excluded (already in encyclicals). Vatican II constitutions are excluded (already in councils).

**Tech Stack:** Python, httpx, BeautifulSoup, asyncpg, qdrant-client, Next.js/TypeScript.

## Global Constraints

- Collection slug: `"papal-documents"`
- Color: `#6070c8` (blue-purple, distinct from church-fathers `#b070d4`)
- `constants.py` and `collections.ts` updates are shared with the apostolic-exhortations plan — apply both at once
- Run all commands from `datapipeline/` with `.venv/bin/python`

---

## File Map

| File | Change |
|---|---|
| `datapipeline/ingest/papal_documents.py` | New — copy of apostolic_exhortations.py with collection name changed |
| `datapipeline/scripts/vendor_sources.py` | Add `PAPAL_DOCUMENTS` list + `vendor_papal_documents()` + VENDORS entry |
| `datapipeline/tests/test_papal_documents.py` | New test file |

(constants.py, globals.css, collections.ts, and run_collection.py are updated in the apostolic-exhortations plan — `"papal-documents"` is added there simultaneously.)

---

### Task 1: Create the ingest module

**Files:**
- Create: `datapipeline/ingest/papal_documents.py`

- [ ] **Step 1: Create the ingest module**

Identical to `apostolic_exhortations.py` with `"papal-documents"` substituted for `"apostolic-exhortations"` in `_SRC` and `collection=`:

```python
"""Papal documents ingestion (apostolic letters + historical bulls).

Mirrors the encyclicals/apostolic_exhortations ingest — same numbered-paragraph
HTML parser. One Document per letter/bull; one Passage per numbered paragraph.
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
from normalize.boilerplate import strip_boilerplate
from ingest.common import split_at_sentences, _split_at_whitespace

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "papal-documents")
_NUM = re.compile(r"^(\d+)\s*\.\s*(.*)", re.DOTALL)
_ROMAN = re.compile(r"^[IVX]+\.\s+\S")
_BUCKET = 20
_CHROME = re.compile(
    r"automatically notified|more information about this site|fan of our facebook"
    r"|^search tips$|^sitemap$|return to (?:the )?home", re.IGNORECASE)


def _strip_leading_caps(text: str) -> str:
    words = text.split()
    i = 0
    while i < len(words):
        letters = [c for c in words[i] if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            i += 1
        else:
            break
    return " ".join(words[i:])


def _is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.7


def _is_bold_only(p) -> bool:
    kids = [c for c in p.children if getattr(c, "name", None)]
    bare = "".join(str(c) for c in p.children if not getattr(c, "name", None)).strip()
    t = p.get_text(strip=True)
    return (len(kids) == 1 and kids[0].name in ("b", "strong")
            and not bare and len(t) >= 8 and not t.endswith(":"))


def _tokens(soup) -> list[tuple[str, int | None, str]]:
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    items = [(p, p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    items = [(p, t) for p, t in items if t and not _CHROME.search(t)]
    toks: list[tuple[str, int | None, str]] = []
    seen = False
    cur: list | None = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            toks.append(("para", cur[0], "\n\n".join(x for x in cur[1] if x)))
            cur = None

    for p, t in items:
        m = _NUM.match(t)
        is_roman = bool(_ROMAN.match(t))
        is_bold = _is_bold_only(p)
        if not seen:
            if m:
                seen = True
                body = m.group(2).strip()
                cur = [int(m.group(1)), [body] if body else []]
            elif is_roman:
                toks.append(("section", None, t))
            else:
                toks.append(("preamble", None, t))
            continue
        if m:
            flush()
            body = m.group(2).strip()
            cur = [int(m.group(1)), [body] if body else []]
            continue
        if is_roman or is_bold:
            flush()
            toks.append(("section", None, t))
            continue
        if cur is not None:
            cur[1].append(t)
    flush()
    cleaned: list[tuple[str, int | None, str]] = []
    for i, tok in enumerate(toks):
        if tok[0] == "section":
            following = toks[i + 1:]
            nxt_sec = next((j for j, x in enumerate(following) if x[0] == "section"), len(following))
            if not any(x[0] == "para" for x in following[:nxt_sec]):
                continue
        cleaned.append(tok)
    return cleaned


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
    did = document_id("papal-documents", slug)
    has_sec = any(k == "section" for k, _, _ in toks)
    meta = {"pope": author, "url": entry["url"]}
    passages: list[Passage] = []
    pos = 0
    seen_anchors: set[str] = set()

    def emit(content: str, ref: str, base_anchor: str, ckey: str, clabel: str,
             unit: str | None) -> None:
        nonlocal pos
        content = clean_text(strip_footnote_markers(strip_boilerplate(content)))
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

    pre_parts: list[str] = []
    for k, _, t in toks:
        if k != "preamble":
            continue
        if _is_shouting(t):
            break
        pre_parts.append(t)
    pre = _strip_leading_caps("\n\n".join(pre_parts).strip()).strip()
    if pre:
        emit(pre, f"{title} — Preamble", make_anchor(slug, "preamble"),
             make_anchor(slug, "preamble"), "Preamble", None)

    bucket_range: dict[int, tuple[int, int]] = {}
    if not has_sec:
        for k, n, _ in toks:
            if k != "para":
                continue
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range.get(b, (n, n))
            bucket_range[b] = (min(lo, n), max(hi, n))

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
        if has_sec:
            if cur_key is None:
                cur_key, cur_label = make_anchor(slug, "sec-0"), "Introduction"
            ckey, clabel = cur_key, cur_label
        else:
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range[b]
            clabel = f"Paragraphs {lo}–{hi}" if lo != hi else f"Paragraph {lo}"
            ckey = make_anchor(slug, f"bucket-{b}")
        emit(t, f"{title}, §{n}", make_anchor(slug, n), ckey, clabel, f"§{n}")

    return Document(id=did, collection="papal-documents", title=title, author=author,
                    year=entry["year"], metadata={"url": entry["url"], "pope": author},
                    passages=passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e) for e in manifest]
```

---

### Task 2: Add vendor list, function, and tests

**Files:**
- Modify: `datapipeline/scripts/vendor_sources.py`
- Create: `datapipeline/tests/test_papal_documents.py`

- [ ] **Step 1: Add PAPAL_DOCUMENTS list and vendor function to vendor_sources.py**

```python
PAPAL_DOCUMENTS = [
    # Historical Papal Bulls
    ("Unam Sanctam",               "Pope Boniface VIII",  1302, "https://www.papalencyclicals.net/bon08/b8unam.htm"),
    ("Exsurge Domine",             "Pope Leo X",          1520, "https://www.papalencyclicals.net/leo10/l10exdom.htm"),
    ("Sublimis Deus",              "Pope Paul III",       1537, "https://www.papalencyclicals.net/paul03/p3subli.htm"),
    # Apostolic Letters — John Paul II
    ("Salvifici Doloris",          "Pope John Paul II",   1984, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1984/documents/hf_jp-ii_apl_11021984_salvifici-doloris.html"),
    ("Mulieris Dignitatem",        "Pope John Paul II",   1988, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1988/documents/hf_jp-ii_apl_15081988_mulieris-dignitatem.html"),
    ("Ordinatio Sacerdotalis",     "Pope John Paul II",   1994, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1994/documents/hf_jp-ii_apl_19940522_ordinatio-sacerdotalis.html"),
    ("Tertio Millennio Adveniente","Pope John Paul II",   1994, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1994/documents/hf_jp-ii_apl_19941110_tertio-millennio-adveniente.html"),
    ("Orientale Lumen",            "Pope John Paul II",   1995, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1995/documents/hf_jp-ii_apl_19950502_orientale-lumen.html"),
    ("Dies Domini",                "Pope John Paul II",   1998, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1998/documents/hf_jp-ii_apl_05071998_dies-domini.html"),
    ("Novo Millennio Ineunte",     "Pope John Paul II",   2001, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/2001/documents/hf_jp-ii_apl_20010106_novo-millennio-ineunte.html"),
    ("Rosarium Virginis Mariae",   "Pope John Paul II",   2002, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/2002/documents/hf_jp-ii_apl_20021016_rosarium-virginis-mariae.html"),
    # Apostolic Letters — Benedict XVI
    ("Ubicumque et Semper",        "Pope Benedict XVI",   2010, "https://www.vatican.va/content/benedict-xvi/en/apost_letters/documents/hf_ben-xvi_apl_20100921_ubicumque-et-semper.html"),
    ("Porta Fidei",                "Pope Benedict XVI",   2011, "https://www.vatican.va/content/benedict-xvi/en/motu_proprio/documents/hf_ben-xvi_motu-proprio_20111011_porta-fidei.html"),
    # Apostolic Letters — Francis
    ("Misericordia et Misera",     "Pope Francis",        2016, "https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco-lettera-ap_20161120_misericordia-et-misera.html"),
    ("Patris Corde",               "Pope Francis",        2020, "https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco-lettera-ap_20201208_patris-corde.html"),
]


def vendor_papal_documents(force: bool) -> None:
    d = os.path.join(_SOURCES, "papal-documents")
    os.makedirs(d, exist_ok=True)
    manifest = []
    seen_slugs: set[str] = set()
    with _client() as client:
        for title, author, year, url in PAPAL_DOCUMENTS:
            base_slug = _slug(title)
            slug = base_slug if base_slug not in seen_slugs else f"{base_slug}-{year}"
            seen_slugs.add(slug)
            fname = slug + ".html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"title": title, "author": author, "year": year,
                             "url": url, "slug": slug, "file": fname})
    _write_manifest(d, manifest)
```

Add to VENDORS dict:
```python
VENDORS = {
    "medieval": vendor_medieval,
    "encyclicals": vendor_encyclicals,
    "apostolic-exhortations": vendor_apostolic_exhortations,
    "papal-documents": vendor_papal_documents,
    "councils": vendor_councils,
    "canon-law": vendor_canon_law,
}
```

- [ ] **Step 2: Create test file**

```python
# datapipeline/tests/test_papal_documents.py
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ingest.papal_documents import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "papal-documents")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))


@pytest.mark.skipif(not _vendored, reason="papal-documents not vendored")
def test_all_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 15
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"


@pytest.mark.skipif(not _vendored, reason="papal-documents not vendored")
def test_clean_anchored_no_footnote_markers():
    import re
    for d in build_documents():
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not re.search(r"\[\d+\]", p.content), f"footnote marker left in {d.title}"
```

- [ ] **Step 3: Vendor, test, and ingest**

```bash
cd datapipeline && .venv/bin/python scripts/vendor_sources.py --collection papal-documents
QDRANT_URL="http://localhost:6333" QDRANT_API_KEY="test" .venv/bin/python -m pytest tests/test_papal_documents.py -v
.venv/bin/python run_collection.py --collection papal-documents --target both --clean
```

- [ ] **Step 4: Commit**

```bash
git add datapipeline/ingest/papal_documents.py datapipeline/scripts/vendor_sources.py \
  datapipeline/tests/test_papal_documents.py \
  docs/superpowers/plans/2026-06-22-papal-documents.md
git commit -m "feat(papal-documents): add new collection with 15 apostolic letters and historical bulls"
```
