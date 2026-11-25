"""Compendium of the Catechism of the Catholic Church (2005), corpus-cleanup 5.5.

Source: vatican.va's English page, vendored as `sources/catechism/compendium-ccc.html`.
Each of its 598 numbered questions is one passage: the question, its answer, and the
saints' sayings printed with it (the page's `blockquote`s and coloured quotations that
follow an answer before the next heading or question). The passage opens with the
question as printed, "12. Why does man have a desire for God?".

The line of Catechism paragraph numbers printed under each question ("27-30 44-45") is
kept out of the text, as `metadata["ccc_references"]`: a list of `[first, last]`
paragraph ranges, so the reader can link each to the CCC's own passages.

Chapters are the page's headings: Part, Section and Chapter, then up to two levels of
headings below a chapter ("Celebrating the Liturgy of the Church", "Who celebrates?"). A
passage's chapter is the nearest heading above it.

Not taken (spec 5.5 asks for the questions with their answers; listed in
NEEDS-CARTER.md): the motu proprio, the introduction, the appendix of prayers and
formulas, and the texts printed between sections (the Creeds, the list of the seven
sacraments, the Decalogue in Exodus, Deuteronomy and the catechetical formula, the Lord's
Prayer, and Augustine's saying before question 2), several of them in Latin. `build`
returns them as `skipped`, and the tests hold their list.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from identity import anchor as make_anchor  # noqa: E402
from ingest.catechism import _title  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from registry import ANCHOR_SCHEME, resolve_document_id  # noqa: E402

SOURCE_FILE = "compendium-ccc.html"
SOURCE_KEY = "catechism/compendium"
URL = ("https://www.vatican.va/archive/compendium_ccc/documents/"
       "archive_2005_compendium-ccc_en.html")
TITLE = "Compendium of the Catechism of the Catholic Church"
QUESTIONS = 598
CCC_LAST = 2865

_DEFAULT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "sources", "catechism", SOURCE_FILE)

# "12. Why …?", and "568 . What …?" where the page puts a space before the point.
_QUESTION = re.compile(r"^(\d{1,3})\s?\.\s+(.+)$", re.DOTALL)
# The line of CCC paragraph numbers under a question: "27-30 44-45", "75-79, 83, 96, 98".
_REFERENCES = re.compile(r"^[\d\s,;\-–]+$")
_RANGE = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?")
_PART = re.compile(r"^Part (One|Two|Three|Four)$", re.I)
_SECTION = re.compile(r"^Section (One|Two)\s+(.+)$", re.I | re.DOTALL)
_CHAPTER = re.compile(r"^CHAPTER (ONE|TWO|THREE|FOUR)$", re.I)
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4}
# A centred heading that opens one of the texts between sections, not a chapter.
_INSERT_HEADINGS = ("The Creed",)
_END = "APPENDIX"
# Misprinted references lines, by question: what the page prints, and the reading the
# Italian and French pages on vatican.va give (checked 21 Nov 2026).
REFERENCE_FIXES = {39: ("2112-213", "212-213")}


@dataclass
class _Heading:
    level: str          # "part", "section", "chapter", "head" or "subhead"
    title: str
    number: int | None = None
    sized: bool = False  # set in the page's larger heading size (font size 4)


@dataclass
class _Entry:
    number: int
    question: str
    chapter: tuple[str, str]
    references: list[list[int]] | None = None
    blocks: list[str] = field(default_factory=list)


@dataclass
class Build:
    document: Document
    skipped: list[str]      # opening words of each block left out, in page order


def _text(el: Tag) -> str:
    """An element's text with each line break as a space and whitespace collapsed. Inline
    tags join without a space, so "(<i>Matthew</i> 19:6)" stays "(Matthew 19:6)"."""
    for br in el.find_all("br"):
        br.replace_with(" ")
    return " ".join(el.get_text("").split())


def ccc_references(line: str) -> list[list[int]]:
    """`[first, last]` CCC paragraph ranges from a references line ("27-30 44-45")."""
    ranges = []
    for m in _RANGE.finditer(line):
        lo = int(m[1])
        hi = int(m[2]) if m[2] else lo
        if not 1 <= lo <= hi <= CCC_LAST:
            raise ValueError(f"compendium: CCC reference {m[0]!r} out of range")
        ranges.append([lo, hi])
    if not ranges:
        raise ValueError(f"compendium: no CCC reference in {line!r}")
    return ranges


def _blocks(corpo: Tag) -> list[Tag]:
    """The page's paragraphs and list items in reading order; a paragraph inside a list
    item is read with its item."""
    return [el for el in corpo.find_all(["p", "li"])
            if el.name == "li" or el.find_parent("li") is None]


class _Chapters:
    """The heading path above the current point, and the chapter it names."""

    def __init__(self) -> None:
        self.path: list[_Heading] = []
        self.pending: _Heading | None = None    # a Part or Chapter waiting for its title

    def heading(self, text: str, sized: bool) -> None:
        if self.pending is not None:
            self.pending.title = text
            self.pending = None
            return
        if m := _PART.match(text):
            self._open(_Heading("part", "", _NUMBERS[m[1].lower()]), "part")
            self.pending = self.path[-1]
        elif m := _SECTION.match(text):
            self._open(_Heading("section", m[2].strip(), _NUMBERS[m[1].lower()]), "section")
        elif m := _CHAPTER.match(text):
            self._open(_Heading("chapter", "", _NUMBERS[m[1].lower()]), "chapter")
            self.pending = self.path[-1]
        else:
            # A sized heading under an unsized one is a level below it ("Who celebrates?"
            # under "Celebrating the Liturgy of the Church"); any other opens a new head.
            head = next((h for h in self.path if h.level == "head"), None)
            level = "subhead" if sized and head is not None and not head.sized else "head"
            self._open(_Heading(level, text, sized=sized), level)

    def _open(self, heading: _Heading, level: str) -> None:
        order = ("part", "section", "chapter", "head", "subhead")
        keep = order[:order.index(level)]
        self.path = [h for h in self.path if h.level in keep] + [heading]

    def current(self) -> tuple[str, str]:
        """(chapter_key, chapter_label): "compendium/part-2/section-1/chapter-2/
        celebrating-the-liturgy-of-the-church/who-celebrates", "Part Two, Section One,
        Chapter Two, Celebrating the Liturgy of the Church, Who celebrates?". Numbered
        levels are named by number; the nearest numbered level's title is shown only when
        no heading sits below it."""
        if not self.path:
            raise ValueError("compendium: a question before the first Part")
        segments, names, titles = ["compendium"], [], []
        for h in self.path:
            if h.number is not None:
                segments.append(f"{h.level}-{h.number}")
                names.append(f"{h.level.capitalize()} {_word(h.number)}")
            else:
                segments.append(h.title)
                titles.append(_title(h.title))
        if not titles:
            titles = [_title(self.path[-1].title)]
        return make_anchor(*segments), ", ".join(names + titles)


def _word(number: int) -> str:
    return next(w for w, n in _NUMBERS.items() if n == number).capitalize()


def build(source_path: str | None = None, questions: int = QUESTIONS) -> Build:
    """The Compendium as one Document of `questions` passages, and what was left out."""
    with open(source_path or _DEFAULT_SRC, "rb") as f:
        soup = BeautifulSoup(f.read().decode("latin-1"), "html.parser")
    corpo = soup.find(id="corpo")
    chapters = _Chapters()
    entries: list[_Entry] = []
    skipped: list[str] = []
    entry: _Entry | None = None
    started = False
    for el in _blocks(corpo):
        text = _text(el)
        if not text:
            continue
        m = _QUESTION.match(text)
        is_question = (el.find("b") is not None and m is not None
                       and int(m[1]) == len(entries) + 1)
        if not started:
            # Before question 1: the contents list, the motu proprio and the introduction.
            # Only the headings straight above question 1 (Part One's) count.
            if not is_question:
                if el.get("align") == "center" and el.find("font") is not None:
                    chapters.heading(text, el.find("font").get("size") == "4")
                else:
                    chapters = _Chapters()
                continue
            started = True
        if text == _END:
            break
        if is_question:
            entry = _Entry(int(m[1]), text, chapters.current())
            entries.append(entry)
        elif el.get("align") == "center" or text in _INSERT_HEADINGS:
            entry = None
            if text in _INSERT_HEADINGS:
                skipped.append(text)
            else:
                font = el.find("font")
                chapters.heading(text, font is not None and font.get("size") == "4")
        elif entry is None:
            skipped.append(text)
        elif entry.references is None:
            if not _REFERENCES.match(text):
                raise ValueError(f"compendium: question {entry.number} has no CCC "
                                 f"references line ({text[:60]!r})")
            wrong, right = REFERENCE_FIXES.get(entry.number, (None, None))
            if wrong is not None:
                if text != wrong:
                    raise ValueError(f"compendium: question {entry.number}'s references "
                                     f"read {text!r}, not the misprint {wrong!r}")
                text = right
            entry.references = ccc_references(text)
        else:
            entry.blocks.append(text)
    if len(entries) != questions:
        raise ValueError(f"compendium: {len(entries)} questions, expected {questions}")

    did = resolve_document_id("catechism", SOURCE_KEY, ("catechism", "compendium"))
    passages = []
    for position, e in enumerate(entries):
        if not e.blocks:
            raise ValueError(f"compendium: question {e.number} has no answer")
        key, label = e.chapter
        passages.append(Passage(
            content=clean_text("\n\n".join([e.question, *e.blocks])),
            reference=f"Compendium of the Catechism, Q. {e.number}",
            anchor=make_anchor("q", e.number),
            chapter_key=key, chapter_label=label, position=position,
            unit_label=f"Q. {e.number}",
            metadata={"ccc_references": e.references}))
    document = Document(
        id=did, collection="catechism", title=TITLE, author=None, year=2005,
        metadata={"source": "vatican.va (English)", "source_key": SOURCE_KEY,
                  "source_file": SOURCE_FILE, "url": URL, "anchor_scheme": ANCHOR_SCHEME},
        passages=passages)
    return Build(document, skipped)


def build_document(source_path: str | None = None) -> Document:
    return build(source_path).document
