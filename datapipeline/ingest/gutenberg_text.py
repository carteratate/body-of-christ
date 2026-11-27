"""Project Gutenberg plain-text works (corpus cleanup 5.6b, #207), read into the element
tree `ingest.thml_doc.make_doc` builds documents from.

A Gutenberg file holds the book between its `*** START OF … ***` and `*** END OF … ***`
lines, with Project Gutenberg's header before and its licence after; both go. The text
is paragraphs separated by blank lines, a paragraph's lines wrapped, italics marked
`_thus_`. A book's notes stand together after the text under a heading of their own
("FOOTNOTES", "NOTES:"), each "[1] …" or "[1: …]", perhaps running on into a second
paragraph, called in the text by "[1]"; an index may follow them.

`read_root` returns a `<ThML>` root holding one `<div1 id="text">` of `<p id="p<k>">`
paragraphs in order (k counts the book's paragraphs from 1), each note put back as a
`<note>` at its caller, as a ThML file holds them, so rule G removes and counts it the
same way. The paragraphs after the notes (an index) are left out. An adapter's chapter
plan then moves the paragraphs into chapter divs (`ingest.theologians`).
"""
from __future__ import annotations

import re
from xml.etree.ElementTree import Element

START = re.compile(r"^\*\*\* ?START OF TH(?:E|IS) PROJECT GUTENBERG EBOOK.*\*\*\* *$", re.M)
END = re.compile(r"^\*\*\* ?END OF TH(?:E|IS) PROJECT GUTENBERG EBOOK.*\*\*\* *$", re.M)
CALLER = re.compile(r"\[(\d+)\]")
# "[1] Mater quidem …" (the Glories of Mary) or "[1: Gal. i, 10; …]" (Brother Lawrence).
NOTE = re.compile(r"^\[(\d+)(?:\]\s*|:\s*)(.*?)\]?$", re.S)
INDEX = re.compile(r"^INDEX\.?$")
ILLUSTRATION = re.compile(r"^\[Illustration\b.*\]$", re.S)
ITALIC = re.compile(r"_([^_]+)_")
ALL_ITALIC = re.compile(r"^_[^_]+_\.?$")


def book_text(raw: str) -> str:
    """The book: what stands between the START and END lines."""
    start, end = START.search(raw), END.search(raw)
    if not start or not end:
        raise ValueError("no Project Gutenberg START and END lines")
    return raw[start.end():end.start()]


def paragraphs(text: str) -> list[tuple[str, bool]]:
    """The text's paragraphs, each on one line (its wrapped lines joined by a space),
    italic marks and illustrations' captions out, each with whether it was set in
    italics throughout."""
    out = []
    for block in re.split(r"\n[ \t]*\n", text):
        para = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if not para or ILLUSTRATION.match(para):
            continue
        out.append((ITALIC.sub(r"\1", para), bool(ALL_ITALIC.match(para))))
    return out


def split_notes(paras: list[tuple[str, bool]], heading: str | None
                ) -> tuple[list[tuple[str, bool]], dict[str, str]]:
    """The book's paragraphs before its notes heading, and its notes by number. Without
    a heading, all paragraphs and no notes."""
    if heading is None:
        return paras, {}
    at = [text for text, _ in paras].index(heading)
    notes: dict[str, str] = {}
    last = None
    for para, _ in paras[at + 1:]:
        if INDEX.match(para):
            break                         # the notes end; an index follows
        m = NOTE.match(para)
        if m:
            last = m.group(1)
            notes[last] = m.group(2).strip()
        elif last is not None:
            notes[last] += " " + para     # a note's second paragraph
    return paras[:at], notes


def read_root(path: str, notes_heading: str | None) -> Element:
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read().replace("\r\n", "\n")
    paras, notes = split_notes(paragraphs(book_text(raw)), notes_heading)
    root = Element("ThML")
    div = Element("div1", {"id": "text"})
    root.append(div)
    for k, (para, italic) in enumerate(paras, 1):
        # A paragraph set in italics throughout (a discourse's argument, a prayer's
        # subtitle) carries the class `italic`.
        p = Element("p", {"id": f"p{k}", **({"class": "italic"} if italic else {})})
        _fill(p, para, notes)
        div.append(p)
    return root


def _fill(p: Element, text: str, notes: dict[str, str]) -> None:
    """Set the paragraph's text with each called note as a `<note>` at its caller."""
    last = None
    pos = 0
    for m in CALLER.finditer(text):
        if m.group(1) not in notes:
            continue                      # a bracketed number that is no caller
        before = text[pos:m.start()]
        if last is None:
            p.text = (p.text or "") + before
        else:
            last.tail = (last.tail or "") + before
        last = Element("note", {"n": m.group(1)})
        last.text = notes[m.group(1)]
        p.append(last)
        pos = m.end()
    if last is None:
        p.text = text
    else:
        last.tail = text[pos:]
