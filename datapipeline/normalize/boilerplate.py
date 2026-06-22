"""Strip trailing site/footer boilerplate scraped from source web pages.

Some web-sourced documents (papalencyclicals.net, vatican.va) carry their
operator's footer text in the main content flow, so it lands in the last
passage — e.g. "Last updated ... © Copyright 2000-2026 Marketing Solutions by
Midstream Marketing" or "Copyright © Dicastery for Communication - Libreria
Editrice Vaticana". These are not part of the document; truncate at them.
"""
from __future__ import annotations

import re

# Earliest occurrence of any of these markers ends the real content.
_CUT = re.compile(
    r"(?is)\s*(?:"
    r"last updated\b"                       # papalencyclicals.net (Midstream) footer lead-in
    r"|©\s*copyright"
    r"|copyright\s*©"
    r"|copyright\s*[-–]\s*libreria"
    r")"
)

# A bare footnotes/endnotes section header left dangling at the very end.
_TRAILING_NOTES = re.compile(r"(?is)\n\s*(?:footnotes|endnotes)\.?\s*$")


def strip_boilerplate(text: str) -> str:
    m = _CUT.search(text)
    if m:
        text = text[: m.start()]
    text = _TRAILING_NOTES.sub("", text)
    return text.rstrip()
