"""Words: the fixed English word list, and the unrecognized-word rate the gate measures.

The list is `data/en_words.txt` (ESDB/SCOWL size 70, US, GB and CA spellings). A word is
recognized when it, lowercased and with diacritics and a possessive "'s" stripped, is in
the list or in the work's own list of proper names and other terms.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

WORD_LIST_PATH = Path(__file__).resolve().parent / "data" / "en_words.txt"

# Runs of letters, with internal apostrophes ("don't"); hyphens split words, so
# "prince-bishops" is two. Digits are not words.
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


@lru_cache(maxsize=1)
def english_words() -> frozenset[str]:
    with open(WORD_LIST_PATH, encoding="utf-8") as f:
        return frozenset(ln.strip() for ln in f if ln.strip() and not ln.startswith("#"))


def fold(word: str) -> str:
    """Lowercase, diacritics stripped, curly apostrophe made straight, possessive dropped."""
    w = unicodedata.normalize("NFKD", word.replace("’", "'"))
    w = w.encode("ascii", "ignore").decode().lower()
    return w[:-2] if w.endswith("'s") else w


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def is_known(word: str, extra: frozenset[str] = frozenset()) -> bool:
    w = fold(word)
    return w in english_words() or w in extra


def unrecognized_rate(texts: Iterable[str], extra: Iterable[str] = ()) -> tuple[float, int, int]:
    """(rate, unrecognized words, words) over `texts`; the rate is 0.0 with no words."""
    names = frozenset(fold(n) for n in extra)
    total = unknown = 0
    for text in texts:
        for w in words(text):
            total += 1
            if not is_known(w, names):
                unknown += 1
    return (unknown / total if total else 0.0), unknown, total
