"""Councils from Schroeder's Disciplinary Decrees of the General Councils (1937) (1.2e).

The text comes through the OCR tool (1.2f), one unit per canon or decree, frozen in
`ocr/texts/<work>.json`. Schroeder's history, summaries, commentary and notes never reach
it. A canon's anchor is `<council>/canon/<Schroeder's number>`; the passage registry keeps
each one on the ID its Tanner canon had, whatever number Tanner gave it. A council rebuilt
by session (Lateran V) names each text `<council>/session-N/<Latin title>`, each session
a chapter (Carter, 9 Nov 2026). Deferrari's texts join their council's document
(`councils_deferrari`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import settings
from ingest import councils_deferrari as deferrari
from ingest import councils_giles as giles
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
    "Third Lateran Council": "schroeder-lateran-3",
    "Fourth Lateran Council": "schroeder-lateran-4",
    "First Council of Lyons": "schroeder-lyons-1",
    "Second Council of Lyons": "schroeder-lyons-2",
    "Council of Vienne": "schroeder-vienne",
    "Fourth Council of Constantinople": "schroeder-constantinople-4",
    "Fifth Lateran Council": "schroeder-lateran-5",
}
# A council printed in two series names both: `<council>/series-K/canon/N`, each series
# its own chapter (Carter, 9 Nov 2026). One series is `<council>/canon/N`.
SERIES_LABELS = {1: "Canons, first series", 2: "Canons, second series"}
# Where a council's canons cannot be `<council>/canon/N`: Constantinople IV's live
# `canon/1` is Tanner's credit line, which retires, and a retired anchor never names
# another text (Carter, 9 Nov 2026).
CANON_PATHS = {"Fourth Council of Constantinople": "canons"}
# D9's fallback: a council that has not passed the OCR gate when the P4 build is cut goes
# here and its adapter emits no passages. Its document ID stays frozen, and 4.1b's removal
# entries explain its Tanner passages.
HELD: frozenset[str] = frozenset()


_UNIT_ID = re.compile(r"^(?:series-(\d+)-)?canon-(\d+)$")
# A text of a council rebuilt by session: `session-N/<name>` (Lateran V's bulls), with
# `-NN` on each part of a text cut for correction and the check.
_SESSION_UNIT = re.compile(r"^(session-(\d+))/([a-z0-9/-]+?)(?:-(\d{2}))?$")


@dataclass
class _Text:
    """One unit of a council's document before it is packed into passages."""
    tail: str               # its anchor under the council
    chapter: str            # its chapter key under the council
    chapter_label: str
    unit_label: str
    reference: str
    body: str
    pages: list[str]
    meta: dict


def _unit(unit_id: str) -> tuple[int | None, str]:
    """(series or None, Schroeder's canon number) of an OCR unit id."""
    m = _UNIT_ID.match(unit_id)
    if not m:
        raise ValueError(f"not a Schroeder canon unit: {unit_id}")
    return (int(m.group(1)) if m.group(1) else None), m.group(2)


def _title(name: str) -> str:
    """A bull's label from its anchor name: "apostolici-regiminis" → "Apostolici regiminis"."""
    return name.replace("-", " ").capitalize()


def _schroeder_texts(council: str, text: dict) -> list[_Text]:
    out: list[_Text] = []
    meta = {"url": SCAN_URL, "text_replaced": TEXT_REPLACED, **text["metadata"]}
    for unit in text["passages"]:
        pages = [p for p in unit["pages"] if p]
        session = _SESSION_UNIT.match(unit["id"])
        if session:
            tail, number, name = f"{session.group(1)}/{session.group(3)}", session.group(2), session.group(3)
            if out and out[-1].tail == tail:
                out[-1].body += (" " if unit.get("continues") else "\n\n") + unit["text"]
                out[-1].pages += pages
                continue
            out.append(_Text(tail, session.group(1), f"Session {number}", _title(name),
                             f"{council}, Session {number}, {_title(name)}", unit["text"],
                             pages, meta))
            continue
        series, number = _unit(unit["id"])
        if series is None:
            path = CANON_PATHS.get(council, "canon")
            out.append(_Text(f"{path}/{number}", "canons", "Canons", f"Canon {number}",
                             f"{council}, Canon {number}", unit["text"], pages, meta))
        else:
            label = SERIES_LABELS[series]
            out.append(_Text(f"series-{series}/canon/{number}", f"series-{series}", label,
                             f"Canon {number}",
                             f"{council}, {label.split(', ')[1].capitalize()}, Canon {number}",
                             unit["text"], pages, meta))
    return out


def _with_deferrari(council: str, texts: list[_Text]) -> list[_Text]:
    """`texts` with Deferrari's in place: each replaces the Schroeder text of its unit or
    follows the one it names, in its chapter."""
    meta, placed = deferrari.texts(council)
    if not placed:
        return texts
    meta = {"url": deferrari.SCAN_URL, "text_replaced": deferrari.TEXT_REPLACED, **meta}
    out = list(texts)
    for spot, body, pages in placed:
        target = spot.replaces or spot.after
        k = next((k for k, t in enumerate(out) if t.tail == target), None)
        if k is None:
            raise ValueError(f"{council}: Deferrari's {spot.unit} names no text {target}")
        here = out[k]
        reference = f"{here.reference.rsplit(', ', 1)[0]}, {spot.label}"
        text = _Text(spot.anchor, here.chapter, here.chapter_label, spot.label, reference,
                     body, pages, meta)
        if spot.replaces:
            out[k] = text
        else:
            out.insert(k + 1, text)
    return out


def _passages(council: str, year: int, texts: list[_Text]) -> list[Passage]:
    slug = slugify(council)
    out: list[Passage] = []
    for text in texts:
        paragraphs = [clean_text(p) for p in text.body.split("\n\n") if p.strip()]
        body = "\n\n".join(paragraphs)
        segments = [Segment(f"p{k}", p) for k, p in enumerate(paragraphs, 1)]
        pieces = pack_text(body, segments, settings.MAX_PASSAGE_CHARS)
        meta = {"council": council, "year": year, "pages": list(dict.fromkeys(text.pages)),
                **text.meta}
        unit_anchor = make_anchor(slug, *text.tail.split("/"))
        for k, (piece, (anchor, held)) in enumerate(
                zip(pieces, name_pieces(unit_anchor, body, pieces, segments)), 1):
            out.append(Passage(content=piece,
                               reference=piece_reference(text.reference, None, None, k, len(pieces)),
                               anchor=anchor, chapter_key=make_anchor(slug, text.chapter),
                               chapter_label=text.chapter_label, position=len(out),
                               unit_label=text.unit_label, metadata=meta, source_units=held))
    return out


def build_schroeder(entry: dict, document_id: str, source_key: str,
                    held: frozenset[str] = HELD) -> Document:
    council = entry["council"]
    work = WORKS[council]
    passages: list[Passage] = []
    translation = TRANSLATION
    if council not in held:
        # Texts Schroeder does not print come from Giles's Matthew Paris (councils_giles).
        before, after = giles.passages(council, entry["year"])
        texts = _with_deferrari(council, _schroeder_texts(council, read_text(work)))
        passages = before + _passages(council, entry["year"], texts) + after
        for k, passage in enumerate(passages):
            passage.position = k
        if before or after:
            translation = f"{TRANSLATION}; {giles.TRANSLATION}"
        if council in deferrari.WORKS:
            translation = f"{TRANSLATION}; {deferrari.TRANSLATION}"
    return Document(id=document_id, collection="councils", title=council, author=None,
                    year=entry["year"], translation=translation,
                    metadata={"url": SCAN_URL, "held_text_url": entry["url"],
                              "council_number": entry.get("council_number"),
                              "source_key": source_key, "source_file": SOURCE_DIR,
                              "anchor_scheme": ANCHOR_SCHEME},
                    passages=passages)
