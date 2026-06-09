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
        url = href.split("#")[0]
        if url.startswith("http"):
            abs_url = url
        else:
            abs_url = base + url
        if abs_url not in seen:
            seen.add(abs_url)
            result.append(abs_url)
    return result


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

        all_canons: list[tuple[int, str, dict]] = []
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
    unique_canons: list[tuple[int, str, dict]] = []
    for num, text, ctx in sorted(all_canons, key=lambda x: x[0]):
        if num not in seen_nums:
            seen_nums.add(num)
            unique_canons.append((num, text, ctx))

    print(f"  Ingesting {len(unique_canons)} unique canons...")
    for position, (canon_num, content, ctx) in enumerate(unique_canons):
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
