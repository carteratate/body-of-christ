"""Strip inline footnote/endnote anchor markers like [1], [18], and the callers of the
papal sources (C-17): numeric `<sup>`, number-only links to a note, "[ 3 ]", "(35)" after a
word or closing quote, and digits glued after punctuation."""
from __future__ import annotations

import re

# A bracketed integer immediately following a word/punctuation = an endnote anchor.
_MARKER = re.compile(r"(?<=\S)\s*\[\d+\]")


def strip_footnote_markers(text: str) -> str:
    return _MARKER.sub("", text)


_SUP_CALLER = re.compile(r"^\W*\d{1,3}\*?\W*$")
_LINK_CALLER = re.compile(r"^\W*\d{1,3}\W*$")
_BRACKET_CALLER = re.compile(r"(?<=\S)\s*\[\s*\d{1,3}\s*\]")
_PAREN_CALLER = re.compile(r"(?<=[A-Za-z\"”’.,;:!?)])\s?\(\d{1,3}\)")
_GLUED_CALLER = re.compile(r"(?<=[a-z\"”’)][.,;:])\d{1,3}(?=\s|$|[A-Z“\"])"
                           r"(?!\s+(?:Cor|Jn|John|Pt|Pet|Peter|Tim|Tm|Thes|Th|Sam|Sm|Kgs|Kg|Kings"
                           r"|Chr|Mac|Macc|Mc|Esd)\b)")
_BARE_CALLER = re.compile(r"(?<=[.!?\"”’)…])\s\d{1,3}(?=\s+[A-Z“\"‘]|\s*$)", re.MULTILINE)
# "sess. 24 On Reformation": a number in a citation, not a caller.
_CITATION_WORD = re.compile(r"\b(?:cf|bk|sess|ch|cap|tit|vol|no|nos|art|can|lib|p|pp|n|dist)\.$",
                            re.IGNORECASE)
# "1 Jn": a number that belongs to the book after it. Removing it names another book.
_NUMBERED_BOOK = re.compile(r"\s+(?:Cor|Jn|John|Pt|Pet|Peter|Tim|Tm|Thes|Th|Sam|Sm|Kgs|Kg|Kings|Chr"
                            r"|Mac|Macc|Mc|Esd)\b")
# What a dropped caller leaves when the source wrapped it: "( )", "[ ]".
_EMPTY_MARKER = re.compile(r"\s*[\[(]\s*[\])]")


def drop_caller_elements(el) -> None:
    """Remove from a BeautifulSoup element the callers its markup shows: a numeric
    `<sup>`, and an in-page link whose text is only a number."""
    for sup in el.find_all("sup"):
        if _SUP_CALLER.match(sup.get_text(strip=True)):
            sup.decompose()
    for a in el.find_all("a"):
        if (a.get("href") or "").startswith("#") \
                and _LINK_CALLER.match(a.get_text(strip=True) or "x"):
            a.decompose()


def strip_note_callers(text: str) -> str:
    """Remove the callers that are plain text."""
    text = _GLUED_CALLER.sub("", _PAREN_CALLER.sub("", _BRACKET_CALLER.sub("", text)))
    return _EMPTY_MARKER.sub("", text)


def strip_bare_callers(text: str) -> str:
    """Remove numbers standing alone after a sentence, for sources that print their
    callers so. A caller never follows a citation's abbreviation or opens a numbered book."""
    def keep_citation(m: re.Match) -> str:
        citation = _CITATION_WORD.search(text, max(0, m.start() - 8), m.start())
        return m.group(0) if citation or _NUMBERED_BOOK.match(text, m.end()) else ""
    return _BARE_CALLER.sub(keep_citation, text)
