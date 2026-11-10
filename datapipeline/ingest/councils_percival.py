"""Councils 1 to 7 from Percival, *The Seven Ecumenical Councils* (NPNF2 vol. 14, 1900) (1.2c).

CCEL's `npnf214.xml` prints each council's texts among Percival's introductions, excursus,
extracts from the acts and commentary. Only the divs in `COUNCILS` are read, an allowlist
taken from the 1.2a inventory (`docs/research/council-translation-inventory.md`): the
creeds, definitions, canons, anathemas, letters and decrees it marks "yes" (Carter, 4 Nov
2026), so an unrecognised div is dropped by default. Chalcedon's canons 29 and 30, the
anathemas against Origen and the iconoclast definition are left out (Decision log
"Percival's extra texts (1.2c)").

Inside an allowed div the council's text runs from its first paragraph to the one before
"Notes." or "Note.": from there on are the Ancient Epitome, the commentators and Percival's
notes. Headings (`HEADING_CLASSES`, and `TITLE_CLASS` before a text's first paragraph), Percival's source lines in parentheses ("(Found in
…)") and his bracketed connecting notes ("[Next was read …]") go wherever they stand.
His `<note>`s are editor material (1.10b); each one's scripture reference stays as the
passage's footnote, after the word it followed (`ingest.scripture_notes`).

Two texts Percival does not print come through the OCR tool (1.2f; R9, Carter, 4 Nov
2026): Nestorius's second letter to Cyril from James Chrystal (1895), without his
summaries or notes, read at Ephesus and condemned there (its passages carry `voice =
"rejected"` in the registry), and Nicaea II's four anathemas concerning holy images from
Hefele's account of the session (English vol. 5, 1896), each passage with a note saying
so in the registry.

Anchors name the text: `council-of-nicaea/creed`, `council-of-nicaea/canon/5`,
`council-of-ephesus/anathema/3`, `council-of-chalcedon/definition`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import defusedxml.ElementTree as ET

from config import settings
from identity import anchor as make_anchor, slugify
from ingest.common import _NOTE_MARK, _block_text, _unmark
from ingest.pieces import Segment, name_pieces, pack_units, piece_reference
from ingest.thml_doc import footnotes, notes_per_piece
from model import Document, Passage
from normalize.text import clean_text
from ocr.fixes import read_text
from registry import ANCHOR_SCHEME

SOURCE_FILE = "npnf214.xml"            # under sources/councils/
URL = "https://ccel.org/ccel/schaff/npnf214"
TRANSLATION = "Henry R. Percival, ed., The Seven Ecumenical Councils (NPNF2 vol. 14, 1900)"
TEXT_REPLACED = "Percival (NPNF2-14) replaces Tanner"
# Paragraph classes that are headings in CCEL's ThML: the div's title (c14), "Canon I."
# (c34, and c46 on Chalcedon's VIII and XIII), the Greek collections' title of each of
# Nicaea II's canons (c50), a letter's title line (c44). Class c31 is a heading too, and
# also marks "Notes.", which ends the text.
HEADING_CLASSES = frozenset({"c14", "c31", "c34", "c44", "c46", "c50"})
# Before a text's first paragraph, c35 is a title as well (eight of Nicaea II's canon
# titles); inside one it is the text's own (the creeds named in Chalcedon's Definition).
TITLE_CLASS = "c35"
_NOTES = re.compile(r"^Notes?\.$|^Note [IVX]+\.$")
_EDITOR_LINE = re.compile(r"^\(.*\)\.?$|^\[.*\]\.?$", re.DOTALL)


@dataclass(frozen=True)
class Text:
    """One unit of a council's document.

    `div` is the ThML div; `first` and `last` are paragraph ids within it (the part after
    the div's id: `p7`) where the text does not run from the div's first text paragraph to
    the one before its notes. `ocr` names a frozen OCR work (`ocr/texts/<work>.json`) in
    place of a div."""
    tail: str                  # its anchor under the council
    label: str                 # its unit label
    chapter: str               # its chapter key under the council
    chapter_label: str
    div: str = ""
    first: str | None = None
    last: str | None = None
    ocr: str = ""


def _canons(div: str, ids: list[str], label: str = "Canons") -> list[Text]:
    return [Text(f"canon/{n}", f"Canon {n}", "canons", label, f"{div}.{d}")
            for n, d in enumerate(ids, 1)]


_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii",
          "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv",
          "xxv", "xxvi", "xxvii", "xxviii", "xxix", "xxx", "xxxi"]


def _divs(*ks: int) -> list[str]:
    return [_ROMAN[k - 1] for k in ks]


# The allowlist, by the manifest's council name, in Percival's order.
COUNCILS: dict[str, list[Text]] = {
    "Council of Nicaea": [
        Text("creed", "The Creed", "creed", "The Nicene Creed", "vii.iii", first="p7"),
        *_canons("vii.vi", _divs(1, 3, 4, 5, 6, 8, 10, 12, 14, 15, 16, 18, 19, 21, 22, 24,
                                 25, 27, 28, 30)),
        Text("synodal-letter", "The Synodal Letter", "synodal-letter",
             "The Synodal Letter to the Egyptians", "vii.ix"),
    ],
    "First Council of Constantinople": [
        Text("creed", "The Creed", "creed", "The Creed of the 150 Fathers", "ix.iii",
             first="p6", last="p7"),
        Text("letter-to-theodosius", "Letter to Theodosius", "letter-to-theodosius",
             "Letter to the Emperor Theodosius", "ix.vi"),
        *_canons("ix.viii", _divs(1, 3, 4, 5, 6, 7, 9)),
        Text("synodical-letter", "The Synodical Letter", "synodical-letter",
             "The Synodical Letter (382)", "ix.ix"),
    ],
    "Council of Ephesus": [
        Text("cyril-second-letter", "Cyril's Second Letter", "cyril-second-letter",
             "Cyril's Second Letter to Nestorius", "x.v"),
        Text("nestorius-second-letter", "Nestorius's Second Letter", "nestorius-second-letter",
             "Nestorius's Second Letter to Cyril", ocr="chrystal-ephesus"),
        Text("cyril-third-letter", "Cyril's Third Letter", "cyril-third-letter",
             "Cyril's Third Letter to Nestorius", "x.viii"),
        *[Text(f"anathema/{n}", f"Anathema {n}", "anathemas", "The Twelve Anathemas of Cyril",
               f"x.ix.{d}")
          for n, d in enumerate(_divs(1, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14), 1)],
        Text("decree-against-nestorius", "Decree against Nestorius", "decree-against-nestorius",
             "Decree against Nestorius", "x.xi"),
        Text("synodical-letter", "Synodical Letter", "canons", "Synodical Letter and Canons",
             "x.xvi.i", first="p4", last="p5"),
        *_canons("x.xvi", _divs(2, 4, 5, 6, 8, 9, 10, 12), "Synodical Letter and Canons"),
        Text("letter-to-pamphylia", "Letter to the Synod in Pamphylia", "letter-to-pamphylia",
             "Letter to the Synod in Pamphylia", "x.xvi.xiii"),
        Text("letter-to-celestine", "Letter to Pope Celestine", "letter-to-celestine",
             "Letter to Pope Celestine", "x.xvi.xiv", first="p4"),
        Text("definition-against-the-messalians", "Definition against the Messalians",
             "definition-against-the-messalians", "Definition against the Messalians",
             "x.xvi.xv"),
        Text("decree-on-euprepius-and-cyril", "Decree on Euprepius and Cyril",
             "decree-on-euprepius-and-cyril", "Decree on Euprepius and Cyril", "x.xvi.xvii"),
        # Percival prints it with Chalcedon, which read it; Tanner with Ephesus, where the
        # live passages holding it are (the formula of union is inside it).
        Text("letter-to-john-of-antioch", "Cyril's Letter to John of Antioch",
             "letter-to-john-of-antioch", "Cyril's Letter to John of Antioch", "xi.v"),
    ],
    "Council of Chalcedon": [
        Text("tome-of-leo", "The Tome of Leo", "tome-of-leo", "The Tome of Leo", "xi.vii"),
        Text("condemnation-of-dioscorus", "Condemnation of Dioscorus",
             "condemnation-of-dioscorus", "The Condemnation Sent to Dioscorus", "xi.x"),
        Text("definition", "The Definition of Faith", "definition", "The Definition of Faith",
             "xi.xiii"),
        Text("decree-on-jerusalem-and-antioch", "Decree on Jerusalem and Antioch",
             "decree-on-jerusalem-and-antioch",
             "Decree on the Jurisdiction of Jerusalem and Antioch (Session VII)", "xi.xv"),
        Text("decree-on-the-bishop-of-ephesus", "Decree on the Bishop of Ephesus",
             "decree-on-the-bishop-of-ephesus",
             "Decree on the Bishop of Ephesus (Session XII)", "xi.xvi"),
        Text("decree-on-nicomedia", "Decree on Nicomedia", "decree-on-nicomedia",
             "Decree on Nicomedia (Session XIII)", "xi.xvii"),
        # Canons 1 to 28; Percival's 29 and 30 (`xi.xviii.xxx`, `.xxxi`) are left out.
        *_canons("xi.xviii", _ROMAN[:28]),
    ],
    "Second Council of Constantinople": [
        Text("sentence", "The Sentence of the Synod", "sentence", "The Sentence of the Synod",
             "xii.vi"),
        # One div holds all fourteen, each after its numeral; Percival's notes on XI stand
        # between XI and XII.
        *[Text(f"anathema/{n}", f"Anathema {n}", "anathemas", "The Fourteen Anathemas",
               "xii.vii", first=p, last=p)
          for n, p in enumerate(["p4", "p6", "p8", "p10", "p12", "p14", "p17", "p21", "p23",
                                 "p25", "p27", "p34", "p36", "p38"], 1)],
    ],
    "Third Council of Constantinople": [
        Text("sentence-against-the-monothelites", "Sentence against the Monothelites",
             "sentence-against-the-monothelites",
             "The Sentence against the Monothelites (Session XIII)", "xiii.viii"),
        Text("definition", "The Definition of Faith", "definition", "The Definition of Faith",
             "xiii.x"),
        Text("letter-to-agatho", "Letter to Pope Agatho", "letter-to-agatho",
             "Letter of the Council to Pope Agatho", "xiii.xii"),
    ],
    "Second Council of Nicaea": [
        # The Decree, without the acclamations Percival prints after it.
        Text("definition", "The Definition", "definition", "The Definition", "xvi.xii",
             last="p11"),
        Text("anathemas", "Anathemas concerning holy images", "anathemas",
             "Anathemas concerning Holy Images", ocr="hefele-nicaea-2"),
        *_canons("xvi.xiv", _ROMAN[:22]),
        Text("letter-to-the-emperors", "Letter to the Emperor and Empress",
             "letter-to-the-emperors", "Letter of the Synod to the Emperor and Empress",
             "xvi.xv"),
    ],
}
# The frozen OCR works, with the translation each names.
OCR_TRANSLATIONS = {
    "chrystal-ephesus": "James Chrystal (1895)",
    "hefele-nicaea-2": "William R. Clark, in Hefele's History of the Councils (1896)",
}


@dataclass
class _Paragraph:
    pid: str
    text: str
    notes: list[tuple[int, str]]


def _paragraphs(div, text: Text) -> list[_Paragraph]:
    """The council's paragraphs of `text`'s div (see the module docstring)."""
    div_id = div.get("id")
    started = text.first is None
    out: list[_Paragraph] = []
    for el in div:
        if el.tag not in ("p", "verse"):
            continue
        pid = (el.get("id") or "").removeprefix(f"{div_id}-")
        if not started:
            started = pid == text.first
            if not started:
                continue
        texts: list[str] = []
        body, marks = _unmark(_block_text(el, _NOTE_MARK, texts))
        if len(marks) != len(texts):
            raise ValueError(f"{div_id}-{pid}: a note outside the paragraph's text")
        if _NOTES.match(body):
            break
        title = el.get("class") in HEADING_CLASSES or (el.get("class") == TITLE_CLASS and not out)
        if body and not title and not _EDITOR_LINE.match(body):
            out.append(_Paragraph(pid, body, list(zip(marks, texts))))
        if pid == text.last:
            break
    if not started:
        raise ValueError(f"{div_id}: no paragraph {text.first}")
    if text.last is not None and (not out or out[-1].pid != text.last):
        raise ValueError(f"{div_id}: its text does not end at {text.last}")
    if not out:
        raise ValueError(f"{div_id}: no text")
    return out


_PART = re.compile(r"^(.+?)(?:-\d{2})?$")


def _ocr_paragraphs(work: str) -> tuple[list[_Paragraph], dict]:
    """A frozen OCR work's paragraphs, its passages for correction and the check joined
    back, and its metadata (`text_source`, `scan_id`) and pages."""
    frozen = read_text(work)
    joined = ""
    pages: list[str] = []
    for unit in frozen["passages"]:
        sep = "" if not joined else " " if unit.get("continues") else "\n\n"
        joined += sep + unit["text"]
        pages += [p for p in unit["pages"] if p]
    paragraphs = [_Paragraph(f"p{k}", p.strip(), [])
                  for k, p in enumerate(joined.split("\n\n"), 1) if p.strip()]
    meta = frozen["metadata"]
    return paragraphs, {"url": f"https://archive.org/details/{meta['scan_id']}", **meta,
                        "pages": list(dict.fromkeys(pages))}


def _passages(council: str, year: int, root_divs: dict) -> list[Passage]:
    slug = slugify(council)
    out: list[Passage] = []
    for text in COUNCILS[council]:
        if text.ocr:
            paragraphs, extra = _ocr_paragraphs(text.ocr)
            meta = {"council": council, "year": year, **extra}
        else:
            paragraphs = _paragraphs(root_divs[text.div], text)
            meta = {"council": council, "year": year, "url": f"{URL}/npnf214.{text.div}.html",
                    "text_replaced": TEXT_REPLACED}
        raw = "\n\n".join(p.text for p in paragraphs)
        notes: list[tuple[int, str]] = []
        at = 0
        for p in paragraphs:
            notes += [(at + k, t) for k, t in p.notes]
            at += len(p.text) + 2
        segments = [Segment(p.pid, p.text) for p in paragraphs]
        parts = [p.text for p in pack_units([(None, p.text) for p in paragraphs],
                                            settings.MAX_PASSAGE_CHARS)]
        unit_anchor = make_anchor(slug, *text.tail.split("/"))
        reference = f"{council}, {text.label}"
        for k, (part, (anchor, held), part_notes) in enumerate(zip(
                parts, name_pieces(unit_anchor, raw, parts, segments),
                notes_per_piece(raw, parts, notes)), 1):
            content = clean_text(part)
            refs = footnotes(part, content, part_notes)
            out.append(Passage(content=content,
                               reference=piece_reference(reference, None, None, k, len(parts)),
                               anchor=anchor, chapter_key=make_anchor(slug, text.chapter),
                               chapter_label=text.chapter_label, position=len(out),
                               unit_label=text.label,
                               metadata={**meta, "footnotes": refs} if refs else meta,
                               source_units=held))
    return out


def read_divs(path: str) -> dict:
    """The allowlisted divs of `npnf214.xml`, by id."""
    wanted = {t.div for texts in COUNCILS.values() for t in texts if t.div}
    root = ET.parse(path).getroot()
    found = {e.get("id"): e for e in root.iter() if e.get("id") in wanted}
    missing = wanted - set(found)
    if missing:
        raise ValueError(f"{path}: no div {sorted(missing)}")
    return found


def build_percival(entry: dict, document_id: str, source_key: str, divs: dict) -> Document:
    council = entry["council"]
    works = [t.ocr for t in COUNCILS[council] if t.ocr]
    translation = "; ".join([TRANSLATION, *(OCR_TRANSLATIONS[w] for w in works)])
    return Document(id=document_id, collection="councils", title=council, author=None,
                    year=entry["year"], translation=translation,
                    metadata={"url": URL, "held_text_url": entry["url"],
                              "council_number": entry.get("council_number"),
                              "source_key": source_key, "source_file": SOURCE_FILE,
                              "anchor_scheme": ANCHOR_SCHEME},
                    passages=_passages(council, entry["year"], divs))
