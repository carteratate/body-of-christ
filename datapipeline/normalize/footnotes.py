"""Strip inline footnote/endnote anchor markers like [1], [18]."""
from __future__ import annotations

import re

# A bracketed integer immediately following a word/punctuation = an endnote anchor.
_MARKER = re.compile(r"(?<=\S)\s*\[\d+\]")


def strip_footnote_markers(text: str) -> str:
    return _MARKER.sub("", text)
