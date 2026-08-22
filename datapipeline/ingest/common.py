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


_SENT_END = re.compile(r'(?<=[.!?])\s+')
_MAX_FALLBACK_SCAN = 500

# A trailing piece shorter than this is folded back into the one before it. Splitting on
# a size budget can leave a runt — the catechism produces final pieces reading only
# "irrelevant.", "proceeds.", "19:26)." — and a passage that short carries no meaning
# alone: it gets its own embedding and can be retrieved as a standalone result that tells
# the reader nothing. `test_catechism_passages.py` forbids passages under 30 characters,
# and passed before only because the truncation bug discarded them.
#
# 40, not a rounder larger number, because folding is the ONLY thing that can push a
# piece past the cap. Measured over the seven collections with local sources, every
# threshold from 40 up removes all 57 catechism fragments, so the extra width buys
# nothing:
#
#     threshold    over 4,000 chars    longest piece
#            40                   6            4,019
#           100                  15            4,085
#           200                  21            4,154
#
# This does NOT establish a minimum passage length for the corpus: 6,281 of 54,027 live
# chunks are under 200 characters and none of them come from this function, which only
# ever sees a piece another splitter already oversized.
_MIN_TAIL_CHARS = 40


def split_at_sentences(
    text: str,
    target: int = 1200,
    overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks of ~target chars at sentence boundaries.

    All limits are soft — splits always happen at sentence ends. If no sentence
    boundary is found within _MAX_FALLBACK_SCAN chars of the target, splits at
    the nearest whitespace instead.
    """
    if len(text) <= target:
        return [text]

    sentences = _SENT_END.split(text)
    if len(sentences) <= 1:
        return _split_at_whitespace(text, target, overlap)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        current.append(sent)
        current_len += len(sent) + 1
        if current_len >= target:
            chunks.append(" ".join(current))
            overlap_sents: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) + 1 <= overlap:
                    overlap_sents.insert(0, s)
                    overlap_len += len(s) + 1
                else:
                    break
            current = overlap_sents
            current_len = overlap_len

    if current:
        last = " ".join(current)
        if not chunks or last != chunks[-1]:
            chunks.append(last)

    return chunks


def _split_at_whitespace(text: str, target: int, overlap: int) -> list[str]:
    """Split text into ~target-sized pieces at whitespace, keeping ALL of it.

    The fallback when no sentence boundary can be found. Two bugs lived here, and the
    second is why the first went unnoticed for so long:

      overlap == 0 — `start = end - overlap` made start equal end, which the guard
        `if start >= end: break` then read as "the loop is not advancing". It returned
        the FIRST piece and silently discarded the rest. Every ingest adapter calls this
        with overlap=0, so ~4,500 chunks across nine collections are missing their tail;
        where the text had no detectable sentence boundary at all, everything past the
        cap was dropped.

      overlap > 0 — once `end` reached the end of the text, `start = end - overlap`
        stepped backwards and the loop re-emitted the same tail forever. The one caller
        that passes a real overlap therefore hangs, which is presumably why nobody
        exercised it and found the truncation.

    Both come from conflating "how far to step back for overlap" with "have we
    finished". Termination is now decided by whether `end` reached the text, and the
    step-back only applies when it genuinely advances.
    """
    # A non-positive target would make `end <= start`, so neither the step-back nor its
    # fallback advances and the loop spins. The old guard caught that only as a side
    # effect of the same comparison that caused the truncation, so removing it removed
    # this protection too. Clamped rather than raised: callers pass a configured
    # constant, and a bad value should degrade to one-piece-per-character rather than
    # abort an ingest mid-run.
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
        # `end` always exceeds `start` (the ws guard requires it), so falling back to it
        # guarantees progress even when the requested overlap would not.
        next_start = end - overlap
        start = next_start if next_start > start else end

    kept = [c for c in chunks if c]
    # Not when overlapping: the tail already repeats the end of its predecessor, so
    # merging the two would duplicate that span inside a single piece. Unreachable at
    # the current settings — the only caller passing an overlap uses 200, five times
    # `_MIN_TAIL_CHARS`, and an overlapped tail is at least the overlap wide — so this
    # is a guard against a future retuning, not a live path.
    if not overlap and len(kept) > 1 and len(kept[-1]) < _MIN_TAIL_CHARS:
        kept[-2] = f"{kept[-2]} {kept[-1]}"
        kept.pop()
    return kept


_OVERLAP_CHARS = 200

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
            parts = split_at_sentences(content_text, target=_CF_SPLIT_TARGET, overlap=_OVERLAP_CHARS)
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
