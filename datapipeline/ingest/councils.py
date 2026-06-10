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
        if not text:
            continue

        tag = elem.name
        if tag in ("h2", "h3", "h4"):
            if acc_len >= 100:
                _flush()
            active_section = text
            continue

        if len(text) < _MIN_LENGTH:
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
    headers (<strong>CHAPTER I</strong>). Accumulates paragraphs up to _TARGET_LATE
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
    acc: list[tuple[int, str]] = []   # (para_num, text)
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

    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p", "strong"]):
        text = elem.get_text(separator=" ", strip=True)
        if not text:
            continue

        # Chapter heading: "CHAPTER I" or "Chapter II" standalone
        if re.match(r"^CHAPTER\s+[IVXLCDM]+$", text, re.IGNORECASE):
            if acc_len >= 100:
                _flush()
            active_chapter = text.title()  # "Chapter I"
            continue

        if elem.name in ("h3", "h4") and len(text) < 120:
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
