"""Title-case ALL-CAPS shouting in headings/titles/references."""
from __future__ import annotations

import re

_KEEP = {"CCC", "OT", "NT", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
_LOWER = {"of", "the", "and", "in", "to", "for", "on", "a", "an", "or", "with", "by", "from",
          "into", "at", "as"}
# A run of 3+ consecutive all-caps words (each ≥2 letters), e.g. "THE FORMATION OF CLERICS".
_CAPS_RUN = re.compile(r"\b(?:[A-Z][A-Z'’]+)(?:\s+[A-Z][A-Z'’]+){2,}\b")


def _title_word(word: str, first: bool) -> str:
    """One word in title case. Leading punctuation is kept and the first letter after it
    is capitalized ('"HE' becomes '"He'); a word opening a quotation counts as first."""
    lead = len(word) - len(word.lstrip("\"'“‘(["))
    head, body = word[:lead], word[lead:]
    if body.rstrip(",.:;!?\"'”’)]") in _KEEP:
        return word
    low = body.lower()
    if not first and not head and low.rstrip(",.:;") in _LOWER:
        return low
    return head + low[:1].upper() + low[1:]


def _opens_phrase(previous: str) -> bool:
    """A word after a colon, a full stop or a dash starts a phrase ("Man: The Image")."""
    return previous.endswith((":", ".", "-", "–", "—"))


def title_case_shouting(text: str) -> str:
    def repl(m: re.Match) -> str:
        words = m.group(0).split()
        return " ".join(_title_word(w, i == 0 or _opens_phrase(words[i - 1]))
                        for i, w in enumerate(words))
    return _CAPS_RUN.sub(repl, text)


def smart_title_case(text: str) -> str:
    """Title-case a label whose letters are ALL uppercase (a shouting proper
    name/title like "POLYCARP" or "CLEMENT OF ROME"); otherwise fix only
    embedded all-caps runs via title_case_shouting."""
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        words = text.split()
        return " ".join(_title_word(w, i == 0 or _opens_phrase(words[i - 1]))
                        for i, w in enumerate(words))
    return title_case_shouting(text)
