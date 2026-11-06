"""Councils from Schroeder's Disciplinary Decrees of the General Councils (1937) (1.2e).

The text comes through the OCR tool (1.2f), one unit per canon, frozen in
`ocr/texts/<work>.json`. Schroeder's history, summaries, commentary and notes never reach
it. A canon's anchor is `<council>/canon/<Schroeder's number>`; the passage registry keeps
each one on the ID its Tanner canon had, whatever number Tanner gave it.
"""
from __future__ import annotations

from config import settings
from identity import anchor as make_anchor, slugify
from ingest.pieces import Segment, name_pieces, pack_text, piece_reference
from model import Document, Passage
from normalize.text import clean_text
from ocr.fixes import read_text
from registry import ANCHOR_SCHEME

SCAN_URL = "https://archive.org/details/DisciplinaryCouncils"
SOURCE_DIR = "DisciplinaryCouncils/"    # under sources/councils/
TRANSLATION = "H. J. Schroeder (1937)"
TEXT_REPLACED = "Schroeder (1937) replaces Tanner"

# Councils built from Schroeder, by the manifest's council name.
WORKS = {
    "First Lateran Council": "schroeder-lateran-1",
    "Second Lateran Council": "schroeder-lateran-2",
    "Fourth Lateran Council": "schroeder-lateran-4",
}
# D9's fallback: a council that has not passed the OCR gate when the P4 build is cut goes
# here and its adapter emits no passages. Its document ID stays frozen, and 4.1b's removal
# entries explain its Tanner passages.
HELD: frozenset[str] = frozenset()


def _canon_number(unit_id: str) -> str:
    return unit_id.removeprefix("canon-")


def _passages(council: str, year: int, text: dict) -> list[Passage]:
    slug = slugify(council)
    chapter_key = make_anchor(slug, "canons")
    out: list[Passage] = []
    for unit in text["passages"]:
        number = _canon_number(unit["id"])
        paragraphs = [clean_text(p) for p in unit["text"].split("\n\n") if p.strip()]
        body = "\n\n".join(paragraphs)
        segments = [Segment(f"p{k}", p) for k, p in enumerate(paragraphs, 1)]
        pieces = pack_text(body, segments, settings.MAX_PASSAGE_CHARS)
        meta = {"council": council, "year": year, "url": SCAN_URL,
                "pages": [p for p in dict.fromkeys(unit["pages"]) if p],
                "text_replaced": TEXT_REPLACED, **text["metadata"]}
        base = f"{council}, Canon {number}"
        unit_anchor = make_anchor(slug, "canon", number)
        for k, (piece, (anchor, held)) in enumerate(
                zip(pieces, name_pieces(unit_anchor, body, pieces, segments)), 1):
            out.append(Passage(content=piece,
                               reference=piece_reference(base, None, None, k, len(pieces)),
                               anchor=anchor, chapter_key=chapter_key, chapter_label="Canons",
                               position=len(out), unit_label=f"Canon {number}", metadata=meta,
                               source_units=held))
    return out


def build_schroeder(entry: dict, document_id: str, source_key: str,
                    held: frozenset[str] = HELD) -> Document:
    council = entry["council"]
    work = WORKS[council]
    passages = [] if council in held else _passages(council, entry["year"], read_text(work))
    return Document(id=document_id, collection="councils", title=council, author=None,
                    year=entry["year"], translation=TRANSLATION,
                    metadata={"url": SCAN_URL, "held_text_url": entry["url"],
                              "council_number": entry.get("council_number"),
                              "source_key": source_key, "source_file": SOURCE_DIR,
                              "anchor_scheme": ANCHOR_SCHEME},
                    passages=passages)
