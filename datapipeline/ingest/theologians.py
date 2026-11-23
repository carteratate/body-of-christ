"""Theologians and spiritual writers from CCEL ThML (corpus-cleanup 5.6b, issue #207).

Each work is one vendored ThML file under `sources/theologians/` and one entry in
`WORKS`: its labels, its dates and translation, and which of the file's divs are the
author's. The file's other divs (title page, editors' introductions and prefaces, annals,
indexes) are never read, so an editor's essay cannot reach a passage by default. Inside a
chapter, rule G drops the editors' paragraphs (`_WorkEditor`), and their notes leave
the text as everywhere (`ingest.thml_doc`).

The works' own headings are chapter labels, and a heading the work prints longer than
its label stays in the text, marked through `headings.py` (#445; Carter, 23 Nov 2026):
each chapter of the Interior Castle opens with Teresa's "This chapter treats of…", her
arguments of the Life's chapters (printed together before the book) each open their
chapter, and a book's, part's or mansion's own heading opens its first chapter. Levels:
1 for a division the label names, 2 below it, 3 deeper (`headings.py`).

The documents join the collection `COLLECTION`, today's `medieval`, which 5.1b.3 renames
to `theologians`: that rename changes the one constant `ingest.keys.THEOLOGIANS`. The files stay in
`sources/theologians/` (5.1b.3 keeps source directory names), and each document's source
key is its file's path there, so neither changes with the key.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

import defusedxml.ElementTree as ET

from model import Document
from ingest.common import _block_text, _build_parent_map
from ingest.keys import THEOLOGIANS
from ingest.editorial import PLAIN_CALLERS, ChapterEdit, Editor, Removed
from ingest.thml_doc import ChapterPlan, make_doc

# The collection these works publish under; 5.1b.3 renames it in `ingest.keys`.
COLLECTION = THEOLOGIANS
SOURCE_DIR = "theologians"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", SOURCE_DIR)

CCEL_CREDIT = "Sourced via CCEL.org"
# Teresa's headings of the Life's chapters are not Lewis's: he left them out, following
# Bouix, and Zimmerman's introduction to the 1904 edition prints them before the book.
LIFE_NOTE = ("Each chapter opens with Teresa's own heading, which Lewis's translation "
             "left out; it is given as Benedict Zimmerman's 1904 edition prints it.")


@dataclass(frozen=True)
class ThmlWork:
    file: str                  # under sources/theologians/
    url: str                   # where CCEL serves it (the rights row's source_url)
    title: str
    author: str
    year: int                  # when the author finished it
    translation: str           # as the card reads it after "Translated by", or whole
    chapters: Callable         # root -> [(book, div, ChapterPlan)]
    genre: str                 # D5's writer value, or `other` (registry.genres)
    # Paragraph classes the work prints its own headings in (a chapter's title, Teresa's
    # chapter headings): kept in the text though they repeat a title line, and set as
    # printed (no opening-capitals change); the chapter plans mark them.
    title_classes: frozenset[str] = frozenset()
    notes: str | None = None   # the document's note (2.3's `notes`)

    @property
    def source_key(self) -> str:
        return f"{SOURCE_DIR}/{self.file}"


def _read_root(path: str):
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


def _div(root, div_id: str):
    for d in root.iter():
        if isinstance(d.tag, str) and d.tag.startswith("div") and d.get("id") == div_id:
            return d
    raise ValueError(f"no div {div_id!r}")


def _text(elem) -> str:
    return " ".join(_block_text(elem).split())


# --------------------------------------------------------------------------- Teresa

# The Interior Castle (Stanbrook, 1921): Teresa's preface, the seven mansions' chapters
# and her epilogue. Left out: the title page (i), Zimmerman's note on the edition (ii),
# his introduction (iii), his introductory note to VI, ch. iii (x.iii), the subject
# index (xiii) and CCEL's indexes (xiv).
_CASTLE_MANSIONS = ("v", "vi", "vii", "viii", "ix", "x", "xi")
_CASTLE_EDITOR_DIVS = frozenset({"x.iii"})
# "Chapter II. The Human Soul." -> "Chapter II. The Human Soul"
_CHAPTER_TITLE = re.compile(r"^Chapter ([IVXLC]+)\.\s+(.+?)\.?$")


def _castle_chapters(root):
    preface = _div(root, "iv")
    out = [(None, preface, ChapterPlan(label="Preface", headings=_castle_heading(preface)))]
    for mansion_id in _CASTLE_MANSIONS:
        mansion = _div(root, mansion_id)
        book = (mansion.get("title") or "").strip()
        # The mansion's own heading ("THE FIRST MANSIONS", `<h1>`) opens its first chapter.
        lead = ((_text(mansion.find("h1")), 1),)
        first = True
        for ch in mansion:
            if not (isinstance(ch.tag, str) and ch.tag == "div2"):
                continue
            if ch.get("id") in _CASTLE_EDITOR_DIVS:
                continue
            m = _CHAPTER_TITLE.match((ch.get("title") or "").strip())
            if not m:
                raise ValueError(f"teresa-castle2.xml: unexpected chapter title "
                                 f"{ch.get('title')!r}")
            out.append((book, ch, ChapterPlan(label=f"Chapter {m.group(1)}. {m.group(2)}",
                                              headings=_castle_heading(ch),
                                              lead=lead if first else ())))
            first = False
    out.append((None, _div(root, "xii"), ChapterPlan(label="Epilogue")))
    return out


def _castle_heading(chapter) -> tuple[tuple[str, int, bool], ...]:
    """Teresa's heading of a Castle chapter ("THIS CHAPTER TREATS OF…"), or her title
    line over the preface, printed in capitals as the div's first `Centered` paragraph:
    level 2, under the chapter's label."""
    for block in chapter:
        if block.tag != "p" or not _text(block):
            continue          # an empty paragraph stands before it in VI ch. ii and IV
        return ((block.get("id"), 2, False),) if block.get("class") == "Centered" else ()
    return ()


# The Life (Lewis, 1904): Teresa's prologue and forty chapters, then the Relations she
# wrote for her confessors, which Lewis prints after them. Left out: the frontispiece and
# title page (i, ii), the contents (iii), Zimmerman's introduction (iv), Teresa's
# arguments of the chapters gathered before the book (v; each opens its chapter, level 2),
# Lewis's preface (vi), the annals (vii), the index (x) and CCEL's indexes (xi).
# A sentence's end in an argument line; "St." is not one.
_FIRST_SENTENCE = re.compile(r"(?<!\bSt)\.\s+")
_LIFE_ARGUMENT = re.compile(r"^(?:J\.H\.S\.\s*)?Chapter ([IVXLC]+)\.\s*[—-]+\s*(.+)$")


def _life_chapters(root):
    headings = _life_headings(_div(root, "v"))
    life, relations = _div(root, "viii"), _div(root, "ix")
    out = []
    for ch in life:
        if not (isinstance(ch.tag, str) and ch.tag == "div2"):
            continue
        kind = (ch.get("type") or "").lower()
        if kind == "prologue":
            out.append((None, ch, ChapterPlan(label="Prologue")))
            continue
        if kind != "chapter":
            raise ValueError(f"teresa-life.xml: unexpected div {ch.get('id')!r} in the Life")
        n = (ch.get("n") or "").strip()
        argument = ch.find("argument")
        if argument is None or not n:
            raise ValueError(f"teresa-life.xml: chapter {ch.get('id')!r} has no number "
                             f"or argument")
        # The label takes the first sentence of the edition's argument line, which is
        # Lewis's; Teresa's own heading opens the chapter's text, level 2.
        subject = _FIRST_SENTENCE.split(_text(argument), 1)[0].rstrip(".")
        out.append((None, ch, ChapterPlan(label=f"Chapter {n}. {subject}",
                                          lead=((headings[n], 2),))))
    # "The Relations." (`<h2>`) opens the first of them, level 1.
    lead = ((_text(relations.find("h2")), 1),)
    for rel in relations:
        if not (isinstance(rel.tag, str) and rel.tag == "div2"):
            continue
        if (rel.get("type") or "").lower() != "relation" or not rel.get("n"):
            raise ValueError(f"teresa-life.xml: unexpected div {rel.get('id')!r} in the "
                             f"Relations")
        out.append(("The Relations", rel, ChapterPlan(label=f"Relation {rel.get('n')}",
                                                      lead=lead)))
        lead = ()
    return out


def _life_headings(arguments) -> dict[str, str]:
    """Teresa's own heading of each chapter of the Life, by its Roman number, from "St.
    Teresa's Arguments of the Chapters" (div v), notes left out."""
    out = {}
    for block in arguments:
        if block.tag != "p":
            continue
        m = _LIFE_ARGUMENT.match(_text(block))
        if m:
            out[m.group(1)] = m.group(2).strip()
    if len(out) != 40:
        raise ValueError(f"teresa-life.xml: {len(out)} chapter arguments, not 40")
    return out


# What is no passage text though it stands in the author's chapters, by file: paragraphs
# by class (an editor's), which the editor drops; and divs whose own paragraphs are the
# author's headings (the Life's arguments, which open their chapters through `lead`),
# which the build never reads. The checks' extractor (`checks.source_text.thml_units`)
# reads both so.
NOT_BODY_CLASSES = {"teresa-castle2.xml": {"Outline": "apparatus"}}
HEADING_DIVS = {"teresa-life.xml": frozenset({"v"})}
# Single paragraphs by id: in the Life, Báñez's signed note on the manuscript after
# Teresa's last line (ch. xl) and the transcriber's page marker "{p. 479}" (Relation XI);
# in the Castle, the printers' colophon.
NOT_BODY_PARAGRAPHS = {"teresa-life.xml": {"viii.xli-p58": "apparatus",
                                           "ix.xi-p12": "apparatus"},
                       # The printers' colophon after the Castle's last "Amen" ("HERE ENDS
                       # THE INTERIOR CASTLE … PRINTED BY THE BENEDICTINES OF STANBROOK").
                       "teresa-castle2.xml": {"xii-p3": "apparatus"}}


def not_body(source_file: str) -> tuple[dict[str, str], frozenset[str], dict[str, str]]:
    """`NOT_BODY_CLASSES`, `HEADING_DIVS` and `NOT_BODY_PARAGRAPHS` for a source file
    named as the checks name it (`../theologians/<file>`); empty for any other file."""
    prefix = f"../{SOURCE_DIR}/"
    if not source_file.startswith(prefix):
        return {}, frozenset(), {}
    name = source_file[len(prefix):]
    return (NOT_BODY_CLASSES.get(name, {}), HEADING_DIVS.get(name, frozenset()),
            NOT_BODY_PARAGRAPHS.get(name, {}))


class _WorkEditor(Editor):
    """Rule G for these files, beyond the editors' lines `Editor` finds. The Castle's
    chapters open with Zimmerman's outline of the chapter's numbered paragraphs
    (`Outline`, "1. Plan of this book. 2. …"), which goes; Teresa's heading in capitals
    before it (`Centered`) stays, marked. In the Life, two single paragraphs go by id
    (`NOT_BODY_PARAGRAPHS`).

    The Castle also prints the first word of a chapter's first paragraph in capitals
    ("1. WHILE I was begging"), a printer's opening, which is set in normal case ("1.
    While I was begging"; "1. I HAVE known" to "1. I have known"). Two of the Life's notes are called by a bracketed number,
    which leaves with them. No paragraph of either file opens with a word that is
    capitals of its own. A caller printed as a plain digit is read without it
    (`ingest.editorial.PLAIN_CALLERS`)."""

    def __init__(self, *args, title_classes: frozenset[str] = frozenset(), **kwargs):
        super().__init__(*args, **kwargs)
        self.title_classes = title_classes

    def chapter(self, elem, label: str) -> ChapterEdit:
        edit = super().chapter(elem, label)
        for block in elem:
            # A title the work prints as the chapter's first paragraph is marked, not
            # dropped, though it repeats the label `Editor` would drop it for.
            if block.tag == "p" and block.get("class") in self.title_classes \
                    and edit.dropped.get(id(block)) == "heading":
                del edit.dropped[id(block)]
                edit.removed = [x for x in edit.removed
                                if x.block != edit.locators[id(block)]]
        for block in elem:
            if block.tag != "p":
                continue
            kind = (NOT_BODY_PARAGRAPHS.get(self.source_file, {}).get(block.get("id"))
                    or NOT_BODY_CLASSES.get(self.source_file, {}).get(block.get("class")))
            kind = {"apparatus": "summary"}.get(kind, kind)
            if kind and id(block) not in edit.dropped:
                edit.dropped[id(block)] = kind
                edit.removed.append(Removed(edit.locators[id(block)], kind, _block_text(block)))
        inner = edit.edit

        callers = f"../{SOURCE_DIR}/{self.source_file}"

        def opened(block, marked, notes):
            marked, notes = inner(block, marked, notes)
            marked = _NOTE_CALL.sub("", marked)
            for printed, without in PLAIN_CALLERS.get((callers, block.get("id")), ()):
                marked = marked.replace(printed, without)
            if block.get("class") in self.title_classes:
                return marked, notes          # a title in capitals throughout stays so
            return _OPENING_CAPS.sub(_opening, marked, count=1), notes

        edit.edit = opened
        return edit


# A note's number printed in brackets just before the note (the Life, ch. xxvi and xxix):
# "vision.[8]" with note 8 after it. The note leaves; so does its call.
_NOTE_CALL = re.compile(r"\[\d+\](?=\u2063)")
# A printer's opening: the paragraph's first word (after its number) in capitals, or the
# word after an opening "I" ("1. I HAVE known", III ch. ii).
_OPENING_CAPS = re.compile(r"^(\s*(?:\d+\.\s+)?)(I\s+)?([A-Z][A-Z’']+)(?![a-z])")


def _opening(m: re.Match) -> str:
    word = m.group(3).lower() if m.group(2) else m.group(3).capitalize()
    return m.group(1) + (m.group(2) or "") + word



# A paragraph the file closes mid-sentence: it ends on a lower-case word, a comma, a
# semicolon, a dash or the word "I", or the next part starts in lower case. A next part
# that opens with its section number ("25. The devils") is a paragraph of its own.
_OPEN_END = re.compile(r"(?:[a-z,;—-]|\bI)$")
_SECTION_START = re.compile(r"^\d+\.?\s")
# The classes a file gives its plain text paragraphs; any other class (a heading, an
# outline, a note) is never joined on.
_BODY_CLASSES = (None,)


def _rejoin_split_paragraphs(chapters, work: ThmlWork) -> int:
    """Join each paragraph of the chapters the build reads that the CCEL file splits at a
    page break (`<pb>` between two `<p>`; the Life, 25 times) back into one, so a
    sentence is not cut by a paragraph break. A paragraph the build drops by id
    (`NOT_BODY_PARAGRAPHS`) between the two parts is passed over. Returns how many were
    joined."""
    skipped = NOT_BODY_PARAGRAPHS.get(work.file, {})
    joined = 0
    for parent in chapters:
        kids = list(parent)
        k = 0
        while k < len(kids):
            first = kids[k]
            if first.tag != "p" or first.get("id") in skipped:
                k += 1
                continue
            j = k + 1
            while j < len(kids) and (kids[j].tag == "pb" or kids[j].get("id") in skipped):
                j += 1
            nxt = kids[j] if j < len(kids) else None
            head, tail = _text(first), _text(nxt) if nxt is not None else ""
            if nxt is None or nxt.tag != "p" or not head or not tail \
                    or nxt.get("class") not in _BODY_CLASSES \
                    or _SECTION_START.match(tail) \
                    or not (_OPEN_END.search(head) or tail[0].islower()):
                k += 1
                continue
            _append(first, nxt)
            parent.remove(nxt)
            kids.pop(j)
            joined += 1
    return joined


def _append(first, nxt) -> None:
    """Move `nxt`'s text and children to the end of `first`, a space between."""
    text = " " + (nxt.text or "").lstrip()
    if len(first):
        first[-1].tail = (first[-1].tail or "").rstrip() + text
    else:
        first.text = (first.text or "").rstrip() + text
    first.extend(list(nxt))


WORKS: tuple[ThmlWork, ...] = (
    ThmlWork(file="teresa-castle2.xml", url="https://ccel.org/ccel/t/teresa/castle2.xml",
             title="The Interior Castle", author="Teresa of Avila", year=1577,
             translation="Benedictines of Stanbrook (1921)", chapters=_castle_chapters,
             genre="treatise", title_classes=frozenset({"Centered"})),
    ThmlWork(file="teresa-life.xml", url="https://ccel.org/ccel/t/teresa/life.xml",
             title="The Life of St. Teresa of Jesus", author="Teresa of Avila", year=1565,
             translation="David Lewis (1904)", chapters=_life_chapters, genre="other",
             notes=LIFE_NOTE),
)


def build_work(work: ThmlWork) -> Document:
    root = _read_root(os.path.join(_SRC, work.file))
    chapters = work.chapters(root)
    _rejoin_split_paragraphs([div for _, div, _ in chapters], work)
    parent_map = _build_parent_map(root)
    editor = _WorkEditor(work.file, work.source_key, parent_map,
                         title_classes=work.title_classes)
    doc = make_doc(collection=COLLECTION, filename=f"../{SOURCE_DIR}/{work.file}",
                   author=work.author, title=work.title,
                   chapters=chapters, source_key=work.source_key,
                   year=work.year, extra_meta={"source_url": work.url}, editor=editor)
    if doc is None:
        raise ValueError(f"{work.file}: no passages")
    doc.translation = work.translation
    doc.notes = work.notes
    return doc


def genre(source_key: str) -> str | None:
    """A work's genre by its source key (2.3's `document_facts`); None for another key."""
    return next((w.genre for w in WORKS if w.source_key == source_key), None)


def build_documents() -> list[Document]:
    return [build_work(w) for w in WORKS]
