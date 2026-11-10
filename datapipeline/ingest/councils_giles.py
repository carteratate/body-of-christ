"""Council texts Schroeder does not print, from J. A. Giles's translation of Matthew
Paris's English History, vol. 2 (London: Bohn, 1853) (1.2e, Carter, 9 Nov 2026).

Matthew Paris copied into his chronicle the bull deposing Frederick II (gap G4) and Lyons
I's constitution on legates (Tanner's I 7, gap G12). The text comes through the OCR tool,
frozen in `ocr/texts/<work>.json`. Each text is its own chapter of the council's
document, under Giles's printed heading, and is built in the council's Schroeder
document: the bull before the canons, as Tanner places it, and I 7 after them.
"""
from __future__ import annotations

import re

from config import settings
from identity import anchor as make_anchor, slugify
from ingest.pieces import Segment, name_pieces, pack_text, piece_reference
from model import Passage
from normalize.text import clean_text
from ocr.fixes import read_text

SCAN_URL = "https://archive.org/details/matthewparisseng02pari"
TRANSLATION = "J. A. Giles (1853)"

# By the manifest's council name: the work, and its texts in the order they are placed.
# A text is (OCR unit name, anchor under the council, Giles's heading, before the canons).
WORKS = {
    "First Council of Lyons": ("giles-matthew-paris-lyons-1", (
        ("deposition", "deposition",
         "How the pope excommunicated the emperor Frederick at the council of Lyons", True),
        ("duty-of-the-legate", "duty-of-the-legate", "Of the duty of the legate", False),
    )),
}

_PART = re.compile(r"^(.+?)(?:-\d{2})?$")
# The shared splitter reads "St." as a sentence end and can cut "St. / Peter".
_LAST_WORD_ABBREVIATION = re.compile(r"\b(?:St|SS?)\.\s*$")


def _abbreviations_kept(pieces: list[str]) -> list[str]:
    """`pieces` (stripped, a space between them) with a closing "St." moved to the start
    of the next piece, so a name is never cut."""
    pieces = list(pieces)
    for k in range(len(pieces) - 1):
        m = _LAST_WORD_ABBREVIATION.search(pieces[k])
        if m:
            pieces[k], pieces[k + 1] = (pieces[k][:m.start()].rstrip(),
                                        f"{m.group(0).strip()} {pieces[k + 1]}")
    return pieces


def _texts(frozen: dict) -> dict[str, tuple[str, list[str]]]:
    """Each OCR unit's whole text and pages, its passages joined back: a passage that
    `continues` was cut from its paragraph only for correction and the check."""
    out: dict[str, tuple[str, list[str]]] = {}
    for unit in frozen["passages"]:
        name = _PART.match(unit["id"]).group(1)
        text, pages = out.get(name, ("", []))
        sep = "" if not text else " " if unit.get("continues") else "\n\n"
        out[name] = (text + sep + unit["text"], pages + [p for p in unit["pages"] if p])
    return out


def passages(council: str, year: int) -> tuple[list[Passage], list[Passage]]:
    """The council's Giles passages placed before its canons, and those after them.
    Positions are the caller's to set."""
    if council not in WORKS:
        return [], []
    work, placed = WORKS[council]
    frozen = read_text(work)
    texts = _texts(frozen)
    slug = slugify(council)
    before: list[Passage] = []
    after: list[Passage] = []
    for name, key, heading, first in placed:
        text, pages = texts[name]
        unit_anchor = chapter_key = make_anchor(slug, key)
        paragraphs = [clean_text(p) for p in text.split("\n\n") if p.strip()]
        body = "\n\n".join(paragraphs)
        segments = [Segment(f"p{k}", p) for k, p in enumerate(paragraphs, 1)]
        pieces = _abbreviations_kept(pack_text(body, segments, settings.MAX_PASSAGE_CHARS))
        meta = {"council": council, "year": year, "url": SCAN_URL,
                "pages": list(dict.fromkeys(pages)), **frozen["metadata"]}
        out = before if first else after
        for k, (piece, (anchor, held)) in enumerate(
                zip(pieces, name_pieces(unit_anchor, body, pieces, segments)), 1):
            out.append(Passage(content=piece,
                               reference=piece_reference(f"{council}, {heading}", None, None,
                                                         k, len(pieces)),
                               anchor=anchor, chapter_key=chapter_key, chapter_label=heading,
                               position=0, unit_label=None, metadata=meta,
                               source_units=held))
    return before, after
