"""Pure text-normalization cleaners (whitespace, punctuation, ellipsis, joined
sentences, ligatures and reviewed line-end broken words)."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_SPACES = re.compile(r"[ \t ]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
# 3+ dots separated only by spaces, plus any leading whitespace so the ellipsis
# attaches cleanly to the preceding word.
_ELLIPSIS = re.compile(r"\s*\.(?:\s*\.){2,}")
# A sentence run into the next one ("consecration.The Synod", "said.”The"): a lowercase
# letter, end punctuation, an optional closing quote or bracket, then a capitalized word.
# The lowercase letter keeps initials and abbreviations ("U.S.Bishops") out.
_SENTENCE_JOIN = re.compile(r"([a-z][.?!;:][”\"’)]?)(?=[A-Z][a-z])")
# A section sign run onto the end of the previous sentence ("parentibus.§2").
_SECTION_JOIN = re.compile(r"([.;:])(?=§)")
# Whitespace-delimited tokens that are addresses, where a dot before a capital is not a join.
_ADDRESS = re.compile(r"://|www\.|@")
_LIGATURES = str.maketrans({"æ": "ae", "œ": "oe", "Æ": "Ae", "Œ": "Oe"})
BROKEN_WORDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "broken_words.json")


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


def repair_sentence_joins(text: str) -> str:
    """Put back the space the source lost between two sentences, or before a section sign.
    Only adds whitespace, and leaves tokens holding a URL or an email address alone."""
    def token(m: re.Match) -> str:
        tok = m.group(0)
        if _ADDRESS.search(tok):
            return tok
        return _SECTION_JOIN.sub(r"\1 ", _SENTENCE_JOIN.sub(r"\1 ", tok))
    return re.sub(r"\S+", token, text)


def fold_ligatures(text: str) -> str:
    """æ, œ, Æ and Œ spelled out as ae, oe, Ae and Oe, which keyword search can match."""
    return text.translate(_LIGATURES)


@lru_cache(maxsize=1)
def broken_words() -> tuple[dict[str, str], re.Pattern | None]:
    """The reviewed list in `broken_words.json`: each broken form → its correction, and
    one pattern matching any broken form as a whole word."""
    with open(BROKEN_WORDS_PATH, encoding="utf-8") as f:
        fixes = {e["broken"]: e["corrected"] for e in json.load(f)}
    if not fixes:
        return fixes, None
    forms = sorted(fixes, key=len, reverse=True)
    pattern = re.compile(r"(?<![A-Za-z])(?:" + "|".join(map(re.escape, forms)) + r")(?![A-Za-z])")
    return fixes, pattern


def rejoin_broken_words(text: str) -> str:
    """Mend words the source broke at a line end ("pre- cisely", "anti- religious") from
    the reviewed list only. No pattern rule: a hyphen and a space before a lowercase word
    is as often a lost dash ("action- it") as a broken word."""
    fixes, pattern = broken_words()
    if pattern is None:
        return text
    return pattern.sub(lambda m: fixes[m.group(0)], text)


def clean_text(text: str) -> str:
    """Universal cleaner applied to every passage's content. Sentence joins are repaired
    after punctuation is tightened, which makes some ("life .Nor" becomes "life.Nor")."""
    text = normalize_ellipses(text)
    text = collapse_whitespace(text)
    text = tighten_punctuation(text)
    text = repair_sentence_joins(text)
    text = fold_ligatures(text)
    text = rejoin_broken_words(text)
    return text.strip()
