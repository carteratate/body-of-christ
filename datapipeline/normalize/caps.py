"""Title-case ALL-CAPS shouting in headings/titles/references."""
from __future__ import annotations

import re

_KEEP = {"CCC", "OT", "NT", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
_LOWER = {"of", "the", "and", "in", "to", "for", "on", "a", "an", "or", "with", "by", "from"}
# A run of 3+ consecutive all-caps words (each ≥2 letters), e.g. "THE FORMATION OF CLERICS".
_CAPS_RUN = re.compile(r"\b(?:[A-Z][A-Z'’]+)(?:\s+[A-Z][A-Z'’]+){2,}\b")


def _title_word(word: str, first: bool) -> str:
    if word in _KEEP:
        return word
    low = word.lower()
    if not first and low in _LOWER:
        return low
    return low.capitalize()


def title_case_shouting(text: str) -> str:
    def repl(m: re.Match) -> str:
        words = m.group(0).split()
        return " ".join(_title_word(w, i == 0) for i, w in enumerate(words))
    return _CAPS_RUN.sub(repl, text)


def smart_title_case(text: str) -> str:
    """Title-case a label whose letters are ALL uppercase (a shouting proper
    name/title like "POLYCARP" or "CLEMENT OF ROME"); otherwise fix only
    embedded all-caps runs via title_case_shouting."""
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        words = text.split()
        return " ".join(_title_word(w, i == 0) for i, w in enumerate(words))
    return title_case_shouting(text)
