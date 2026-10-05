"""Read vendored source files into units of text, without the adapters.

Each extractor returns `list[SourceUnit]` for one file. A unit is one block of the
source (a paragraph, a verse, a numbered Catechism paragraph, a note) with the region it
belongs to:

- "body": the work's own text, which should reach a passage;
- "note": footnotes and endnotes;
- "toc": tables of contents and navigation links;
- "heading": headings and titles;
- "apparatus": page furniture that is none of the above (title pages, indexes, language
  bars, site footers, the editor's introduction to a Bible book).

Nothing here imports from `ingest/`, so a parser defect cannot hide itself by being
shared. Where a sentence of body text is interrupted by a note, the note's position is
marked with `SEGMENT_BREAK`, so the text either side is measured separately whether or
not an adapter leaves the note inline.
"""
from __future__ import annotations

import html
import json
import os
import re
from glob import glob
from typing import NamedTuple

import defusedxml.ElementTree as ET
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

SOURCES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources")

# Separates two stretches of text that must not be read as one sentence.
SEGMENT_BREAK = "\u2029"

REGIONS = ("body", "note", "toc", "heading", "apparatus")


class SourceUnit(NamedTuple):
    source_file: str      # path relative to sources/<collection>/
    unit_id: str | None   # div id, "<BOOK>/<chapter>/<verse>", paragraph or canon number
    text: str
    region: str           # one of REGIONS


# --------------------------------------------------------------------------- ThML

_THML_TOC_TITLES = frozenset({"contents", "table of contents"})
_THML_APPARATUS = re.compile(
    r"^(?:title pages?|indexes|indices|index|subject index(?:es)?|index of .*|errata)\.?$")
_THML_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_THML_DIVS = frozenset(f"div{n}" for n in range(1, 7))


def _thml_div_region(title: str, inherited: str) -> str:
    if inherited != "body":
        return inherited
    t = " ".join((title or "").split()).lower()
    if t in _THML_TOC_TITLES:
        return "toc"
    if _THML_APPARATUS.match(t):
        return "apparatus"
    return "body"


def _thml_text(el, skip_notes: bool) -> str:
    """Text of an element. With skip_notes, each <note> becomes a SEGMENT_BREAK.
    Entities the source escaped twice ("&amp;gt;") are read as the character."""
    return html.unescape(_thml_raw(el, skip_notes))


def _thml_raw(el, skip_notes: bool) -> str:
    parts = [el.text or ""]
    for child in el:
        if skip_notes and child.tag == "note":
            parts.append(SEGMENT_BREAK)
        elif child.tag == "br":
            parts.append(" ")
        else:
            parts.append(_thml_raw(child, skip_notes))
        parts.append(child.tail or "")
    return "".join(parts)


def _read_thml(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


def thml_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """ThML (CCEL XML). Body is <p> text inside div1 to div6; <note> is "note";
    <scripCom> and <pb> carry no text and are ignored. unit_id is the nearest
    ancestor div's id."""
    source_file = source_file or os.path.basename(path)
    root = _read_thml(path)
    units: list[SourceUnit] = []

    def walk(el, div_id: str | None, region: str, in_div: bool) -> None:
        for child in el:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag in _THML_DIVS:
                walk(child, child.get("id") or div_id,
                     _thml_div_region(child.get("title") or "", region), True)
            elif tag == "note":
                if in_div:
                    units.append(SourceUnit(source_file, div_id,
                                            _thml_text(child, skip_notes=False), "note"))
            elif tag == "p":
                if in_div:
                    units.append(SourceUnit(source_file, div_id,
                                            _thml_text(child, skip_notes=True), region))
                    # A note inside the paragraph is its own unit.
                    for note in child.iter("note"):
                        units.append(SourceUnit(source_file, div_id,
                                                _thml_text(note, skip_notes=False), "note"))
            elif tag in _THML_HEADINGS:
                if in_div:
                    units.append(SourceUnit(source_file, div_id,
                                            _thml_text(child, skip_notes=True), "heading"))
            else:
                walk(child, div_id, region, in_div)

    walk(root, None, "body", False)
    return [u for u in units if u.text.strip()]


def thml_divs(path: str) -> list[tuple[str, int, str, str]]:
    """Every div1 to div6 of a ThML file as (id, level, title, region), in order."""
    root = _read_thml(path)
    out: list[tuple[str, int, str, str]] = []

    def walk(el, region: str) -> None:
        for child in el:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag in _THML_DIVS:
                r = _thml_div_region(child.get("title") or "", region)
                out.append((child.get("id") or "", int(tag[3:]),
                            " ".join((child.get("title") or "").split()), r))
                walk(child, r)
            else:
                walk(child, region)

    walk(root, "body")
    return out


# --------------------------------------------------------------------------- HTML

# Elements that start a new block of text. Inline elements (a, b, i, span, font, …)
# join the block they sit in.
_HTML_BLOCKS = frozenset({
    "p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "dd", "dt",
    "blockquote", "center", "tr", "table", "ul", "ol", "dl", "body", "pre",
})
_HTML_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_HTML_DROP = ("script", "style", "noscript", "nav", "header", "footer", "form", "head")

# A notes heading, or a horizontal rule followed by numbered notes, starts the notes.
# papalencyclicals.net heads its notes "REFERENCES:".
_NOTES_HEADING = re.compile(r"^(?:end|foot)?notes?\b|^references:?$", re.IGNORECASE)
_NOTE_START = re.compile(r"^\s*(?:\[\s*1\s*\]|\(\s*1\s*\)|1\s*\.|1\s)")
_BRACKET_NOTE_START = re.compile(r"^\s*(?:\[\s*1\s*\]|\(\s*1\s*\))")
_SITE_CHROME = re.compile(
    r"^copyright\s*©|^©\s*copyright|automatically notified|more information about this site"
    r"|fan of our facebook|^search tips$|^sitemap$|return to (?:the )?home|^last updated\b",
    re.IGNORECASE)
_PARA_NUMBER = re.compile(r"^\s*(\d{1,4})\s*\.(?:\s|$)")
_CANON_NUMBER = re.compile(r"^\W*n?\s*Can\.\s*(\d+)")
_LEADING_NUMBER = re.compile(r"^\s*(?:\d{1,4}\s*\.|\W*n?\s*Can\.\s*\d+\.?)\s*")


def _is_shouting(text: str) -> bool:
    """A short all-capitals block: a heading set as a paragraph."""
    letters = [c for c in text if c.isalpha()]
    return (len(text) < 200 and len(letters) >= 4
            and sum(c.isupper() for c in letters) / len(letters) >= 0.8)


def _html_main(soup: BeautifulSoup) -> Tag:
    """The element holding the document: papalencyclicals.net's entry-content, the
    current vatican.va layout's `documento`, the old vatican.va layout's largest table
    cell, else the body."""
    for selector in ("div.entry-content", "div.documento"):
        found = soup.select(selector)
        if found:
            return max(found, key=lambda e: len(e.get_text(" ", strip=True)))
    cells = soup.find_all("td")
    if cells:
        # The innermost cell holding most of the text: a layout table nests cells.
        best = max(cells, key=lambda e: len(e.get_text(" ", strip=True)))
        return best
    return soup.body or soup


class _Block(NamedTuple):
    tag: str
    text: str
    all_link: bool   # every letter and digit sits inside an <a href>


def _html_blocks(main: Tag) -> list[_Block]:
    blocks: list[_Block] = []

    def visit(el: Tag, block_tag: str) -> None:
        buf: list[str] = []
        linked = [0, 0]   # characters inside links, all characters

        def flush() -> None:
            text = "".join(buf)
            if text.strip():
                blocks.append(_Block(block_tag, text, linked[0] == linked[1]))
            buf.clear()
            linked[0] = linked[1] = 0

        def inline(node, in_link: bool) -> None:
            for child in node.children:
                if isinstance(child, Comment):
                    continue
                if isinstance(child, NavigableString):
                    s = str(child)
                    buf.append(s)
                    n = sum(c.isalnum() for c in s)   # separators such as " - " are not text
                    linked[1] += n
                    if in_link:
                        linked[0] += n
                    continue
                if not isinstance(child, Tag):
                    continue
                if child.name in _HTML_BLOCKS:
                    flush()
                    visit(child, child.name)
                    continue
                if child.name == "br":
                    buf.append(" ")
                    continue
                if child.name == "hr":
                    flush()
                    blocks.append(_Block("hr", "", False))
                    continue
                inline(child, in_link or (child.name == "a" and child.get("href") is not None))

        inline(el, False)
        flush()

    visit(main, main.name)
    return blocks


def html_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """vatican.va and papalencyclicals.net HTML. Body is the visible text of the main
    content element, one unit per block (<p>, <li>, <div>, table cell, …). Text after
    the first notes marker is "note": a notes heading ("Notes", "NOTES", "ENDNOTES",
    "REFERENCES:"), a horizontal rule followed by note 1 when note 1 is bracketed or the
    body has already used paragraph number 1, or a block that opens with "[1]". Headings are "heading"; blocks that
    are entirely links (language bars, tables of contents) are "toc"; site footers are
    "apparatus". unit_id is the leading paragraph or canon number."""
    source_file = source_file or os.path.basename(path)
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    for tag in soup.find_all(_HTML_DROP):
        tag.decompose()
    blocks = _html_blocks(_html_main(soup))

    units: list[SourceUnit] = []
    in_notes = False
    seen_para_one = False
    for i, block in enumerate(blocks):
        if block.tag == "hr":
            if in_notes:
                continue
            nxt = next((b for b in blocks[i + 1:] if b.tag != "hr" and b.text.strip()), None)
            if nxt is not None:
                lead = " ".join(nxt.text.split())
                if _BRACKET_NOTE_START.match(lead) or (seen_para_one and _NOTE_START.match(lead)):
                    in_notes = True
            continue
        text = " ".join(block.text.split())
        if not in_notes and units and _BRACKET_NOTE_START.match(text) and text.startswith("["):
            in_notes = True     # "[1] …" with its rule outside the main element
        if not in_notes and len(text) < 40 and _NOTES_HEADING.match(text):
            in_notes = True
            units.append(SourceUnit(source_file, None, block.text, "heading"))
            continue
        number = _PARA_NUMBER.match(text) or _CANON_NUMBER.match(text)
        unit_id = number.group(1) if number else None
        body_text = block.text
        if number:
            # The number is the unit's identity, not its text: adapters drop it.
            body_text = _LEADING_NUMBER.sub("", block.text, count=1)
        if in_notes:
            region = "note"
        elif _SITE_CHROME.search(text):
            region = "apparatus"
        elif block.all_link:
            region = "toc"
        elif block.tag in _HTML_HEADINGS or (not number and _is_shouting(text)):
            region = "heading"
        else:
            region = "body"
            if unit_id == "1" and _PARA_NUMBER.match(text):
                seen_para_one = True
        if in_notes and _SITE_CHROME.search(text):
            region = "apparatus"
        units.append(SourceUnit(source_file, unit_id,
                                body_text if region == "body" else block.text, region))
    return units


# --------------------------------------------------------------------------- USFM

_USFM_NOTE = re.compile(r"\\(f|fe|x)\s.*?\\\1\*", re.DOTALL)
_USFM_WORD = re.compile(r"\\\+?w\s+([^|\\]*?)\s*(?:\|[^\\]*)?\\\+?w\*")
_USFM_MARKER = re.compile(r"\\\+?[a-zA-Z0-9]+\*?")
# Paragraph markers whose text is a heading or the editor's introduction, not verses.
_USFM_HEADINGS = frozenset({"h", "mt", "mt1", "mt2", "mt3", "ms", "ms1", "ms2", "mr", "s",
                            "s1", "s2", "s3", "sr", "r", "d", "sp", "is", "is1", "is2",
                            "cl", "cd"})
_USFM_APPARATUS = frozenset({"id", "ide", "toc1", "toc2", "toc3", "ip", "ipr", "im", "imt",
                             "imt1", "imt2", "io1", "io2", "iot", "rem", "sts"})
_USFM_BREAKS = frozenset({"p", "m", "mi", "nb", "pc", "pi", "pi1", "pi2", "q", "q1", "q2",
                          "q3", "qr", "qc", "b", "li", "li1", "li2"})
_USFM_TOKEN = re.compile(
    r"(?m)\\(c|v)\s+(\d+)[a-z]?\s?|^\\("
    + "|".join(sorted(_USFM_HEADINGS | _USFM_APPARATUS | _USFM_BREAKS, key=len, reverse=True))
    + r")(?![a-z0-9])")


def _usfm_plain(raw: str) -> str:
    text = _USFM_WORD.sub(r"\1", raw)
    text = _USFM_MARKER.sub(" ", text)
    return text


def usfm_book_code(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"^\\id\s+([A-Z0-9]{3})", line)
            if m:
                return m.group(1)
    raise ValueError(f"{path}: no \\id line")


def usfm_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """USFM (Bible). One unit per \\v, unit_id "<BOOK>/<chapter>/<verse>". Footnotes and
    cross-references (\\f, \\fe, \\x) are "note"; section headings and Psalm titles
    (\\s, \\d, …) are "heading"; the book's identification lines and introduction are
    "apparatus". A verse continues across paragraph and poetry markers until the next
    verse, chapter or heading."""
    source_file = source_file or os.path.basename(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    code = usfm_book_code(path)
    units: list[SourceUnit] = []
    # Notes first, so a verse's text can be read with them removed.
    for m in _USFM_NOTE.finditer(raw):
        units.append(SourceUnit(source_file, None, _usfm_plain(m.group(0)[3:-3]), "note"))
    body = _USFM_NOTE.sub(f" {SEGMENT_BREAK} ", raw)

    chapter = 0
    current: tuple[str | None, str] = (None, "apparatus")
    buf: list[str] = []
    pos = 0

    def flush() -> None:
        text = _usfm_plain("".join(buf))
        if text.strip(f" \t\n{SEGMENT_BREAK}"):
            units.append(SourceUnit(source_file, current[0], text, current[1]))
        buf.clear()

    for m in _USFM_TOKEN.finditer(body):
        buf.append(body[pos:m.start()])
        pos = m.end()
        kind, number, para = m.group(1), m.group(2), m.group(3)
        if kind == "c":
            flush()
            chapter = int(number)
            current = (None, "heading")
        elif kind == "v":
            flush()
            current = (f"{code}/{chapter}/{int(number)}", "body")
        elif para in _USFM_HEADINGS:
            flush()
            current = (None, "heading")
        elif para in _USFM_APPARATUS:
            flush()
            current = (None, "apparatus")
        elif current[1] == "body":
            # \p, \q1, \m, \b, …: a paragraph or poetry break inside the current verse.
            buf.append(" ")
        else:
            # A paragraph after a heading and before the next verse marker: text with
            # no verse number, measured for coverage but outside any verse.
            flush()
            current = (None, "body" if chapter else "apparatus")
    buf.append(body[pos:])
    flush()
    return units


# --------------------------------------------------------------------------- CCC

def _ccc_heading(para: dict, text: str) -> bool:
    """An unnumbered, unindented short line not ending in ":" or ";" is a heading in
    ccc.json; indented lines are quotations inside the paragraph before them."""
    t = text.strip()
    return ("indent" not in (para.get("attrs") or {}) and len(t) < 120
            and not t.endswith((":", ";", ",")))


def ccc_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """ccc.json (Catechism). One unit per numbered paragraph, unit_id the CCC number.
    Unnumbered paragraphs that follow a numbered one (indented quotations, the
    continuation of a paragraph) belong to it; unnumbered paragraphs before the first
    number of a page are "heading". Footnotes are "note"."""
    source_file = source_file or os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("page_nodes", {})

    def order(key: str) -> int:
        try:
            return int(key.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    units: list[SourceUnit] = []
    for key in sorted(nodes, key=order):
        node = nodes[key]
        number: int | None = None
        parts: list[str] = []

        def flush() -> None:
            if number is not None and parts:
                units.append(SourceUnit(source_file, str(number), "\n".join(parts), "body"))

        for para in node.get("paragraphs", []):
            elements = para.get("elements", [])
            refs = [e.get("ref_number") for e in elements
                    if e.get("type") == "ref-ccc" and e.get("ref_number") is not None]
            text = " ".join(e.get("text", "") for e in elements
                            if e.get("type") == "text" and e.get("text"))
            if refs:
                flush()
                number, parts = refs[0], [text] if text.strip() else []
            elif not text.strip():
                continue
            elif number is None or _ccc_heading(para, text):
                flush()          # keep source order: the paragraph so far, then the heading
                parts = []
                units.append(SourceUnit(source_file, None, text, "heading"))
            else:
                parts.append(text)
        flush()
        for note_number, note in (node.get("footnotes") or {}).items():
            text = " ".join(r.get("text") or "" for r in note.get("refs", []))
            if text.strip():
                units.append(SourceUnit(source_file, f"n{note_number}", text, "note"))
    return units


# --------------------------------------------------------------------------- files

# Collections whose files are listed in sources/<collection>/manifest.json, by format.
_MANIFEST_HTML = ("apostolic-exhortations", "councils", "encyclicals", "papal-documents")


def collection_files(collection: str, sources: str = SOURCES) -> list[str]:
    """The source files a collection is built from, relative to sources/<collection>/,
    as the vendored manifests list them. Files a manifest leaves out (downloaded but never
    published) are not measured."""
    base = os.path.join(sources, collection)
    if collection in _MANIFEST_HTML or collection in ("medieval", "church-fathers"):
        with open(os.path.join(base, "manifest.json"), encoding="utf-8") as f:
            return [e["file"] for e in json.load(f)]
    if collection == "canon-law":
        with open(os.path.join(base, "pages.json"), encoding="utf-8") as f:
            return [p["file"] for p in json.load(f) if p.get("parsed", True)]
    if collection == "bible":
        return sorted(os.path.relpath(p, base)
                      for p in glob(os.path.join(base, "eng-web-c_usfm", "*.usfm")))
    if collection == "catechism":
        return ["ccc.json"]
    if collection == "summa":
        return ["summa.xml"]
    raise ValueError(f"unknown collection {collection!r}")


def file_units(collection: str, source_file: str, sources: str = SOURCES) -> list[SourceUnit]:
    path = os.path.join(sources, collection, source_file)
    if source_file.endswith(".xml"):
        return thml_units(path, source_file)
    if source_file.endswith(".html"):
        return html_units(path, source_file)
    if source_file.endswith(".usfm"):
        return usfm_units(path, source_file)
    if source_file.endswith(".json"):
        return ccc_units(path, source_file)
    raise ValueError(f"no extractor for {source_file}")
