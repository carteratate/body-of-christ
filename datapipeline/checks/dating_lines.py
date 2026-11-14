"""Papal dating lines against the registry's years (corpus-cleanup 2.3, C-05).

A papal document's page usually ends with its dating line ("Given at Rome, at St.
Peter's, 27 April, 1859, …"). Each document's year in the work registry must be the year
that line prints, unless the line is a reviewed misprint (`MISPRINTS`). Read from the
vendored page each manifest names (vatican.va or papalencyclicals.net), held documents
included; a held document keeps its manifest year, as the registry holds no facts for it.
"""
from __future__ import annotations

import json
import os
import re

from bs4 import BeautifulSoup

from checks.source_text import SOURCES

COLLECTIONS = ("encyclicals", "apostolic-exhortations", "papal-documents")
# "Given at Rome …" or "Given in Rome …", up to the first year on the same line.
_GIVEN = re.compile(r"\bGiven\b,?\s+(?:at|in|from)\s+(?:the\s+)?[A-Z][^\n]{0,240}?"
                    r"\b(1[2-9]\d\d|20[0-2]\d)\b")
# Source key → (the year the source prints, why it is wrong).
MISPRINTS = {
    "encyclicals/salutis-nostrae": (
        1744, "the page prints 1744 for 1774: Clement XIV, who issued it, was elected in "
              "1769, and the bull proclaims the Jubilee of 1775"),
}


def printed_year(path: str) -> int | None:
    """The year of the last dating line in a vendored page, or None if it prints none."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = BeautifulSoup(f.read(), "html.parser").get_text("\n")
    matches = list(_GIVEN.finditer(re.sub(r"[ \t\xa0]+", " ", text)))
    return int(matches[-1].group(1)) if matches else None


def mismatches(years: dict[str, int | None], sources: str = SOURCES
               ) -> tuple[int, list[tuple[str, int | None, int]]]:
    """How many pages print a dating line, and each (source key, year, printed year)
    where the year differs and no misprint explains it. `years` maps a source key to the
    registry's year; a key it lacks takes the manifest's."""
    dated, out = 0, []
    for collection in COLLECTIONS:
        with open(os.path.join(sources, collection, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        for entry in manifest:
            key = f"{collection}/{entry['slug']}"
            printed = printed_year(os.path.join(sources, collection, entry["file"]))
            if printed is None:
                continue
            dated += 1
            year = years.get(key, entry.get("year"))
            if printed != year and MISPRINTS.get(key, (None,))[0] != printed:
                out.append((key, year, printed))
    return dated, out
