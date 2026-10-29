# Councils Collection Ingestion Plan

> **Superseded implementation plan.** Preserve this file as history; do not execute its
> commands. Use [`datapipeline/README.md`](../../../datapipeline/README.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "councils" corpus collection containing all 21 Ecumenical Councils, scraping Councils 1–20 from papalencyclicals.net and the 16 Vatican II documents from vatican.va, with one DB document row per council (or per Vatican II document), chunked structurally by canon groups and session/decree sections.

**Architecture:** A `councils.py` script with two parsers: `parse_council_page()` for papalencyclicals.net HTML (numbered canons → accumulated groups, section headers → new chunks), and `parse_vatican2_doc()` for vatican.va numbered-paragraph documents (same accumulation strategy as encyclicals.py). Vatican II documents each get their own `documents` row with `metadata.council = "Vatican II"` and `metadata.document_type`. The script uses httpx with 1.5s politeness delay. Collection registered in constants, collections.ts, and globals.css.

**Tech Stack:** Python asyncio, httpx, BeautifulSoup (lxml), asyncpg, Next.js/TypeScript (constants only).

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Modify | `services/api/app/rag/constants.py` | Add `"councils"` |
| Modify | `apps/web/src/lib/collections.ts` | Add councils entry |
| Modify | `apps/web/src/app/globals.css` | Add CSS var |
| Create | `datapipeline/ingest/councils.py` | Ingest script |
| Create | `datapipeline/tests/test_councils.py` | Unit tests |
| Modify | `datapipeline/run_all.py` | Add councils to PIPELINE |

---

## Task 1: Register "councils" collection across the stack

**Files:**
- Modify: `services/api/app/rag/constants.py`
- Modify: `apps/web/src/lib/collections.ts`
- Modify: `apps/web/src/app/globals.css`

- [ ] **Step 1: Add to backend constants**

`services/api/app/rag/constants.py` complete file after change (note: if medieval plan was already applied, "medieval" will already be present):

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
})
```

- [ ] **Step 2: Add CSS variable**

In `apps/web/src/app/globals.css`, inside the `@theme` block after the `--color-collection-medieval` line (add that line if the medieval plan hasn't run yet):

```css
  --color-collection-councils:       #4A7070;
```

- [ ] **Step 3: Add to frontend collection list**

In `apps/web/src/lib/collections.ts`, add after `medieval` (or after `summa` if medieval plan hasn't run):

```typescript
export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "📖 Bible",           color: "var(--color-collection-bible)" },
  { key: "catechism",      label: "⛪ Catechism",        color: "var(--color-collection-catechism)" },
  { key: "church-fathers", label: "✝ Church Fathers",   color: "var(--color-collection-church-fathers)" },
  { key: "encyclicals",    label: "📜 Encyclicals",      color: "var(--color-collection-encyclicals)" },
  { key: "canon-law",      label: "⚖️ Canon Law",        color: "var(--color-collection-canon-law)" },
  { key: "summa",          label: "📚 Summa Theologica", color: "var(--color-collection-summa)" },
  { key: "medieval",       label: "🏰 Medieval",         color: "var(--color-collection-medieval)" },
  { key: "councils",       label: "⚜️ Councils",          color: "var(--color-collection-councils)" },
];
```

- [ ] **Step 4: TypeScript check**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/constants.py apps/web/src/lib/collections.ts apps/web/src/app/globals.css
git commit -m "feat(councils): register councils collection in constants and frontend"
```

---

## Task 2: Write tests for parse_council_page (TDD)

**Files:**
- Create: `datapipeline/tests/test_councils.py`

- [ ] **Step 1: Create the test file**

```python
# datapipeline/tests/test_councils.py
import sys, os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.councils import parse_council_page, parse_vatican2_doc


# ── Fixtures ─────────────────────────────────────────────────────────────────

SIMPLE_COUNCIL_HTML = """<html><body>
<h1>Council of Nicaea — 325 A.D.</h1>
<h3>Introduction</h3>
<p>The Council of Nicaea was convoked by Constantine in 325 AD to resolve the Arian controversy and define orthodox Christian teaching about the nature of Christ.</p>
<h3>Canons</h3>
<p>Canon 1: If anyone in sickness has undergone surgery at the hands of physicians or has been castrated by barbarians, let him remain among the clergy.</p>
<p>Canon 2: If anyone has recently joined the faith and been catechized briefly, or if he has changed directly from a dissolute life, it is not right for him to be immediately promoted to bishop, priest, or deacon.</p>
<p>Canon 3: The great Synod strictly forbids bishops, priests, and deacons to have with them a woman who has been introduced to live with them, with the exception of a mother or sister or aunt.</p>
</body></html>"""

LONG_COUNCIL_HTML = """<html><body>
<h1>Council of Trent</h1>
<h3>Session VI — Decree on Justification</h3>
""" + "\n".join(
    f"<p>Canon {i}: {'This is a substantial canon with enough content to matter for chunking. ' * 5}</p>"
    for i in range(1, 25)
) + """
<h3>Session VII — Canons on the Sacraments</h3>
<p>Canon 1: If anyone says that the sacraments of the New Law were not all instituted by Jesus Christ our Lord, or that there are more or fewer than seven, let him be anathema.</p>
</body></html>"""

VAT2_HTML = """<html><body>
<h3>CHAPTER I</h3>
<h4>REVELATION ITSELF</h4>
<p>1. In His goodness and wisdom God chose to reveal Himself and to make known to us the hidden purpose of His will by which through Christ, the Word made flesh, man might have access to the Father in the Holy Spirit and come to share in the divine nature.</p>
<p>2. The most intimate truth which this revelation gives us about God and the salvation of man is made clear to us in Christ, Who is the Mediator and at the same time the fullness of all revelation.</p>
<h3>CHAPTER II</h3>
<h4>HOW DIVINE REVELATION IS HANDED ON</h4>
<p>3. God has seen to it that what He had revealed for the salvation of all nations would abide perpetually in its full integrity and be handed on to all generations.</p>
<p>4. Sacred tradition and Sacred Scripture form one sacred deposit of the word of God, committed to the Church.</p>
</body></html>"""


# ── parse_council_page ───────────────────────────────────────────────────────

def test_parse_council_page_returns_chunks():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    assert len(chunks) >= 1


def test_parse_council_page_chunk_is_4_tuple():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    content, ref, pos, meta = chunks[0]
    assert isinstance(content, str) and len(content) > 0
    assert isinstance(ref, str) and len(ref) > 0
    assert isinstance(pos, int)
    assert isinstance(meta, dict)


def test_parse_council_page_ref_includes_council_name():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    for _, ref, _, _ in chunks:
        assert "Council of Nicaea" in ref


def test_parse_council_page_metadata_has_council_and_year():
    chunks = parse_council_page(SIMPLE_COUNCIL_HTML, "Council of Nicaea", 325)
    for _, _, _, meta in chunks:
        assert meta["council"] == "Council of Nicaea"
        assert meta["year"] == 325


def test_parse_council_page_positions_are_sequential():
    chunks = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563)
    positions = [pos for _, _, pos, _ in chunks]
    assert positions == list(range(len(positions)))


def test_parse_council_page_no_chunk_exceeds_ceiling():
    chunks = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563)
    for content, _, _, _ in chunks:
        assert len(content) <= 4000  # ceiling is 3800, allow header overhead


def test_parse_council_page_section_creates_new_chunk():
    """A section header should start a new chunk boundary."""
    chunks = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563)
    refs = [ref for _, ref, _, _ in chunks]
    # Session VI and Session VII should appear in separate chunks
    session_6_refs = [r for r in refs if "Session VI" in r]
    session_7_refs = [r for r in refs if "Session VII" in r]
    assert len(session_6_refs) >= 1
    assert len(session_7_refs) >= 1


def test_parse_council_page_larger_target_produces_fewer_or_equal_chunks():
    """target=2500 should produce no more chunks than target=2000 on the same text."""
    chunks_2000 = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563, target=2000)
    chunks_2500 = parse_council_page(LONG_COUNCIL_HTML, "Council of Trent", 1563, target=2500)
    assert len(chunks_2500) <= len(chunks_2000)


# ── parse_vatican2_doc ───────────────────────────────────────────────────────

def test_parse_vatican2_doc_returns_chunks():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    assert len(chunks) >= 1


def test_parse_vatican2_doc_metadata_has_council_and_type():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    for _, _, _, meta in chunks:
        assert meta["council"] == "Vatican II"
        assert meta["document_type"] == "constitution"
        assert meta["year"] == 1965


def test_parse_vatican2_doc_ref_includes_doc_title():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    for _, ref, _, _ in chunks:
        assert "Dei Verbum" in ref


def test_parse_vatican2_doc_positions_sequential():
    chunks = parse_vatican2_doc(VAT2_HTML, "Dei Verbum", "constitution", 1965)
    positions = [p for _, _, p, _ in chunks]
    assert positions == list(range(len(positions)))
```

- [ ] **Step 2: Run tests — confirm they FAIL**

```bash
cd datapipeline && .venv/bin/python3 -m pytest tests/test_councils.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'ingest.councils'`

- [ ] **Step 3: Commit**

```bash
git add datapipeline/tests/test_councils.py
git commit -m "test(councils): add failing tests for parse_council_page and parse_vatican2_doc"
```

---

## Task 3: Implement councils.py

**Files:**
- Create: `datapipeline/ingest/councils.py`

- [ ] **Step 1: Create the ingest script**

```python
# datapipeline/ingest/councils.py
"""Ecumenical Councils ingestion.

Scrapes papalencyclicals.net for Councils 1-20, and vatican.va for the 16
Vatican II documents. One DB document row per council (or Vatican II document).

Chunking:
  - Council pages: canon/paragraph accumulation with section header boundaries.
  - Vatican II docs: numbered-paragraph accumulation (same pattern as encyclicals.py).
"""
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

_DELAY = 1.5
_TARGET_EARLY = 2000   # Nicaea through Lateran V: short canons, denser packing
_TARGET_LATE  = 2500   # Trent, Vatican I, Vatican II: long doctrinal prose
_CEILING = 3800
_MIN_LENGTH = 40

# Councils 1–20: one document row each.
# (title, year, url, target)  — target controls chunk size per council.
COUNCILS: list[tuple[str, int, str, int]] = [
    ("Council of Nicaea",                    325,  "https://www.papalencyclicals.net/councils/ecum01.htm",  _TARGET_EARLY),
    ("First Council of Constantinople",      381,  "https://www.papalencyclicals.net/councils/ecum02.htm",  _TARGET_EARLY),
    ("Council of Ephesus",                   431,  "https://www.papalencyclicals.net/councils/ecum03.htm",  _TARGET_EARLY),
    ("Council of Chalcedon",                 451,  "https://www.papalencyclicals.net/councils/ecum04.htm",  _TARGET_EARLY),
    ("Second Council of Constantinople",     553,  "https://www.papalencyclicals.net/councils/ecum05.htm",  _TARGET_EARLY),
    ("Third Council of Constantinople",      681,  "https://www.papalencyclicals.net/councils/ecum06.htm",  _TARGET_EARLY),
    ("Second Council of Nicaea",             787,  "https://www.papalencyclicals.net/councils/ecum07.htm",  _TARGET_EARLY),
    ("Fourth Council of Constantinople",     870,  "https://www.papalencyclicals.net/councils/ecum08.htm",  _TARGET_EARLY),
    ("Lateran Councils I, II, and III",     1179,  "https://www.papalencyclicals.net/councils/ecum09-11.htm", _TARGET_EARLY),
    ("Fourth Lateran Council",              1215,  "https://www.papalencyclicals.net/councils/ecum12-2.htm",  _TARGET_EARLY),
    ("Councils of Lyons I and II",          1274,  "https://www.papalencyclicals.net/councils/ecum13-14.htm", _TARGET_EARLY),
    ("Councils of Vienne through Lateran V",1517,  "https://www.papalencyclicals.net/councils/ecum15-18.htm", _TARGET_EARLY),
    ("Council of Trent",                    1563,  "https://www.papalencyclicals.net/councils/trent.htm",    _TARGET_LATE),
    ("First Vatican Council",               1870,  "https://www.papalencyclicals.net/councils/ecum20.htm",   _TARGET_LATE),
]

# Vatican II: 16 documents, each gets its own DB row.
# (title, document_type, year, url)
VATICAN_II_DOCS: list[tuple[str, str, int, str]] = [
    ("Dei Verbum",             "constitution",  1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19651118_dei-verbum_en.html"),
    ("Lumen Gentium",          "constitution",  1964, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19641121_lumen-gentium_en.html"),
    ("Sacrosanctum Concilium", "constitution",  1963, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19631204_sacrosanctum-concilium_en.html"),
    ("Gaudium et Spes",        "constitution",  1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19651207_gaudium-et-spes_en.html"),
    ("Ad Gentes",              "decree",        1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651207_ad-gentes_en.html"),
    ("Presbyterorum Ordinis",  "decree",        1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651207_presbyterorum-ordinis_en.html"),
    ("Apostolicam Actuositatem","decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651118_apostolicam-actuositatem_en.html"),
    ("Optatam Totius",         "decree",        1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651028_optatam-totius_en.html"),
    ("Perfectae Caritatis",    "decree",        1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651028_perfectae-caritatis_en.html"),
    ("Christus Dominus",       "decree",        1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651028_christus-dominus_en.html"),
    ("Unitatis Redintegratio", "decree",        1964, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19641121_unitatis-redintegratio_en.html"),
    ("Orientalium Ecclesiarum","decree",        1964, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19641121_orientalium-ecclesiarum_en.html"),
    ("Inter Mirifica",         "decree",        1963, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19631204_inter-mirifica_en.html"),
    ("Gravissimum Educationis","declaration",   1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_gravissimum-educationis_en.html"),
    ("Nostra Aetate",          "declaration",   1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_nostra-aetate_en.html"),
    ("Dignitatis Humanae",     "declaration",   1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651207_dignitatis-humanae_en.html"),
]

_CANON_RE = re.compile(
    r"^(?:Canon|Can\.?)\s+(\d+|[IVXLCDM]+)[\.\:]?\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)
_NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)", re.DOTALL)


def parse_council_page(
    html: str,
    council_name: str,
    year: int,
    target: int = _TARGET_EARLY,
) -> list[tuple[str, str, int, dict]]:
    """Parse a papalencyclicals.net council page into chunks.

    Groups numbered canons/paragraphs up to `target` chars, starting a new chunk
    at each section header (h2/h3/h4). Returns (content, reference, position, metadata).
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    chunks: list[tuple[str, str, int, dict]] = []
    position = 0
    active_section: str | None = None
    acc: list[str] = []
    acc_len: int = 0

    def _flush() -> None:
        nonlocal position, acc, acc_len
        if not acc:
            return
        body = "\n\n".join(acc)
        if active_section:
            content = f"[{council_name} — {active_section}]\n\n{body}"
            ref = f"{council_name} — {active_section}"
        else:
            content = f"[{council_name}]\n\n{body}"
            ref = council_name
        chunks.append((content, ref, position, {
            "council": council_name,
            "section": active_section,
            "year": year,
        }))
        position += 1
        acc, acc_len = [], 0

    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
        text = elem.get_text(separator=" ", strip=True)
        if not text or len(text) < _MIN_LENGTH:
            continue

        tag = elem.name
        if tag in ("h2", "h3", "h4"):
            # Skip the page title heading
            if tag == "h1":
                continue
            if acc_len >= 100:
                _flush()
            active_section = text
            continue

        # Canon: "Canon 1: ..." or "Can. I: ..."
        m_canon = _CANON_RE.match(text)
        if m_canon:
            body = text
            if acc_len + len(body) > _CEILING:
                _flush()
            acc.append(body)
            acc_len += len(body)
            if acc_len >= target:
                _flush()
            continue

        # Numbered paragraph: "3. The synod decided..."
        m_num = _NUMBERED_RE.match(text)
        if m_num:
            body = m_num.group(2).strip()
            if len(body) < _MIN_LENGTH:
                continue
            if acc_len + len(body) > _CEILING:
                _flush()
            acc.append(body)
            acc_len += len(body)
            if acc_len >= target:
                _flush()
            continue

        # Plain paragraph (prose, introductions, letters)
        if len(text) >= _MIN_LENGTH:
            if acc_len + len(text) > _CEILING:
                _flush()
            acc.append(text)
            acc_len += len(text)
            if acc_len >= target:
                _flush()

    _flush()
    return chunks


def parse_vatican2_doc(
    html: str,
    title: str,
    document_type: str,
    year: int,
) -> list[tuple[str, str, int, dict]]:
    """Parse a Vatican II document from vatican.va into chunks.

    Documents use numbered paragraphs ("2. In His goodness...") and chapter
    headers (<strong>CHAPTER I</strong>). Accumulates paragraphs up to _TARGET
    chars, flushing at chapter boundaries.

    Returns (content, reference, position, metadata). Metadata always includes
    council="Vatican II" and document_type.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    chunks: list[tuple[str, str, int, dict]] = []
    position = 0
    active_chapter: str | None = None
    acc: list[tuple[int, str]] = []   # (para_num, text); para_num=-1 for overlap
    acc_len: int = 0

    def _flush() -> None:
        nonlocal position, acc, acc_len
        real = [(n, t) for n, t in acc if n != -1]
        if not real:
            acc, acc_len = [], 0
            return
        body = "\n\n".join(t for _, t in real)
        nums = [n for n, _ in real]
        num_str = f"§{nums[0]}–{nums[-1]}" if len(nums) > 1 else f"§{nums[0]}"
        chap_part = f" — {active_chapter}" if active_chapter else ""
        content = f"[{title}{chap_part}]\n\n{body}"
        ref = f"{title}{chap_part}, {num_str}"
        chunks.append((content, ref, position, {
            "council": "Vatican II",
            "document_type": document_type,
            "chapter": active_chapter,
            "para_range": [nums[0], nums[-1]],
            "year": year,
        }))
        position += 1
        acc, acc_len = [], 0

    # Vatican.va pages: chapter markers are <strong>CHAPTER N</strong> or
    # standalone <h3>/<h4> tags. Numbered paragraphs are plain text "N. body".
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p", "strong"]):
        text = elem.get_text(separator=" ", strip=True)
        if not text:
            continue

        # Chapter heading: "CHAPTER I" or "Chapter II" standalone in <h3>/<h4>/<strong>
        if re.match(r"^CHAPTER\s+[IVXLCDM]+$", text, re.IGNORECASE):
            if acc_len >= 100:
                _flush()
            active_chapter = text.title()  # "Chapter I"
            continue

        if elem.name in ("h3", "h4") and len(text) < 120:
            # Section sub-header within a chapter — flush and note but don't change chapter
            if acc_len >= 100:
                _flush()
            continue

        # Numbered paragraph: "2. In His goodness..."
        m = _NUMBERED_RE.match(text)
        if m:
            num = int(m.group(1))
            body = m.group(2).strip()
            if len(body) < _MIN_LENGTH:
                continue
            if acc_len + len(body) > _CEILING:
                _flush()
            acc.append((num, body))
            acc_len += len(body)
            if acc_len >= _TARGET_LATE:
                _flush()

    _flush()
    return chunks


async def main(pool) -> None:
    """Scrape and upsert all council documents."""
    total_chunks = 0

    with httpx.Client(timeout=30, follow_redirects=True) as client:

        # ── Councils 1–20 ────────────────────────────────────────────────────
        with tqdm(total=len(COUNCILS), unit="council", desc="Councils 1–20") as pbar:
            for council_number, (council_name, year, url, target) in enumerate(COUNCILS, start=1):
                pbar.set_postfix({"council": council_name[:30]})
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"\n  WARNING: {council_name}: {exc}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                chunks = parse_council_page(resp.text, council_name, year, target=target)
                if not chunks:
                    print(f"\n  WARNING: No chunks from {council_name}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                doc_id = await upsert_document(
                    pool,
                    collection="councils",
                    title=council_name,
                    translation="",
                    author=None,
                    year=year,
                    metadata={"source_url": url, "council_number": council_number},
                )

                for content, reference, position, meta in chunks:
                    await upsert_chunk(pool, doc_id, content, position, reference, metadata=meta)

                total_chunks += len(chunks)
                pbar.set_postfix({"council": council_name[:30], "chunks": len(chunks)})
                pbar.update(1)
                time.sleep(_DELAY)

        # ── Vatican II documents ─────────────────────────────────────────────
        with tqdm(total=len(VATICAN_II_DOCS), unit="doc", desc="Vatican II") as pbar:
            for doc_title, doc_type, year, url in VATICAN_II_DOCS:
                pbar.set_postfix({"doc": doc_title})
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"\n  WARNING: {doc_title}: {exc}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                chunks = parse_vatican2_doc(resp.text, doc_title, doc_type, year)
                if not chunks:
                    print(f"\n  WARNING: No chunks from {doc_title}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                doc_id = await upsert_document(
                    pool,
                    collection="councils",
                    title=doc_title,
                    translation="",
                    author=None,
                    year=year,
                    metadata={
                        "source_url": url,
                        "council": "Vatican II",
                        "document_type": doc_type,
                    },
                )

                for content, reference, position, meta in chunks:
                    await upsert_chunk(pool, doc_id, content, position, reference, metadata=meta)

                total_chunks += len(chunks)
                pbar.set_postfix({"doc": doc_title, "chunks": len(chunks)})
                pbar.update(1)
                time.sleep(_DELAY)

    print(f"  Done. {total_chunks} total chunks written for councils.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Step 2: Run the tests from Task 2 — they should all pass now**

```bash
cd datapipeline && .venv/bin/python3 -m pytest tests/test_councils.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add datapipeline/ingest/councils.py
git commit -m "feat(councils): councils.py ingest with structural canon/paragraph chunking and Vatican II support"
```

---

## Task 4: Wire councils into run_all.py

**Files:**
- Modify: `datapipeline/run_all.py`

- [ ] **Step 1: Add councils to PIPELINE**

```python
from ingest import bible, catechism, canon_law, encyclicals, church_fathers, summa, medieval, councils

PIPELINE: list[tuple[str, object]] = [
    ("bible",          bible),
    ("catechism",      catechism),
    ("canon-law",      canon_law),
    ("encyclicals",    encyclicals),
    ("church-fathers", church_fathers),
    ("summa",          summa),
    ("medieval",       medieval),
    ("councils",       councils),
]
```

- [ ] **Step 2: Verify import**

```bash
cd datapipeline && .venv/bin/python3 -c "import run_all; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add datapipeline/run_all.py
git commit -m "feat(councils): add councils to run_all.py pipeline"
```

---

## Task 5: Run ingestion and verify

- [ ] **Step 1: Dry-run a single council to check parsing**

```bash
cd datapipeline && .venv/bin/python3 -c "
import httpx
from ingest.councils import parse_council_page
resp = httpx.get('https://www.papalencyclicals.net/councils/ecum01.htm')
chunks = parse_council_page(resp.text, 'Council of Nicaea', 325)
print(f'{len(chunks)} chunks')
for c, r, p, m in chunks[:3]:
    print(f'  [{p}] {r!r}')
    print(f'      {c[:120]!r}')
"
```

Expected: 3–8 chunks, refs like `"Council of Nicaea — Canons"` or `"Council of Nicaea — Introduction"`.

- [ ] **Step 2: Dry-run a Vatican II document**

```bash
cd datapipeline && .venv/bin/python3 -c "
import httpx
from ingest.councils import parse_vatican2_doc
resp = httpx.get('https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19651118_dei-verbum_en.html')
chunks = parse_vatican2_doc(resp.text, 'Dei Verbum', 'constitution', 1965)
print(f'{len(chunks)} chunks')
for c, r, p, m in chunks[:3]:
    print(f'  [{p}] {r!r}')
    print(f'      meta: council={m[\"council\"]!r}, type={m[\"document_type\"]!r}')
"
```

Expected: 5–15 chunks, refs like `"Dei Verbum — Chapter I, §1–4"`, metadata `council='Vatican II'`.

- [ ] **Step 3: If parsing looks correct, run full ingestion**

```bash
cd datapipeline && .venv/bin/python3 -m ingest.councils
```

This fetches 30 pages total (14 council pages + 16 Vatican II docs) with 1.5s delay ≈ ~45 seconds minimum. Expected output:

```
Councils 1–20: 100%|████| 14/14 [...]
Vatican II: 100%|████| 16/16 [...]
  Done. NNN total chunks written for councils.
```

Watch for `WARNING` lines. 404 errors on Vatican II URLs are the most likely failure — check if the URL pattern has changed on vatican.va.

- [ ] **Step 4: Verify in DB**

```bash
cd datapipeline && .venv/bin/python3 -c "
import asyncio
from load import get_pool, close_pool
async def check():
    pool = await get_pool()
    rows = await pool.fetch('''
        SELECT d.title, d.year, COUNT(c.id) AS chunks,
               d.metadata->>'council' AS vat2
        FROM documents d
        JOIN chunks c ON c.document_id = d.id
        WHERE d.collection = 'councils'
        GROUP BY d.title, d.year, d.metadata->>'council'
        ORDER BY d.year NULLS LAST, d.title
    ''')
    for r in rows:
        tag = ' [Vatican II]' if r['vat2'] else ''
        print(f\"{r['year']} | {r['title'][:50]:<50} | {r['chunks']} chunks{tag}\")
    await close_pool()
asyncio.run(check())
"
```

Expected: 30 rows total — 14 council rows + 16 Vatican II document rows, each with a non-zero chunk count.

---

## Self-Review

**Spec coverage:**
- ✅ `"councils"` registered in constants.py, collections.ts, globals.css
- ✅ All 21 councils covered: 14 papalencyclicals.net pages (including multi-council bundles) + 16 Vatican II docs
- ✅ Vatican II: one DB row per document, `metadata.council = "Vatican II"`, `metadata.document_type`
- ✅ `parse_council_page()`: canon/paragraph accumulation, section header boundaries, ceiling enforcement
- ✅ `parse_vatican2_doc()`: numbered paragraph accumulation, chapter boundaries, same metadata contract
- ✅ Reference format: `"Council of Nicaea — Canons"`, `"Dei Verbum — Chapter I, §1–4"`
- ✅ Deep teal color `#4A7070`
- ✅ run_all.py updated

**Placeholder scan:** None — all steps contain complete, runnable code.

**Type consistency:** Both parsers return `list[tuple[str, str, int, dict]]` — the same shape as `upsert_chunk` arguments throughout. The `main()` function unpacks the 4-tuple identically for both parsers.

**Known risk:** Vatican II URL pattern on vatican.va (`/archive/hist_councils/ii_vatican_council/documents/`) was confirmed live during research. If the URLs return 404 during ingestion, check for redirect to `www.vatican.va/content/...` pattern and update the VATICAN_II_DOCS manifest.
