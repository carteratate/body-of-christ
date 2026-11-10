"""The First Vatican Council from Schaff's Creeds of Christendom, vol. 2 (1.2d).

CCEL's `creeds2.xml` prints Dei Filius and Pastor Aeternus in Manning's English (Petri
Privilegium, 1871) beside the Latin: one two-cell table per page, Latin in the cell that
holds `lang="LA"`, English in the other. Only the English cells are read (rule E). A
paragraph opens in a cell indented by `text-indent` and runs on through the unindented
cells after it, across the page's table; a centred cell is a heading. Schaff's notes are
editor material (rule G): each one's scripture reference stays as the passage's footnote,
after the word it followed (`ingest.scripture_notes`; Carter, 1 Nov 2026), and the rest go.

Sessions 1 and 2 (the opening decree and the profession of faith) are not in Schaff. They
are gaps G10 and G11, and the document keeps the council's papalencyclicals.net page in
`metadata.held_text_url` for the reader's link (Carter, 4 Nov 2026).

Anchors: `first-vatican-council/dei-filius/prologue`, `.../dei-filius/chapter-3`,
`.../dei-filius/canons-3/canon-2`, `.../dei-filius/conclusion`,
`.../pastor-aeternus/prologue`, `.../pastor-aeternus/chapter-4`; each chapter, each group
of canons and each prologue and conclusion is a reader chapter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import defusedxml.ElementTree as ET

from config import settings
from identity import anchor as make_anchor, slugify
from ingest.common import _NOTE_MARK, _block_text, _unmark
from ingest.pieces import Segment, name_pieces, pack_units, piece_reference
from ingest.thml_doc import footnotes, notes_per_piece
from model import Document, Passage
from normalize.caps import smart_title_case
from normalize.text import clean_text
from registry import ANCHOR_SCHEME

SOURCE_FILE = "creeds2.xml"            # under sources/councils/
SECTION = "v.ii.i"                     # its title attribute is wrong; select it by id
URL = "https://ccel.org/ccel/schaff/creeds2/creeds2.v.ii.i.html"
TRANSLATION = "Henry Edward Manning (1871), in Philip Schaff, The Creeds of Christendom (1877)"
TEXT_REPLACED = "Manning's translation in Schaff replaces Tanner"

# The two constitutions, by the heading Schaff prints over each.
CONSTITUTIONS = {
    "Dogmatic Constitution on the Catholic Faith": ("dei-filius", "Dei Filius"),
    "First Dogmatic Constitution on the Church of Christ": ("pastor-aeternus", "Pastor Aeternus"),
}
_ROMAN = ("I", "II", "III", "IV")
_CHAPTER = re.compile(r"^Chapter ([IVX]+)\.$")
_CANON_GROUP = re.compile(r"^([IVX]+)\.$")
_CANON = re.compile(r"^(\d+)\.\s+(.+)$", re.DOTALL)
# CCEL heads Pastor Aeternus's first chapter "Chapter IV."; the print reads "Chapter I."
# (p. 258). Chapters are numbered by their order and the heading checked against it.
_CCEL_SLIPS = {("pastor-aeternus", 1): "IV"}
# Words where CCEL's transcription departs from the print, each read on the page image:
# (CCEL's text, the print's, the page).
CORRECTIONS = (
    ("true aud good", "true and good", "253"),
)


@dataclass
class _Paragraph:
    text: str
    notes: list[tuple[int, str]] = field(default_factory=list)   # (offset, note text)
    pages: list[str] = field(default_factory=list)

    def extend(self, text: str, notes: list[tuple[int, str]], page: str) -> None:
        at = len(self.text) + 1
        self.text += " " + text
        self.notes += [(at + k, n) for k, n in notes]
        if page not in self.pages:
            self.pages.append(page)


@dataclass
class _Unit:
    tail: str                 # its anchor under the council
    chapter: str              # its reader chapter under the council
    chapter_label: str
    unit_label: str
    reference: str
    paragraphs: list[_Paragraph] = field(default_factory=list)


@dataclass
class _Cell:
    kind: str                 # "heading", "line" (a cell set as its own paragraph), "opens", "runs-on"
    text: str
    notes: list[tuple[int, str]]
    page: str


def _is_latin(td) -> bool:
    return any(e.get("lang") == "LA" for e in td.iter())


def _corrected(text: str, notes: list[tuple[int, str]], page: str, applied: list[str]
               ) -> tuple[str, list[tuple[int, str]]]:
    for find, replace, on in CORRECTIONS:
        k = text.find(find)
        if k < 0:
            continue
        if on != page:
            raise ValueError(f"correction {find!r} found on p. {page}, not p. {on}")
        text = text[:k] + replace + text[k + len(find):]
        shift = len(replace) - len(find)
        notes = [(at + shift if at > k else at, t) for at, t in notes]
        applied.append(find)
    return text, notes


def _cells(section) -> list[_Cell]:
    """The English cells of the section, in order, each with its page, CORRECTIONS
    applied."""
    out: list[_Cell] = []
    applied: list[str] = []
    page = ""
    for el in section.iter():
        if el.tag == "pb":
            page = el.get("n") or page
        if el.tag != "td" or _is_latin(el):
            continue
        texts: list[str] = []
        text, marks = _unmark(_block_text(el, _NOTE_MARK, texts))
        if len(marks) != len(texts):
            raise ValueError(f"{el.get('id')}: a note outside the cell's text")
        if not text:
            continue
        style = el.get("style") or ""
        if "text-align:center" in style:
            kind = "heading"
        elif any(child.tag == "p" for child in el):
            kind = "line"
        elif "text-indent" in style:
            kind = "opens"
        else:
            kind = "runs-on"
        text, notes = _corrected(text, list(zip(marks, texts)), page, applied)
        out.append(_Cell(kind, text, notes, page))
    if sorted(applied) != sorted(find for find, _, _ in CORRECTIONS):
        raise ValueError(f"corrections applied {applied}, not once each")
    return out


def _units(cells: list[_Cell]) -> list[_Unit]:
    council = "First Vatican Council"
    units: list[_Unit] = []
    key = name = ""
    chapters = 0
    in_canons = False
    pending: str | None = None      # a chapter or canon group waiting for its subtitle
    group = ""

    def start(tail: str, chapter: str, chapter_label: str, unit_label: str) -> _Unit:
        unit = _Unit(tail, chapter, f"{name}, {chapter_label}", unit_label,
                     f"{council}, {name}, {unit_label}")
        units.append(unit)
        return unit

    for cell in cells:
        text = cell.text.strip()
        heading = text.rstrip(".")
        if cell.kind == "heading" and heading in CONSTITUTIONS:
            key, name = CONSTITUTIONS[heading]
            chapters, in_canons, pending = 0, False, None
            start(f"{key}/prologue", f"{key}/prologue", "Prologue", "Prologue")
            continue
        if not key:
            raise ValueError(f"text before the first constitution: {text[:60]!r}")
        if cell.kind in ("heading", "line"):
            if text.startswith("Published in the"):        # Manning's session line
                continue
            if text.startswith("PIUS"):                     # the intitulation
                units[-1].paragraphs.append(_Paragraph(smart_title_case(text), [], [cell.page]))
                continue
            m = _CHAPTER.match(text)
            if m:
                chapters += 1
                expected = _CCEL_SLIPS.get((key, chapters), _ROMAN[chapters - 1])
                if m.group(1) != expected:
                    raise ValueError(f"{name}: chapter {chapters} is headed {text!r}")
                pending = f"chapter-{chapters}"
                continue
            if text == "Canons.":
                in_canons = True
                continue
            m = _CANON_GROUP.match(text)
            if m and in_canons:
                group = str(_ROMAN.index(m.group(1)) + 1)
                pending = f"canons-{group}"
                continue
            if pending is None:
                raise ValueError(f"{name}: unexpected heading {text!r}")
            subtitle = heading
            if pending.startswith("chapter-"):
                roman = _ROMAN[int(pending.split("-")[1]) - 1]
                start(f"{key}/{pending}", f"{key}/{pending}",
                      f"Chapter {roman}: {subtitle}", f"Chapter {roman}")
            else:
                units.append(_Unit("", f"{key}/{pending}",
                                   f"{name}, Canons {_ROMAN[int(group) - 1]}: {subtitle}", "", ""))
            pending = None
            continue
        if cell.kind == "runs-on":
            if not units or not units[-1].paragraphs:
                raise ValueError(f"{name}: a cell runs on from nothing: {text[:60]!r}")
            units[-1].paragraphs[-1].extend(text, cell.notes, cell.page)
            continue
        canon = _CANON.match(text) if in_canons else None
        if canon:
            n = canon.group(1)
            group_unit = next(u for u in reversed(units) if u.chapter.endswith(f"/canons-{group}"))
            roman = _ROMAN[int(group) - 1]
            unit = _Unit(f"{key}/canons-{group}/canon-{n}", group_unit.chapter,
                         group_unit.chapter_label, f"Canon {roman}.{n}",
                         f"{council}, {name}, Canon {roman}.{n}")
            cut = len(text) - len(canon.group(2))
            unit.paragraphs.append(_Paragraph(canon.group(2),
                                              [(at - cut, t) for at, t in cell.notes],
                                              [cell.page]))
            units.append(unit)
            continue
        if in_canons and not units[-1].tail.endswith("/conclusion"):
            # The paragraphs after the last canon close the constitution.
            in_canons = False
            start(f"{key}/conclusion", f"{key}/conclusion", "Conclusion", "Conclusion")
        units[-1].paragraphs.append(_Paragraph(text, list(cell.notes), [cell.page]))
    return [u for u in units if u.tail]


def _passages(units: list[_Unit], year: int) -> list[Passage]:
    slug = slugify("First Vatican Council")
    out: list[Passage] = []
    for unit in units:
        if not unit.paragraphs:
            raise ValueError(f"{unit.tail}: no text")
        raw = "\n\n".join(p.text for p in unit.paragraphs)
        notes: list[tuple[int, str]] = []
        at = 0
        for p in unit.paragraphs:
            notes += [(at + k, t) for k, t in p.notes]
            at += len(p.text) + 2
        segments = [Segment(f"p{k}", p.text) for k, p in enumerate(unit.paragraphs, 1)]
        parts = [p.text for p in pack_units([(None, p.text) for p in unit.paragraphs],
                                            settings.MAX_PASSAGE_CHARS)]
        unit_anchor = make_anchor(slug, *unit.tail.split("/"))
        pages = list(dict.fromkeys(pg for p in unit.paragraphs for pg in p.pages))
        meta = {"council": "First Vatican Council", "year": year, "url": URL, "pages": pages,
                "text_replaced": TEXT_REPLACED}
        for k, (part, (anchor, held), part_notes) in enumerate(zip(
                parts, name_pieces(unit_anchor, raw, parts, segments),
                notes_per_piece(raw, parts, notes)), 1):
            content = clean_text(part)
            piece_meta = meta
            refs = footnotes(part, content, part_notes)
            if refs:
                piece_meta = {**meta, "footnotes": refs}
            out.append(Passage(content=content,
                               reference=piece_reference(unit.reference, None, None, k, len(parts)),
                               anchor=anchor, chapter_key=make_anchor(slug, *unit.chapter.split("/")),
                               chapter_label=unit.chapter_label, position=len(out),
                               unit_label=unit.unit_label, metadata=piece_meta,
                               source_units=held))
    return out


def read_units(path: str) -> list[_Unit]:
    root = ET.parse(path).getroot()
    section = next((e for e in root.iter() if e.get("id") == SECTION), None)
    if section is None:
        raise ValueError(f"{path}: no section {SECTION}")
    return _units(_cells(section))


def build_schaff(entry: dict, document_id: str, source_key: str, path: str) -> Document:
    return Document(id=document_id, collection="councils", title=entry["council"], author=None,
                    year=entry["year"], translation=TRANSLATION,
                    metadata={"url": URL, "held_text_url": entry["url"],
                              "council_number": entry.get("council_number"),
                              "source_key": source_key, "source_file": SOURCE_FILE,
                              "anchor_scheme": ANCHOR_SCHEME},
                    passages=_passages(read_units(path), entry["year"]))
