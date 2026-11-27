"""Project Gutenberg plain-text works (corpus cleanup 5.6b, #207), read into the element
tree `ingest.thml_doc.make_doc` builds documents from.

A Gutenberg file holds the book between its `*** START OF … ***` and `*** END OF … ***`
lines, with Project Gutenberg's header before and its licence after; both go. The text
is paragraphs separated by blank lines, a paragraph's lines wrapped, italics marked
`_thus_`. A book prints its notes in one of three ways, which a work's `NoteStyle`
names: together after the text under a heading of their own ("FOOTNOTES", "NOTES:"),
perhaps with an index after them; in a block under such a heading after each chapter
(Newman's Development); or each as a paragraph of its own just after the paragraph that
calls it (Newman's Apologia). A note may run on into a second paragraph. Each note is
matched to its caller by its label, in reading order, so numbering that restarts is
matched rightly and a bracketed or list number that calls no note is left as it is.

`read_root` returns a `<ThML>` root holding one `<div1 id="text">` of `<p id="p<k>">`
paragraphs in order (k counts the book's paragraphs from 1, its notes and their headings
not counted), each note put back as a `<note>` at its caller, as a ThML file holds them,
so rule G removes and counts it the same way. An adapter's chapter plan then moves the
paragraphs into chapter divs (`ingest.theologians`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class NoteStyle:
    """How a book prints its notes. `caller` finds a call in the text and `note` a note
    paragraph, each with the label as group 1 (`note` has the text as group 2). With
    `heading`, the notes stand under that heading: once after the text (ended by `end`,
    the rest of the book left out) or, with `repeated`, after each chapter, each block
    ended by a heading in capitals. With `inline`, any paragraph `note` matches is one."""
    caller: re.Pattern = CALLER
    note: re.Pattern = NOTE
    heading: str | None = None
    repeated: bool = False
    inline: bool = False
    end: re.Pattern = INDEX


def _caps_line(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def split_notes(paras: list[tuple[str, bool]], style: NoteStyle | str | None
                ) -> tuple[list[tuple[str, bool]], list[tuple[str, str, int]]]:
    """The book's own paragraphs, and its notes as (label, text, place), place being the
    number of the book's paragraphs before the note. Without a style, all paragraphs
    and no notes."""
    if isinstance(style, str):
        style = NoteStyle(heading=style)
    if style is None:
        return paras, []
    body: list[tuple[str, bool]] = []
    notes: list[tuple[str, str, int]] = []
    texts = [text for text, _ in paras]
    k = 0
    while k < len(paras):
        text = texts[k]
        if style.inline and (m := style.note.match(text)):
            notes.append((m.group(1), m.group(2).strip(), len(body)))
            k += 1
            continue
        if style.heading is not None and text == style.heading:
            k += 1
            while k < len(paras):
                text = texts[k]
                if style.end.match(text) or (style.repeated and _caps_line(text)):
                    break
                m = style.note.match(text)
                if m:
                    notes.append((m.group(1), m.group(2).strip(), len(body)))
                elif notes:
                    label, prior, place = notes[-1]
                    notes[-1] = (label, prior + " " + text, place)  # its second paragraph
                k += 1
            if not style.repeated:
                break                     # the rest (an index) is left out
            continue
        body.append(paras[k])
        k += 1
    return body, notes


def match_notes(texts: list[str], notes: list[tuple[str, str, int]], style: NoteStyle
                ) -> dict[tuple[int, int], tuple[str, int, str]]:
    """Each note's caller, as (paragraph index, offset of the call) -> (the note's text,
    the call's end, its label):
    for each note in order, the first call with its label after the last one matched and
    in a paragraph before the note. A note with no caller is an error."""
    calls = [(k, m.start(), m.end(), m.group(1)) for k, text in enumerate(texts)
             for m in style.caller.finditer(text)]
    out: dict[tuple[int, int], tuple[str, int, str]] = {}
    i = 0
    for label, text, place in notes:
        j = next((j for j in range(i, len(calls))
                  if calls[j][3] == label and calls[j][0] < place), None)
        if j is None:
            raise ValueError(f"note {label!r} ({text[:40]!r}) has no caller")
        k, start, end, _ = calls[j]
        out[(k, start)] = (text, end, label)
        i = j + 1
    return out


def read_root(path: str, style: NoteStyle | str | None) -> Element:
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read().replace("\r\n", "\n")
    if isinstance(style, str):
        style = NoteStyle(heading=style)
    paras, notes = split_notes(paragraphs(book_text(raw)), style)
    called = match_notes([text for text, _ in paras], notes, style) if style else {}
    root = Element("ThML")
    div = Element("div1", {"id": "text"})
    root.append(div)
    for k, (para, italic) in enumerate(paras):
        # A paragraph set in italics throughout (a discourse's argument, a prayer's
        # subtitle) carries the class `italic`.
        p = Element("p", {"id": f"p{k + 1}", **({"class": "italic"} if italic else {})})
        _fill(p, para, sorted((start, end, text, label) for (pk, start), (text, end, label)
                              in called.items() if pk == k))
        div.append(p)
    return root


def _fill(p: Element, text: str, calls: list[tuple[int, int, str, str]]) -> None:
    """Set the paragraph's text with each called note, (start, end, note text, label) of
    its call, as a `<note n="label">` there."""
    last = None
    pos = 0
    for start, end, note, label in calls:
        before = text[pos:start]
        if last is None:
            p.text = (p.text or "") + before
        else:
            last.tail = (last.tail or "") + before
        last = Element("note", {"n": label})
        last.text = note
        p.append(last)
        pos = end
    if last is None:
        p.text = text
    else:
        last.tail = text[pos:]
