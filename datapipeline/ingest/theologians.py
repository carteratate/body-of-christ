"""Theologians and spiritual writers from CCEL ThML (corpus-cleanup 5.6b, issue #207).

Each work is one vendored ThML file under `sources/theologians/` and one entry in
`WORKS`: its labels, its dates and translation, and which of the file's divs are the
author's. The file's other divs (title page, editors' introductions and prefaces, annals,
indexes) are never read, so an editor's essay cannot reach a passage by default. Inside a
chapter, rule G drops the editors' paragraphs (`_TeresaEditor`), and their notes leave
the text as everywhere (`ingest.thml_doc`).

The works' own headings are chapter labels, never passage text. Where the author wrote a
longer heading than the label holds (each chapter of the Interior Castle opens "This
chapter treats of…"; Teresa's arguments of the Life's chapters stand together before the
book), it is kept whole as `metadata["heading"]` on the chapter's passages.

The documents join the collection `COLLECTION`, today's `medieval`, which 5.1b.3 renames
to `theologians`: that rename changes this one constant. The files stay in
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
from normalize.caps import roman_capitals
from ingest.common import _block_text, _build_parent_map
from ingest.editorial import PLAIN_CALLERS, ChapterEdit, Editor, Removed
from ingest.thml_doc import ChapterPlan, make_doc

# The collection these works publish under; 5.1b.3 renames it to "theologians".
COLLECTION = "medieval"
SOURCE_DIR = "theologians"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", SOURCE_DIR)

CCEL_CREDIT = "Sourced via CCEL.org"


@dataclass(frozen=True)
class ThmlWork:
    file: str                  # under sources/theologians/
    url: str                   # where CCEL serves it (the rights row's source_url)
    title: str
    author: str
    year: int                  # when the author finished it
    translator: str
    translation_year: int
    chapters: Callable         # root -> [(book, div, ChapterPlan)]
    genre: str                 # D5's writer value, or `other` (registry.genres)

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
    out = [(None, _div(root, "iv"), ChapterPlan(label="Preface"))]
    for mansion_id in _CASTLE_MANSIONS:
        mansion = _div(root, mansion_id)
        book = (mansion.get("title") or "").strip()
        for ch in mansion:
            if not (isinstance(ch.tag, str) and ch.tag == "div2"):
                continue
            if ch.get("id") in _CASTLE_EDITOR_DIVS:
                continue
            m = _CHAPTER_TITLE.match((ch.get("title") or "").strip())
            if not m:
                raise ValueError(f"teresa-castle2.xml: unexpected chapter title "
                                 f"{ch.get('title')!r}")
            heading = _castle_heading(ch)
            out.append((book, ch, ChapterPlan(
                label=f"Chapter {m.group(1)}. {m.group(2)}",
                meta={"heading": heading} if heading else None)))
    out.append((None, _div(root, "xii"), ChapterPlan(label="Epilogue")))
    return out


def _castle_heading(chapter) -> str | None:
    """Teresa's heading of a Castle chapter ("This chapter treats of…"), printed in
    capitals as the chapter's first `Centered` paragraph, in sentence case."""
    for block in chapter:
        if block.tag != "p" or not _text(block):
            continue          # an empty paragraph stands before it in VI ch. ii and IV
        return _sentence_case(_text(block)) if block.get("class") == "Centered" else None
    return None


def _sentence_case(text: str) -> str:
    """A heading printed in capitals, in sentence case: each sentence's first letter
    capital, and the words that are always capital (God, Our Lord, His Majesty, names)
    left to `_ALWAYS_CAPITAL`."""
    out = text.lower()
    out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    for word in _ALWAYS_CAPITAL:
        # "St." ends in no word character, so its end is not a word boundary.
        end = "" if word.endswith(".") else r"\b"
        out = re.sub(rf"\b{re.escape(word.lower())}{end}", word, out)
    return roman_capitals(out)


_ALWAYS_CAPITAL = (
    "God", "Our Lord", "Lord", "His Majesty", "Majesty", "Christ", "Jesus", "Holy Ghost",
    "Holy Spirit", "Blessed Trinity", "Trinity", "He", "Him", "His", "Himself", "Bridegroom",
    "Spouse", "King", "Teresa", "Carmel", "Discalced", "Carmelite", "Martha", "Mary",
    "Magdalen", "Mother of God", "Saviour", "St.", "Saint", "Church", "Catholic", "Gospel", "Communion", "I")


# The Life (Lewis, 1904): Teresa's prologue and forty chapters, then the Relations she
# wrote for her confessors, which Lewis prints after them. Left out: the frontispiece and
# title page (i, ii), the contents (iii), Zimmerman's introduction (iv), Teresa's
# arguments of the chapters gathered before the book (v; each is kept as its chapter's
# heading), Lewis's preface (vi), the annals (vii), the index (x) and CCEL's indexes (xi).
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
        # Lewis's; Teresa's own heading is the chapter's `heading`.
        subject = _FIRST_SENTENCE.split(_text(argument), 1)[0].rstrip(".")
        out.append((None, ch, ChapterPlan(label=f"Chapter {n}. {subject}",
                                          meta={"heading": headings[n]})))
    for rel in relations:
        if not (isinstance(rel.tag, str) and rel.tag == "div2"):
            continue
        if (rel.get("type") or "").lower() != "relation" or not rel.get("n"):
            raise ValueError(f"teresa-life.xml: unexpected div {rel.get('id')!r} in the "
                             f"Relations")
        out.append(("The Relations", rel, ChapterPlan(label=f"Relation {rel.get('n')}")))
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
# by class (heading: the author's heading, kept as `heading`; apparatus: an editor's), and
# divs whose text is the author's headings, kept as each chapter's `heading`. The editor
# drops them, and the checks' extractor (`checks.source_text.thml_units`) reads them so.
NOT_BODY_CLASSES = {"teresa-castle2.xml": {"Centered": "heading", "Outline": "apparatus"}}
HEADING_DIVS = {"teresa-life.xml": frozenset({"v"})}


def not_body(source_file: str) -> tuple[dict[str, str], frozenset[str]]:
    """`NOT_BODY_CLASSES` and `HEADING_DIVS` for a source file named as the checks name
    it (`../theologians/<file>`); empty for any other file."""
    prefix = f"../{SOURCE_DIR}/"
    if not source_file.startswith(prefix):
        return {}, frozenset()
    name = source_file[len(prefix):]
    return NOT_BODY_CLASSES.get(name, {}), HEADING_DIVS.get(name, frozenset())


class _TeresaEditor(Editor):
    """Rule G for the Teresa files, beyond the editors' lines `Editor` finds. The Castle's
    chapters open with Teresa's heading in capitals (`Centered`, kept as the chapter's
    `heading`) and Zimmerman's outline of the chapter's numbered paragraphs (`Outline`,
    "1. Plan of this book. 2. …"), and its preface with Teresa's title line in capitals
    (`Centered`): none is passage text. The Life's Relations open with Teresa's title
    page of them, Lewis's set lines.

    The Castle also prints the first word of a chapter's first paragraph in capitals
    ("1. WHILE I was begging"), a printer's opening, which is set in normal case ("1.
    While I was begging"). Two of the Life's notes are called by a bracketed number,
    which leaves with them. No paragraph of either file opens with a word that is
    capitals of its own. A caller printed as a plain digit is read without it
    (`ingest.editorial.PLAIN_CALLERS`)."""

    def chapter(self, elem, label: str) -> ChapterEdit:
        edit = super().chapter(elem, label)
        for block in elem:
            if block.tag != "p":
                continue
            kind = NOT_BODY_CLASSES.get(self.source_file, {}).get(block.get("class"))
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
            return _OPENING_CAPS.sub(lambda m: m.group(1) + m.group(2).capitalize(),
                                     marked, count=1), notes

        edit.edit = opened
        return edit


# A note's number printed in brackets just before the note (the Life, ch. xxvi and xxix):
# "vision.[8]" with note 8 after it. The note leaves; so does its call.
_NOTE_CALL = re.compile(r"\[\d+\](?=\u2063)")
# A printer's opening: the paragraph's first word (after its number) in capitals.
_OPENING_CAPS = re.compile(r"^(\s*(?:\d+\.\s+)?)([A-Z][A-Z’']+)(?![a-z])")


WORKS: tuple[ThmlWork, ...] = (
    ThmlWork(file="teresa-castle2.xml", url="https://ccel.org/ccel/t/teresa/castle2.xml",
             title="The Interior Castle", author="Teresa of Avila", year=1577,
             translator="Benedictines of Stanbrook", translation_year=1921,
             chapters=_castle_chapters, genre="treatise"),
    ThmlWork(file="teresa-life.xml", url="https://ccel.org/ccel/t/teresa/life.xml",
             title="The Life of St. Teresa of Jesus", author="Teresa of Avila", year=1565,
             translator="David Lewis", translation_year=1904, chapters=_life_chapters,
             genre="other"),
)


def build_work(work: ThmlWork) -> Document:
    root = _read_root(os.path.join(_SRC, work.file))
    parent_map = _build_parent_map(root)
    editor = _TeresaEditor(work.file, work.source_key, parent_map)
    doc = make_doc(collection=COLLECTION, filename=f"../{SOURCE_DIR}/{work.file}",
                   author=work.author, title=work.title,
                   chapters=work.chapters(root), source_key=work.source_key,
                   year=work.year, extra_meta={"source_url": work.url}, editor=editor)
    if doc is None:
        raise ValueError(f"{work.file}: no passages")
    doc.translation = f"{work.translator} ({work.translation_year})"
    return doc


def genre(source_key: str) -> str | None:
    """A work's genre by its source key (2.3's `document_facts`); None for another key."""
    return next((w.genre for w in WORKS if w.source_key == source_key), None)


def build_documents() -> list[Document]:
    return [build_work(w) for w in WORKS]
