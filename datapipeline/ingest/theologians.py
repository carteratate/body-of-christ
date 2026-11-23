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

from xml.etree.ElementTree import Element      # builds an element, parses nothing

import defusedxml.ElementTree as ET

from model import Document
from normalize.caps import smart_title_case
from ingest.common import _block_text, _build_parent_map
from ingest.keys import THEOLOGIANS
from ingest.editorial import PLAIN_CALLERS, ChapterEdit, Editor, Removed
from ingest.thml_doc import ChapterPlan, _clip, make_doc

# The collection these works publish under; 5.1b.3 renames it in `ingest.keys`.
COLLECTION = THEOLOGIANS
SOURCE_DIR = "theologians"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", SOURCE_DIR)

CCEL_CREDIT = "Sourced via CCEL.org"
# The Devout Life's translation as the card names it (`card_notes._TRANSLATIONS`).
ANONYMOUS_1876 = "Anonymous translation (Rivingtons, 1876)"


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
# author's headings (the Life's arguments, which open their chapters through `lead`; a
# Treatise book's title; the Devout Life's contents), which the build never reads. The checks' extractor
# (`checks.source_text.thml_units`) reads both so.
NOT_BODY_CLASSES = {"teresa-castle2.xml": {"Outline": "apparatus"}}
HEADING_DIVS = {"teresa-life.xml": frozenset({"v"}),
                "desales-devout_life.xml": frozenset({"ii"}),
                # The Treatise's twelve book divs, ii to xiii (`_LOVE_BOOKS`).
                "desales-love.xml": frozenset({"ii", "iii", "iv", "v", "vi", "vii", "viii",
                                               "ix", "x", "xi", "xii", "xiii"})}
# Single paragraphs by id: in the Life, Báñez's signed note on the manuscript after
# Teresa's last line (ch. xl) and the transcriber's page marker "{p. 479}" (Relation XI).
NOT_BODY_PARAGRAPHS = {"teresa-life.xml": {"viii.xli-p58": "apparatus",
                                           "ix.xi-p12": "apparatus"},
                       # "THE END." after the Treatise's last chapter: the printer's.
                       "desales-love.xml": {"xiii.xiii-p17": "apparatus"}}


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
            marked = _GLUED_STEP.sub(r"\1 \2", marked)
            for printed, without in PLAIN_CALLERS.get((callers, block.get("id")), ()):
                marked = marked.replace(printed, without)
            for printed, read in TEXT_FIXES.get((self.source_file, block.get("id")), ()):
                marked = marked.replace(printed, read)
            if block.get("class") in self.title_classes:
                return marked, notes          # a title in capitals throughout stays so
            return _OPENING_CAPS.sub(_opening, marked, count=1), notes

        edit.edit = opened
        return edit


# A note's number printed in brackets just before the note (the Life, ch. xxvi and xxix):
# "vision.[8]" with note 8 after it. The note leaves; so does its call.
_NOTE_CALL = re.compile(r"\[\d+\](?=\u2063)")
# Words a file mistranscribes, by (file, paragraph id), each with the evidence: (as the
# file reads, as the edition prints). The Ninth Meditation's subject reads "upon to you";
# the same file's contents, from the same edition, prints "open to you".
TEXT_FIXES = {("desales-devout_life.xml", "iii.xvii-p2"): (("upon to you", "open to you"),)}
# A numbered step run on to the sentence before it with no space ("in the Presence of
# God.2. Humble yourself", the Devout Life's meditations VII to X): the space restored.
_GLUED_STEP = re.compile(r"([a-z][.!?”])(\d{1,2}\. [A-Z])")
# A printer's opening: the paragraph's first word (after its number) in capitals, or the
# word after an opening "I" ("1. I HAVE known", III ch. ii).
_OPENING_CAPS = re.compile(r"^(\s*(?:\d+\.\s+)?)(I\s+)?([A-Z][A-Z’']+)(?![a-z])")


def _opening(m: re.Match) -> str:
    word = m.group(3).lower() if m.group(2) else m.group(3).capitalize()
    return m.group(1) + (m.group(2) or "") + word



# --------------------------------------------------------------------------- de Sales

# Introduction to the Devout Life (Rivingtons, 1876): the author's preface (i.i) and the
# chapters of Parts I to V (iii to vii). Left out: the title page (i), the contents (ii),
# the subject index (viii) and CCEL's indexes (ix). The chapter titles are `<h2>` lines,
# not paragraphs, so they are labels only.
_DEVOUT_PARTS = ("iii", "iv", "v", "vi", "vii")
_PART = re.compile(r"^PART ([IVX]+)\.")
_CHAPTER = re.compile(r"^(?:CHAPTER|Chapter)\s+([IVXLC]+)\.?\s*(.*?)[\s.]*$")


def _devout_chapters(root):
    out = [(None, _div(root, "i.i"), ChapterPlan(label="Preface"))]
    for part_id in _DEVOUT_PARTS:
        part = _div(root, part_id)
        book = f"Part {_PART.match(part.get('title') or '').group(1)}"
        # The part's own heading ("PART I. COUNSELS AND PRACTICES SUITABLE…", `<h1>`)
        # opens its first chapter, level 1.
        lead = ((_text(part.find("h1")).rstrip(), 1),)
        for k, ch in enumerate(_div2s(part)):
            m = _CHAPTER.match(" ".join((ch.get("title") or "").split()))
            if not m:
                raise ValueError(f"desales-devout_life.xml: unexpected chapter title "
                                 f"{ch.get('title')!r}")
            out.append((book, ch, ChapterPlan(label=f"Chapter {m.group(1)}. {m.group(2)}",
                                              headings=_meditation_headings(ch),
                                              lead=lead if k == 0 else ())))
    return out


def _meditation_headings(chapter) -> tuple[tuple[str, int, bool], ...]:
    """The headings of one of Part I's ten meditations (chapters ix to xviii): its subject
    ("Of Creation.") as the chapter's first paragraph, level 2 under the label ("First
    Meditation"), and its parts ("Preparation.", "Considerations.", "Affections and
    Resolutions.", "Conclusion.", "The Choice."), each a paragraph in italics only, level
    3. No other chapter prints a paragraph in italics only."""
    paras = [b for b in chapter if b.tag == "p" and _text(b)]
    parts = [b for b in paras if _italic_only(b)]
    if not parts:
        return ()
    subject = paras[0]
    if _italic_only(subject) or len(_text(subject)) > 80:
        raise ValueError(f"desales-devout_life.xml: meditation {chapter.get('id')!r} opens "
                         f"with no subject line")
    return ((subject.get("id"), 2, False),) + tuple((b.get("id"), 3, False) for b in parts)


def _italic_only(block) -> bool:
    kids = list(block)
    return (len(kids) == 1 and kids[0].tag == "i" and not (block.text or "").strip()
            and not (kids[0].tail or "").strip())


# Treatise on the Love of God (Mackey, about 1884; the TAN reprint of 1997): the author's
# dedicatory prayer (i.vii), his preface (i.viii) and the chapters of Books I to XII (ii
# to xiii). Left out: the cover, frontispiece, title page and TAN's dedication page (i.i to
# i.iv), Mackey's introduction (i.v), the contents (i.vi), TAN's list of its books
# (xiii.xiv), CCEL's indexes (xiv), and "THE END." after Book XII. A book's own text is
# its title only. Each chapter prints "CHAPTER N." (`<h3>`) and then its title as its
# first paragraph, which stays in the text as a marked heading.
_LOVE_BOOKS = ("ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii")
_LOVE_EDITOR_DIVS = frozenset({"xiii.xiv"})
_LOVE_TITLES = frozenset({"subhead", "subhead1", "smallhead"})
_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")


def _love_chapters(root):
    out = [(None, _div(root, "i.vii"), ChapterPlan(label="Dedicatory Prayer")),
           (None, _div(root, "i.viii"), ChapterPlan(label="Preface"))]
    for k, book_id in enumerate(_LOVE_BOOKS):
        book_div = _div(root, book_id)
        book = f"Book {_ROMAN[k]}"
        lead = ((_book_heading(book_div), 1),)
        for j, ch in enumerate(_div2s(book_div)):
            if ch.get("id") in _LOVE_EDITOR_DIVS:
                continue
            number = ch.find("h3")
            m = _CHAPTER.match(_text(number)) if number is not None else None
            first = next((b for b in ch if b.tag == "p" and _text(b)), None)
            if not m or first is None or first.get("class") not in _LOVE_TITLES:
                raise ValueError(f"desales-love.xml: chapter {ch.get('id')!r} prints no "
                                 f"number or title")
            # The label is the printed title (CCEL's typed div titles have slips: "Died by
            # and", "Signfied"); it repeats the title only when it holds it whole.
            title = smart_title_case(_text(first).upper()).rstrip(". ")
            full = f"Chapter {m.group(1)}. {title}"
            label = _clip(full)
            out.append((book, ch, ChapterPlan(label=label,
                                              headings=((first.get("id"), 1, label == full),),
                                              lead=lead if j == 0 else ())))
    return out


def _book_heading(book) -> str:
    """A Treatise book's own heading as printed over its first chapter, one line: "BOOK I.
    CONTAINING A PREPARATION FOR THE WHOLE TREATISE." The running title "THE LOVE OF
    GOD." over Book I is not part of it."""
    lines = [_text(c) for c in book if c.tag in ("h1", "h2", "h3", "p") and _text(c)]
    lines = [t for t in lines if t != "THE LOVE OF GOD."]
    return " ".join(lines)


def _div2s(parent):
    return [d for d in parent if isinstance(d.tag, str) and d.tag == "div2"]


# A paragraph the file closes mid-sentence: it ends on a lower-case word, a comma, a
# semicolon, a dash or the word "I", or the next part starts in lower case. A next part
# that opens with its section number ("25. The devils") is a paragraph of its own.
_OPEN_END = re.compile(r"(?:[a-z,;—-]|\bI)$")
_SECTION_START = re.compile(r"^\d+\.?\s")
# The classes a file gives its plain text paragraphs; any other class (a heading, an
# outline, a note) is never joined on.
_BODY_CLASSES = (None, "Body", "noindent")


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


# A class a file gives each line of a short verse quotation set as paragraphs (the
# Treatise's couplet from Pythagoras, II ch. xviii).
_VERSE_LINE_CLASSES = ("List7",)
# Verse lines a file sets as plain paragraphs, by `<p>` id: the Devout Life's closing
# couplet from St Francis's song (V ch. xviii).
_VERSE_LINES = {"desales-devout_life.xml": frozenset({"vii.xviii-p11", "vii.xviii-p12"})}
_VERSE_FILES = frozenset({"desales-love.xml", "desales-devout_life.xml"})


def _verse_blocks(chapters, work: ThmlWork) -> None:
    """Turn each verse quotation inside a chapter into a `<verse>` of `<l>` lines, which
    the builder reads as one paragraph, line by line, as it reads the Fathers' poems: a
    plain `<div>` of `<p>` lines (the Treatise's five, set as an indented block), and a
    run of `<p>` lines of a verse-line class or listed in `_VERSE_LINES`. Only the files
    in `_VERSE_FILES` print verse so."""
    if work.file not in _VERSE_FILES:
        return
    listed = _VERSE_LINES.get(work.file, frozenset())

    def is_line(block) -> bool:
        return block.tag == "p" and (block.get("class") in _VERSE_LINE_CLASSES
                                     or block.get("id") in listed)

    for chapter in chapters:
        kids = list(chapter)
        k = 0
        while k < len(kids):
            child = kids[k]
            if child.tag == "div" and all(line.tag == "p" for line in child):
                lines, run = list(child), [child]
            elif is_line(child):
                j = k
                while j < len(kids) and is_line(kids[j]):
                    j += 1
                lines = run = kids[k:j]
            else:
                k += 1
                continue
            verse = Element("verse", {"id": child.get("id")})
            for line in lines:
                line.tag = "l"
                verse.append(line)
            verse.tail = run[-1].tail
            position = list(chapter).index(run[0])
            for gone in run:
                if gone in list(chapter):
                    chapter.remove(gone)
            chapter.insert(position, verse)
            kids = list(chapter)
            k = position + 1


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
             translation="David Lewis (1904)", chapters=_life_chapters, genre="other"),
    # The 1876 translation names no translator (R6, the rights row).
    ThmlWork(file="desales-devout_life.xml",
             url="https://ccel.org/ccel/d/desales/devout_life.xml",
             title="Introduction to the Devout Life", author="Francis de Sales", year=1609,
             translation=ANONYMOUS_1876, chapters=_devout_chapters, genre="manual"),
    ThmlWork(file="desales-love.xml", url="https://ccel.org/ccel/d/desales/love.xml",
             title="Treatise on the Love of God", author="Francis de Sales", year=1616,
             translation="Henry Benedict Mackey (1884)", chapters=_love_chapters,
             genre="treatise",
             title_classes=_LOVE_TITLES),
)


def build_work(work: ThmlWork) -> Document:
    root = _read_root(os.path.join(_SRC, work.file))
    chapters = work.chapters(root)
    _verse_blocks([div for _, div, _ in chapters], work)
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
    return doc


def genre(source_key: str) -> str | None:
    """A work's genre by its source key (2.3's `document_facts`); None for another key."""
    return next((w.genre for w in WORKS if w.source_key == source_key), None)


def build_documents() -> list[Document]:
    return [build_work(w) for w in WORKS]
