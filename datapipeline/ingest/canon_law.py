"""Code of Canon Law (1983) ingestion (dual pipeline).

Reads the vendored vatican.va canon pages from sources/canon-law/ and builds a
single Document with one clean Passage per canon. Book is assigned by canon-
number range (the 7 books have fixed ranges); Title/Chapter context is forward-
filled across page boundaries (vatican.va only emits the header on the page
where a section starts). The legacy parse helpers (parse_canon_page, grouping)
are retained for their unit tests.
"""
from __future__ import annotations
import json
import os
import re

from bs4 import BeautifulSoup

from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import smart_title_case

_BASE = "http://www.vatican.va"
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


# Matches a full Roman numeral (used to re-uppercase ones smart_title_case
# lowercased — its acronym set only covers I–X, so XI+ come back as 'Xi').
_ROMAN_WORD = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def _fix_romans(label: str) -> str:
    return " ".join(
        w.upper() if len(w) > 1 and _ROMAN_WORD.match(w.upper()) else w
        for w in label.split())


def _clean_label(text: str) -> str:
    """Title-case an ALL-CAPS hierarchy header. Trailing punctuation is trimmed
    BEFORE casing so trailing-dot Roman numerals ('TITLE II.') keep their case;
    Roman numerals beyond X are re-uppercased after casing."""
    trimmed = clean_text(text).strip().rstrip(".:").strip()
    return _fix_romans(smart_title_case(trimmed))


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
