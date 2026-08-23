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
    chunks: list[tuple[str, str, int, dict | None]] = field(default_factory=list)  # (content, reference, position, metadata)


def _strip_tags(text: str) -> str:
    """Remove XML/HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return " ".join(text.split())


def _extract_p_text(elem) -> str:
    """Concatenate text from all <p> descendants of elem (recursive)."""
    parts = []
    for p in elem.iter("p"):
        raw = et_tostring(p, encoding="unicode", method="xml")
        t = _strip_tags(raw)
        if t:
            parts.append(t)
    return "\n\n".join(parts)


def _direct_p_text(elem) -> str:
    """Concatenate text from only the DIRECT <p> children of elem.

    Used for chapter content so a book-level div that has both intro paragraphs
    and chapter sub-divs does not duplicate its chapters' text.
    """
    parts = []
    for child in elem:
        if child.tag == "p":
            raw = et_tostring(child, encoding="unicode", method="xml")
            t = _strip_tags(raw)
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def _parse_author(creator: str) -> tuple[str, int | None]:
    """
    Parse 'Augustine, Saint, Bishop of Hippo (345-430)' or
    'Athanasius, St. (c.296-c.373)' into (cleaned_name, death_year).
    """
    m = re.search(r"\(c?\.?\d{3,4}\??-c?\.?(\d{3,4})\)\s*$", creator)
    year: int | None = None
    if m:
        try:
            year = int(m.group(1))
        except ValueError:
            pass
        creator = creator[: m.start()].strip().rstrip(",").strip()
    return creator, year


def _is_summa(root) -> bool:
    head = root.find(".//electronicEdInfo")
    if head is None:
        return False
    author_id = head.findtext("authorID") or ""
    book_id = head.findtext("bookID") or ""
    return author_id.strip() == "aquinas" and book_id.strip() == "summa"


_DISPLAY_TRAILING_CLOSERS = frozenset('"\'\u2019\u201d')
DISPLAY_PASSAGE_MAX_OVERSHOOT = 500


def _display_terminal_char(text: str, position: int) -> str:
    """Return the punctuation before any closing quote or numeric footnote."""
    cursor = position - 1
    while cursor >= 0:
        char = text[cursor]
        if char.isspace():
            cursor -= 1
            continue
        if char in _DISPLAY_TRAILING_CLOSERS:
            cursor -= 1
            continue
        if char in ")]":
            opener = "(" if char == ")" else "["
            note_cursor = cursor - 1
            while note_cursor >= 0 and text[note_cursor].isdigit():
                note_cursor -= 1
            if note_cursor < cursor - 1 and note_cursor >= 0 and text[note_cursor] == opener:
                cursor = note_cursor - 1
                continue
            cursor -= 1
            continue
        return char
    return ""


def _display_starts_sentence(text: str, position: int, separator: str) -> bool:
    """Distinguish a sentence break from a period inside a citation or abbreviation."""
    cursor = position + len(separator)
    opening = frozenset('"\'([\u2018\u201c')
    while cursor < len(text) and text[cursor] in opening:
        cursor += 1
    return cursor >= len(text) or text[cursor].isupper() or text[cursor].isdigit()


def _display_break_kind(text: str, position: int, separator: str) -> int:
    """Rank a whitespace boundary by how natural it is to a reader."""
    terminal = _display_terminal_char(text, position)
    starts_sentence = _display_starts_sentence(text, position, separator)
    if (separator.count("\n") >= 2 and starts_sentence
            and terminal in ".!?;:"):
        return 0
    if terminal in ".!?" and starts_sentence:
        return 1
    if terminal in ";:":
        return 2
    if terminal == ",":
        return 3
    return 4


def _choose_display_break(text: str, start: int, lower: int,
                          hard_upper: int, soft_upper: int, max_chars: int) -> int:
    """Choose the strongest readable break without creating a small piece."""
    boundaries = []
    for match in re.finditer(r"\s+", text[start:soft_upper + 1]):
        position = start + match.start()
        if lower <= position <= soft_upper:
            boundaries.append(
                (position, _display_break_kind(text, position, match.group(0)))
            )
    if not boundaries:
        # Only an individual token longer than the cap reaches this path.
        return hard_upper

    # A nearby paragraph, sentence, or semicolon may exceed the target slightly because
    # preserving that structure reads better than an arbitrary cut. Weak comma and
    # whitespace fallbacks remain inside the configured target.
    structural = [boundary for boundary in boundaries if boundary[1] <= 2]
    if structural:
        return min(structural, key=lambda boundary: (boundary[1], -boundary[0]))[0]
    fallback = [boundary for boundary in boundaries if boundary[0] <= hard_upper]
    if fallback:
        return min(fallback, key=lambda boundary: (boundary[1], -boundary[0]))[0]
    return hard_upper


def split_display_passage(text: str, max_chars: int) -> list[str]:
    """Split one meaningful source passage into complete, readable display pieces.

    The caller supplies a passage chosen from source structure, such as a canon,
    pericope, numbered paragraph, chapter, or Summa article role. This function owns
    only the size cap. It keeps every word exactly once, reserves enough text for a
    useful final piece, prefers paragraph and sentence boundaries, and falls back
    through clause punctuation to whitespace.

    A structural boundary may exceed ``max_chars`` by at most 500 characters. A single
    token longer than ``max_chars`` is the sole case where a word can be cut.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    text = text.strip()
    if not text or len(text) <= max_chars:
        return [text] if text else []

    pieces: list[str] = []
    start = 0
    min_split_piece = max(1, max_chars // 4)
    while len(text) - start > max_chars:
        lower = start + min_split_piece
        # Leave enough text for a useful final display passage. Because the minimum is
        # one quarter of the maximum, any larger remainder can also be partitioned into
        # pieces within the same range.
        hard_upper = min(start + max_chars, len(text) - min_split_piece)
        soft_upper = min(
            start + max_chars + DISPLAY_PASSAGE_MAX_OVERSHOOT,
            len(text) - min_split_piece,
        )
        end = _choose_display_break(
            text, start, lower, hard_upper, soft_upper, max_chars
        )
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
        while start < len(text) and text[start].isspace():
            start += 1

    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


# Compatibility for callers outside the current collection builders. Display-passage
# construction uses `split_display_passage`; this older overlap interface remains only
# for legacy imports while they are retired.
_MIN_TAIL_CHARS = 40
_MAX_FALLBACK_SCAN = 500


def _split_at_whitespace(text: str, target: int, overlap: int) -> list[str]:
    target = max(1, target)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target, len(text))
        if end < len(text):
            ws = text.rfind(" ", start, end + _MAX_FALLBACK_SCAN)
            if ws > start:
                end = ws
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        next_start = end - overlap
        start = next_start if next_start > start else end
    kept = [chunk for chunk in chunks if chunk]
    if not overlap and len(kept) > 1 and len(kept[-1]) < _MIN_TAIL_CHARS:
        kept[-2] = f"{kept[-2]} {kept[-1]}"
        kept.pop()
    return kept

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


def _detect_is_multi_author(root) -> bool:
    """True when the file groups content by multiple authors at div1 level.

    Heuristic: if >1 div1 exists AND none match generic chapter/book patterns,
    assume they represent different authors.
    """
    titles = [(d.get("title") or "").strip() for d in root.iter("div1")]
    titles = [t for t in titles if t]

    if len(titles) <= 1:
        return False

    # Check if titles look like chapters/books (not author names)
    # Examples: "Book I", "Chapter 1", "Part III", "Volume II"
    generic_patterns = re.compile(r"^(Book|Chapter|Part|Volume|Treatise)\s", re.IGNORECASE)
    generic_count = sum(1 for t in titles if generic_patterns.match(t))

    # If most titles are NOT generic chapter/book names, assume multi-author
    return generic_count <= len(titles) * 0.3


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
    """Short reference label for a chunk-level div.

    Preference order: shorttitle → title (if non-generic) → Chapter N → title.
    Using 'n' to fabricate 'Chapter N' only when no meaningful title exists.
    """
    st = (elem.get("shorttitle") or "").strip()
    if st:
        return st
    title = (elem.get("title") or "").strip()
    if title and not _GENERIC_CHAPTER_RE.match(title):
        return title[:50]
    n = (elem.get("n") or "").strip()
    if n:
        return f"Chapter {n.upper()}"
    return title[:50]


def _build_reference(
    doc: "ThmlDocument",
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
        if not ancestors:
            return _maybe_title_case((chunk_elem.get("title") or "Unknown").strip())
        author_lbl = _maybe_title_case((ancestors[0].get("title") or "").strip()) or "Unknown"
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
        # When there are 2+ ancestor levels, skip the outermost (div1 volume/container)
        # so references read "Book I, Chapter I" rather than "Volume I, Book I, Chapter I".
        ref_ancestors = ancestors[1:] if len(ancestors) >= 2 else ancestors
        path = []
        for anc in ref_ancestors:
            lbl = _parent_label(anc)
            if lbl:
                path.append(lbl)
        if chunk_lbl:
            path.append(chunk_lbl)
        return f"{short_author} — {work}, {', '.join(path)}" if path else f"{short_author} — {work}"


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
        parent_lbl = _parent_label(parent) if parent is not None else ""
        chunk_title = (chunk_elem.get("title") or "").strip()[:120]
        return f"[{parent_lbl}] {chunk_title}" if parent_lbl else chunk_title


def _chunk_standard(root, doc: "ThmlDocument", min_length: int = 100) -> list[tuple[str, str, int, dict | None]]:
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
    author_id = (head_elem.findtext("authorID") if head_elem is not None else "") or ""
    book_id = (head_elem.findtext("bookID") if head_elem is not None else "") or ""

    chunks: list[tuple[str, str, int, dict | None]] = []
    position = 0

    for elem in chunk_elems:
        content_text = _extract_p_text(elem)
        if len(content_text) < min_length:
            continue

        # Collect ancestors root→parent (div elements only)
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
            "parent_shorttitle": _parent_label(parent) if parent is not None else "",
            "chapter_title": (elem.get("title") or "").strip(),
        }

        if len(content) <= _CEILING:
            chunks.append((content, reference, position, metadata))
            position += 1
        else:
            parts = split_display_passage(content_text, _CF_SPLIT_TARGET)
            total = len(parts)
            for idx, part in enumerate(parts):
                part_content = f"{header}\n\n{part}" if header else part
                part_ref = f"{reference} ({idx + 1}/{total})" if total > 1 else reference
                chunks.append((part_content, part_ref, position, metadata))
                position += 1

    return chunks


def _chunk_summa(root, min_length: int = 50) -> list[tuple[str, str, int, dict | None]]:
    """Chunk at div4 (Article) level for the Summa, with full Part→Treatise→Question breadcrumb."""
    head_elem = root.find(".//electronicEdInfo")
    author_id = (head_elem.findtext("authorID") if head_elem is not None else "") or ""
    book_id = (head_elem.findtext("bookID") if head_elem is not None else "") or ""

    chunks: list[tuple[str, str, int, dict | None]] = []
    position = 0
    for div1 in root.iter("div1"):
        div1_title = (div1.get("title") or "").strip()
        for div2 in div1:
            if not div2.tag.startswith("div2"):
                continue
            div2_title = (div2.get("title") or "").strip()
            for div3 in div2:
                if not div3.tag.startswith("div3"):
                    continue
                div3_title = (div3.get("title") or "").strip()
                for div4 in div3:
                    if not div4.tag.startswith("div4"):
                        continue
                    div4_title = (div4.get("title") or "").strip()
                    content = _extract_p_text(div4)
                    if len(content) < min_length:
                        continue
                    ref_parts = [p for p in [div1_title, div2_title, div3_title, div4_title] if p]
                    reference = ", ".join(ref_parts)
                    metadata: dict = {
                        "author_id": author_id,
                        "book_id": book_id,
                        "div_depth": 4,
                        "part": div1_title,
                        "treatise": div2_title,
                        "question": div3_title,
                        "article": div4_title,
                    }
                    chunks.append((content, reference, position, metadata))
                    position += 1
    return chunks


_SKIP_WORK_TITLES = _SKIP_TITLES | frozenset({
    "introductory notice", "introductory notice.", "title pages", "title pages.",
    "subject index", "subject indexes", "appendix", "indexes.", "errata",
})


def _cf_skippable(title: str) -> bool:
    """True for ThML div titles that are front-matter, not a work/father/chapter."""
    t = (title or "").strip().lower()
    if t in _SKIP_WORK_TITLES:
        return True
    return t.startswith("introductory note") or t.startswith("introductory notice")


def iter_works(root):
    """Yield (father_label, work_label, [chunk_div_elements]) for a ThML volume.

    Multi-author volume (div1 = father, div2 = work, chapters = div3): one tuple
    per (father, work). Otherwise (single author / generic div1s): one tuple per
    div1, with father == work and chapters = the chunk-level divs beneath it.
    """
    div1s = [d for d in root.iter("div1") if not _cf_skippable(d.get("title") or "")]
    multi = _detect_is_multi_author(root)
    chunk_level = _detect_chunk_level(root)
    for d1 in div1s:
        father = (d1.get("title") or "").strip()
        div2s = [d for d in d1.iter("div2") if not _cf_skippable(d.get("title") or "")]
        if multi and div2s and chunk_level >= 3:
            for d2 in div2s:
                chapters = [e for e in d2.iter(f"div{chunk_level}")
                            if not _cf_skippable(e.get("title") or "")]
                if chapters:
                    yield father, (d2.get("title") or "").strip(), chapters
        else:
            chapters = [e for e in d1.iter(f"div{chunk_level}")
                        if not _cf_skippable(e.get("title") or "")]
            if chapters:
                yield father, father, chapters


_BOOK_RE = re.compile(r"^\s*Book\s+[IVXLCDM0-9]", re.IGNORECASE)


def _has_direct_p(elem) -> bool:
    return any(child.tag == "p" for child in elem)


def _book_label(elem) -> str | None:
    """Return a clean book label ('Book I') if elem is a book division, else None.

    ThML marks books via type="Book" and carries the readable label in shorttitle
    ('Book I'); the title attribute is a long descriptive sentence.
    """
    if (elem.get("type") or "").strip().lower() == "book":
        st = (elem.get("shorttitle") or "").strip()
        if st:
            return st
        n = (elem.get("n") or "").strip()
        return f"Book {n.upper()}" if n else "Book"
    for attr in ("shorttitle", "title"):
        v = (elem.get(attr) or "").strip()
        if _BOOK_RE.match(v):
            return v
    return None


def iter_chapters(work_root, parent_map):
    """Yield (book_label|None, chapter_elem) for the content-bearing divs under
    work_root, at whatever depth they occur (work→chapter or work→book→chapter).
    A chapter is any div with direct <p> children; its book is the nearest ancestor
    book division. Chapters under skippable front-matter ancestors are omitted.
    """
    for elem in work_root.iter():
        tag = elem.tag
        if elem is work_root or not (isinstance(tag, str) and tag.startswith("div")):
            continue
        if not _has_direct_p(elem):
            continue
        skip = _cf_skippable(elem.get("title") or "")
        book = None
        cur = parent_map.get(elem)
        while cur is not None and cur is not work_root:
            if _cf_skippable(cur.get("title") or ""):
                skip = True
                break
            if book is None:
                book = _book_label(cur)
            cur = parent_map.get(cur)
        if skip:
            continue
        yield book, elem


def parse_thml_string(xml_string: str) -> ThmlDocument:
    """Parse a ThML XML string into a ThmlDocument."""
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


def parse_thml(path: str) -> ThmlDocument:
    """Parse a ThML XML file into a ThmlDocument."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_thml_string(f.read())
