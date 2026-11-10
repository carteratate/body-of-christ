"""Passage links into vatican.va (corpus-cleanup item 2.4e, issue #292).

An excerpt-only passage links to its document's page at the source. vatican.va pages are
long and their paragraph anchors are not dependable, so a passage's link carries a text
fragment (`#:~:text=`) of its opening words, and a browser that supports fragments
scrolls to the passage and highlights it. One that does not opens the page at the top,
as before.

The fragment is about eight words, cut before anything the page may render differently
from the stored text (a footnote marker, a bracket). datapipeline/checks/source_links.py
looks for every fragment in the vendored page and writes the passages it cannot find to
source_link_misses.json; those keep the plain URL. The check loads this file by path, so
it must import nothing beyond the standard library.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlparse

_MISSES = Path(__file__).with_name("source_link_misses.json")

FRAGMENT_WORDS = 8
# Fewer words than this match too much of a page to say where the passage is.
MIN_FRAGMENT_WORDS = 3

# A passage that begins with its own paragraph number ("22. ", "(22) ", "§ 22 ").
_LEADING_NUMBER = re.compile(r"^(?:§\s*)?[\(\[]?\d{1,4}[a-z]?[\)\]]?[.:]?\s+")
# Where the page may not render the stored text: brackets, which hold editorial insertions
# and note numbers, note signs, and digits fixed to a word or its punctuation ("norms.12"),
# which are footnote markers.
_STOP = re.compile(r"[\[\]\(\)\{\}<>*†‡]|(?<=[^\s\d])\d")
_WORD_THEN_PUNCT = re.compile(r"[^\W\d_][.,;:!?\"'”’]+$")
# A quotation mark standing alone: the stored text spaced it from its words ("“ recover"),
# the page may not.
_LONE_QUOTE = re.compile(r"[\"'“”‘’«»]+")
# A note number standing alone after a word's punctuation ('"is love," 36 the').
_LONE_NUMBER = re.compile(r"\d{1,4}[.,;:]?")
# How many times a fragment may start again after a stop that left too few words before
# it, as when a passage opens on the tail of a citation ("Jas. 1:17). As the Council").
_RESTARTS = 3


def is_vatican(url: str | None) -> bool:
    host = urlparse(url).hostname if url else None
    return bool(host) and (host == "vatican.va" or host.endswith(".vatican.va"))


def _words_to_stop(tokens: list[str]) -> tuple[list[str], int]:
    """The words before the first stop, and the index of the token after it (len(tokens)
    when nothing stops them)."""
    words: list[str] = []
    for i, token in enumerate(tokens):
        if len(words) == FRAGMENT_WORDS:
            return words, i
        if _LONE_QUOTE.fullmatch(token):
            if words:
                return words, i + 1
            continue   # an opening mark before the first word: the match starts after it
        if (words and _LONE_NUMBER.fullmatch(token)
                and not words[-1][-1].isalnum()):
            return words, i + 1
        stop = _STOP.search(token)
        if stop is None:
            words.append(token)
            continue
        head = token[:stop.start()]
        # A note number fixed to a word's punctuation ("norms.12") leaves the word; one
        # inside a token ("8:28", "A1") takes the whole token, a part of which may not
        # end a word on the page.
        if head and (not stop.group().isdigit() or _WORD_THEN_PUNCT.search(head)):
            words.append(head)
        return words, i + 1
    return words, len(tokens)


def fragment_text(content: str | None) -> str | None:
    """The opening words of a passage for its text fragment, or None when too few of
    them can be relied on.

    A fragment matches within one block of the page, so it is taken from one line of the
    passage: the first of at least FRAGMENT_WORDS words, which passes over a heading the
    passage opens with, else the first line."""
    lines = [" ".join(line.split()) for line in (content or "").splitlines()]
    lines = [line for line in lines if line]
    text = next((line for line in lines if len(line.split()) >= FRAGMENT_WORDS),
                lines[0] if lines else "")
    tokens = _LEADING_NUMBER.sub("", text, count=1).split()
    for _ in range(_RESTARTS + 1):
        words, after = _words_to_stop(tokens)
        # A fragment matches whole words, so it must not end on a hyphen or dash the
        # page may break differently; other trailing punctuation stays.
        while words and words[-1].rstrip("-–—") != words[-1]:
            words[-1] = words[-1].rstrip("-–—")
            if not words[-1]:
                words.pop()
        if len(words) >= MIN_FRAGMENT_WORDS:
            return " ".join(words)
        tokens = tokens[after:]
        if not tokens:
            break
    return None


def with_fragment(url: str, text: str) -> str:
    """`url` with a text fragment for `text`. `-`, `,` and `&` are syntax inside the
    directive, so they are encoded with everything else that is not unreserved."""
    directive = ":~:text=" + quote(text, safe="").replace("-", "%2D")
    return url + directive if "#" in url else url + "#" + directive


@lru_cache(maxsize=1)
def _misses() -> frozenset[str]:
    try:
        return frozenset(json.loads(_MISSES.read_text())["chunk_ids"])
    except FileNotFoundError:
        return frozenset()


def passage_url(url: str, chunk_id, content: str | None) -> str:
    """A vatican.va document URL with the passage's text fragment, or the URL unchanged
    when it is on another host, the passage is a known miss, or its opening words give
    no fragment."""
    if not is_vatican(url) or (chunk_id is not None and str(chunk_id) in _misses()):
        return url
    text = fragment_text(content)
    return with_fragment(url, text) if text else url
