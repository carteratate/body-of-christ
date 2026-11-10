"""Council texts from R. J. Deferrari's translation of Denzinger, *The Sources of Catholic
Dogma* (St. Louis: B. Herder, 1957), decree text only (R9; Carter, 4 and 9 Nov 2026).

Deferrari's texts go into their council's document, built with Schroeder's
(`councils_schroeder`). The text comes through the OCR tool from the text layer of the
Loreto reprint's PDF (`ocr/pdf.py`), frozen in `ocr/texts/<work>.json`. Denzinger's
headings, notes and numbers never reach it.

Each text either replaces Schroeder's text of the same unit (Constantinople IV's canons
1, 3, 11, 12 and 21, which Schroeder only summarises) or follows a named one (the extract
of canon 17 after Schroeder's summary of it; Pastor aeternus gregem in session 11).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ocr.fixes import read_text

SCAN_URL = "https://archive.org/details/sourcesofcatholi00denz"
TRANSLATION = "R. J. Deferrari (1957)"
TEXT_REPLACED = "Deferrari (1957) replaces Tanner"


@dataclass(frozen=True)
class Placed:
    unit: str                  # the OCR unit id
    anchor: str                # its anchor under the council
    label: str                 # its unit label
    replaces: str | None = None  # the Schroeder text (anchor under the council) it replaces
    after: str | None = None     # or the one it follows


# By the manifest's council name: the work and its texts.
WORKS: dict[str, tuple[str, tuple[Placed, ...]]] = {
    "Fourth Council of Constantinople": ("deferrari-constantinople-4", (
        Placed("canon/1", "canons/1", "Canon 1", replaces="canons/1"),
        Placed("canon/3", "canons/3", "Canon 3", replaces="canons/3"),
        Placed("canon/11", "canons/11", "Canon 11", replaces="canons/11"),
        Placed("canon/12", "canons/12", "Canon 12", replaces="canons/12"),
        Placed("canon/17/extract", "canons/17/extract", "Canon 17 (extract)", after="canons/17"),
        Placed("canon/21", "canons/21", "Canon 21", replaces="canons/21"),
    )),
    "Fifth Lateran Council": ("deferrari-lateran-5", (
        Placed("session-11/pastor-aeternus-gregem", "session-11/pastor-aeternus-gregem",
               "Pastor aeternus gregem",
               after="session-11/supernae-majestatis-praesidio"),
    )),
}

_PART = re.compile(r"^(.+?)(?:-\d{2})?$")


def texts(council: str) -> tuple[dict, list[tuple[Placed, str, list[str]]]]:
    """The work's metadata and, per placed text, its whole text (its passages for
    correction and the check joined back) and pages."""
    if council not in WORKS:
        return {}, []
    work, placed = WORKS[council]
    frozen = read_text(work)
    joined: dict[str, tuple[str, list[str]]] = {}
    for unit in frozen["passages"]:
        name = _PART.match(unit["id"]).group(1)
        text, pages = joined.get(name, ("", []))
        sep = "" if not text else " " if unit.get("continues") else "\n\n"
        joined[name] = (text + sep + unit["text"], pages + [p for p in unit["pages"] if p])
    missing = {p.unit for p in placed} ^ set(joined)
    if missing:
        raise ValueError(f"{work}: units and placed texts differ: {sorted(missing)}")
    return frozen["metadata"], [(p, *joined[p.unit]) for p in placed]
