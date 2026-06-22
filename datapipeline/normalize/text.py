"""Pure text-normalization cleaners (whitespace, punctuation, ellipsis)."""
from __future__ import annotations

import re

_SPACES = re.compile(r"[ \t ]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
# 3+ dots separated only by spaces, plus any leading whitespace so the ellipsis
# attaches cleanly to the preceding word.
_ELLIPSIS = re.compile(r"\s*\.(?:\s*\.){2,}")


def collapse_whitespace(text: str) -> str:
    # Collapse horizontal whitespace; preserve newlines (paragraph structure).
    lines = [_SPACES.sub(" ", ln).strip() for ln in text.split("\n")]
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def tighten_punctuation(text: str) -> str:
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def normalize_ellipses(text: str) -> str:
    def repl(m: re.Match) -> str:
        dots = m.group(0).count(".")
        # Long runs (≥6 dots) are table/diagram artifacts → drop to a space.
        # Genuine omission marks (3–5 dots) → " …" attached to the prior word.
        return " " if dots >= 6 else " …"
    return _ELLIPSIS.sub(repl, text)


def clean_text(text: str) -> str:
    """Universal cleaner applied to every passage's content."""
    text = normalize_ellipses(text)
    text = collapse_whitespace(text)
    text = tighten_punctuation(text)
    return text.strip()
