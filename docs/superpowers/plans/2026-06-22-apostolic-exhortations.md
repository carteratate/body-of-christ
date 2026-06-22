# Apostolic Exhortations Collection Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `apostolic-exhortations` as a new collection containing 32 papal apostolic exhortations from Pius X (1908) through Leo XIV (2025).

**Architecture:** Clone the encyclicals pipeline pattern — same HTML parser, same vendor/ingest/writer chain. New collection slug, new source directory, new ingest module, new vendor list. Evangelii Nuntiandi (Paul VI) and Evangelii Gaudium (Francis) are intentionally excluded — they already exist in the `encyclicals` collection.

**Tech Stack:** Python, httpx, BeautifulSoup, asyncpg, qdrant-client, Next.js/TypeScript.

## Global Constraints

- Collection slug: `"apostolic-exhortations"` (hyphenated, consistent with `canon-law`, `church-fathers`)
- Color: `#c87840` (warm amber-brown, distinct from encyclicals `#e8c040`)
- Ingest script mirrors `ingest/encyclicals.py` — only the collection name and `_SRC` path differ
- Vendor list excludes Evangelii Nuntiandi and Evangelii Gaudium (already in encyclicals)
- Run all commands from `datapipeline/` with `.venv/bin/python`

---

## File Map

| File | Change |
|---|---|
| `services/api/app/rag/constants.py` | Add `"apostolic-exhortations"` to `VALID_COLLECTIONS` |
| `apps/web/src/app/globals.css` | Add `--color-collection-apostolic-exhortations` CSS var |
| `apps/web/src/lib/collections.ts` | Add entry to `COLLECTIONS` array |
| `datapipeline/ingest/apostolic_exhortations.py` | New — copy of encyclicals.py with collection name changed |
| `datapipeline/scripts/vendor_sources.py` | Add `APOSTOLIC_EXHORTATIONS` list + `vendor_apostolic_exhortations()` + VENDORS entry |
| `datapipeline/run_collection.py` | Add import + BUILDERS entry |
| `datapipeline/tests/test_apostolic_exhortations.py` | New test file |

---

### Task 1: Register the new collection in backend and frontend

**Files:**
- Modify: `services/api/app/rag/constants.py`
- Modify: `apps/web/src/app/globals.css`
- Modify: `apps/web/src/lib/collections.ts`

- [ ] **Step 1: Add to constants.py**

```python
VALID_COLLECTIONS: frozenset[str] = frozenset({
    "bible",
    "catechism",
    "church-fathers",
    "encyclicals",
    "canon-law",
    "summa",
    "medieval",
    "councils",
    "apostolic-exhortations",
    "papal-documents",
})
```

- [ ] **Step 2: Add CSS variable to globals.css**

Add inside the `:root` block after `--color-collection-councils`:
```css
  --color-collection-apostolic-exhortations: #c87840;
  --color-collection-papal-documents:        #6070c8;
```

(Adding both new collections at once since they're adjacent changes.)

- [ ] **Step 3: Add to collections.ts**

```typescript
export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",                    label: "Bible",                    color: "var(--color-collection-bible)",                    hex: "#d4885a" },
  { key: "catechism",                label: "Catechism",                color: "var(--color-collection-catechism)",                hex: "#5b9bd4" },
  { key: "summa",                    label: "Summa Theologica",         color: "var(--color-collection-summa)",                    hex: "#55cc88" },
  { key: "encyclicals",              label: "Encyclicals",              color: "var(--color-collection-encyclicals)",              hex: "#e8c040" },
  { key: "apostolic-exhortations",   label: "Apostolic Exhortations",   color: "var(--color-collection-apostolic-exhortations)",   hex: "#c87840" },
  { key: "papal-documents",          label: "Papal Documents",          color: "var(--color-collection-papal-documents)",          hex: "#6070c8" },
  { key: "councils",                 label: "Councils",                 color: "var(--color-collection-councils)",                 hex: "#60d4c8" },
  { key: "church-fathers",           label: "Church Fathers",           color: "var(--color-collection-church-fathers)",           hex: "#b070d4" },
  { key: "medieval",                 label: "Medieval",                 color: "var(--color-collection-medieval)",                 hex: "#90a0a8" },
  { key: "canon-law",                label: "Canon Law",                color: "var(--color-collection-canon-law)",                hex: "#e84040" },
];
```

---

### Task 2: Create the ingest module

**Files:**
- Create: `datapipeline/ingest/apostolic_exhortations.py`

- [ ] **Step 1: Create the ingest module**

This is identical to `ingest/encyclicals.py` with two lines changed — the `_SRC` path and the `collection=` argument in `build_document()`.

```python
"""Apostolic exhortations ingestion (dual pipeline).

Mirrors the encyclicals ingest exactly — same HTML parser, same numbered-paragraph
tokenizer. One Document per exhortation; one Passage per numbered paragraph.
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

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "apostolic-exhortations")
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
    did = document_id("apostolic-exhortations", slug)
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

    return Document(id=did, collection="apostolic-exhortations", title=title, author=author,
                    year=entry["year"], metadata={"url": entry["url"], "pope": author},
                    passages=passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e) for e in manifest]
```

---

### Task 3: Add vendor list and function

**Files:**
- Modify: `datapipeline/scripts/vendor_sources.py`

- [ ] **Step 1: Add APOSTOLIC_EXHORTATIONS list and vendor function**

Add after the ENCYCLICALS block and before COUNCILS:

```python
APOSTOLIC_EXHORTATIONS = [
    # Pope Pius X
    ("Haerent Animo",               "Pope Pius X",       1908, "https://www.papalencyclicals.net/pius10/p10haer.htm"),
    # Pope Pius XII
    ("Menti Nostrae",               "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12clerg.htm"),
    # Pope Paul VI
    ("Signum Magnum",               "Pope Paul VI",      1967, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19670513_signum-magnum.html"),
    ("Evangelica Testificatio",     "Pope Paul VI",      1971, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19710629_evangelica-testificatio.html"),
    ("Marialis Cultus",             "Pope Paul VI",      1974, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19740202_marialis-cultus.html"),
    ("Gaudete in Domino",           "Pope Paul VI",      1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19750509_gaudete-in-domino.html"),
    # Pope John Paul II
    ("Catechesi Tradendae",         "Pope John Paul II", 1979, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_16101979_catechesi-tradendae.html"),
    ("Familiaris Consortio",        "Pope John Paul II", 1981, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_19811122_familiaris-consortio.html"),
    ("Redemptionis Donum",          "Pope John Paul II", 1984, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_25031984_redemptionis-donum.html"),
    ("Reconciliatio et Paenitentia","Pope John Paul II", 1984, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_02121984_reconciliatio-et-paenitentia.html"),
    ("Christifideles Laici",        "Pope John Paul II", 1988, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_30121988_christifideles-laici.html"),
    ("Redemptoris Custos",          "Pope John Paul II", 1989, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_15081989_redemptoris-custos.html"),
    ("Pastores Dabo Vobis",         "Pope John Paul II", 1992, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_25031992_pastores-dabo-vobis.html"),
    ("Ecclesia in Africa",          "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_14091995_ecclesia-in-africa.html"),
    ("Vita Consecrata",             "Pope John Paul II", 1996, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_25031996_vita-consecrata.html"),
    ("A New Hope for Lebanon",      "Pope John Paul II", 1997, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_19970510_lebanon.html"),
    ("Ecclesia in America",         "Pope John Paul II", 1999, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_22011999_ecclesia-in-america.html"),
    ("Ecclesia in Asia",            "Pope John Paul II", 1999, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_06111999_ecclesia-in-asia.html"),
    ("Ecclesia in Oceania",         "Pope John Paul II", 2001, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_20011122_ecclesia-in-oceania.html"),
    ("Ecclesia in Europa",          "Pope John Paul II", 2003, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_20030628_ecclesia-in-europa.html"),
    ("Pastores Gregis",             "Pope John Paul II", 2003, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_20031016_pastores-gregis.html"),
    # Pope Benedict XVI
    ("Sacramentum Caritatis",       "Pope Benedict XVI", 2007, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20070222_sacramentum-caritatis.html"),
    ("Verbum Domini",               "Pope Benedict XVI", 2010, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20100930_verbum-domini.html"),
    ("Africae Munus",               "Pope Benedict XVI", 2011, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20111119_africae-munus.html"),
    ("Ecclesia in Medio Oriente",   "Pope Benedict XVI", 2012, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20120914_ecclesia-in-medio-oriente.html"),
    # Pope Francis
    ("Amoris Laetitia",             "Pope Francis",      2016, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20160319_amoris-laetitia.html"),
    ("Gaudete et Exsultate",        "Pope Francis",      2018, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20180319_gaudete-et-exsultate.html"),
    ("Christus Vivit",              "Pope Francis",      2019, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20190325_christus-vivit.html"),
    ("Querida Amazonia",            "Pope Francis",      2020, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20200202_querida-amazonia.html"),
    ("Laudate Deum",                "Pope Francis",      2023, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/20231004-laudate-deum.html"),
    ("C'est la confiance",          "Pope Francis",      2023, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/20231015-santateresa-delbambinogesu.html"),
    # Pope Leo XIV
    ("Dilexi te",                   "Pope Leo XIV",      2025, "https://www.vatican.va/content/leo-xiv/en/apost_exhortations/documents/20251004-dilexi-te.html"),
]
```

Add the vendor function after `vendor_encyclicals`:

```python
def vendor_apostolic_exhortations(force: bool) -> None:
    d = os.path.join(_SOURCES, "apostolic-exhortations")
    os.makedirs(d, exist_ok=True)
    manifest = []
    seen_slugs: set[str] = set()
    with _client() as client:
        for title, author, year, url in APOSTOLIC_EXHORTATIONS:
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

Add to `VENDORS` dict:
```python
VENDORS = {
    "medieval": vendor_medieval,
    "encyclicals": vendor_encyclicals,
    "apostolic-exhortations": vendor_apostolic_exhortations,
    "councils": vendor_councils,
    "canon-law": vendor_canon_law,
}
```

---

### Task 4: Wire into run_collection.py and add tests

**Files:**
- Modify: `datapipeline/run_collection.py`
- Create: `datapipeline/tests/test_apostolic_exhortations.py`

- [ ] **Step 1: Add to run_collection.py**

```python
from ingest import (church_fathers, summa, bible, catechism, medieval,
                    encyclicals, councils, canon_law, apostolic_exhortations,
                    papal_documents)

BUILDERS = {
    "church-fathers": church_fathers.build_all,
    "summa": lambda: [summa.build_document()],
    "bible": bible.build_documents,
    "catechism": lambda: [catechism.build_document()],
    "medieval": medieval.build_documents,
    "encyclicals": encyclicals.build_documents,
    "councils": councils.build_documents,
    "canon-law": canon_law.build_documents,
    "apostolic-exhortations": apostolic_exhortations.build_documents,
    "papal-documents": papal_documents.build_documents,
}
```

- [ ] **Step 2: Create test file**

```python
# datapipeline/tests/test_apostolic_exhortations.py
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ingest.apostolic_exhortations import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "apostolic-exhortations")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))


@pytest.mark.skipif(not _vendored, reason="apostolic-exhortations not vendored")
def test_all_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 32
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"


@pytest.mark.skipif(not _vendored, reason="apostolic-exhortations not vendored")
def test_clean_anchored_no_footnote_markers():
    import re
    for d in build_documents():
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not re.search(r"\[\d+\]", p.content), f"footnote marker left in {d.title}"
```

- [ ] **Step 3: Vendor and run tests**

```bash
cd datapipeline && .venv/bin/python scripts/vendor_sources.py --collection apostolic-exhortations
QDRANT_URL="http://localhost:6333" QDRANT_API_KEY="test" .venv/bin/python -m pytest tests/test_apostolic_exhortations.py -v
```

Expected: `manifest.json (32 entries)`, tests pass.

- [ ] **Step 4: Ingest**

```bash
cd datapipeline && .venv/bin/python run_collection.py --collection apostolic-exhortations --target both --clean
```

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/constants.py apps/web/src/app/globals.css apps/web/src/lib/collections.ts \
  datapipeline/ingest/apostolic_exhortations.py datapipeline/scripts/vendor_sources.py \
  datapipeline/run_collection.py datapipeline/tests/test_apostolic_exhortations.py \
  docs/superpowers/plans/2026-06-22-apostolic-exhortations.md
git commit -m "feat(apostolic-exhortations): add new collection with 32 documents (Pius X through Leo XIV)"
```
