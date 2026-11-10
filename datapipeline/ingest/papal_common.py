"""The papal parser (corpus-cleanup 1.3a): one tokenizer and one document builder for the
encyclicals, apostolic exhortations and papal documents collections.

One Document per manifest entry, from vendored HTML (papalencyclicals.net's
`div.entry-content`, vatican.va's `div.documento`). `tokens` walks `p`, `li`, `h2` to `h4`
and `hr` in document order, stops at the endnotes, and types what is left: the greeting
(preamble), prose before the first number (preface), numbered paragraphs, headings and
prayers. A heading opens the section after it, and the top tier of a document's headings
are its chapters. A source that numbers nothing cites by chapter (`piece_reference`), never
by a number the parser would have to invent.

Anchors are not renumbered to match: a unit keeps the anchor its live text has (D1), and
`papal_anchors.json` lists the units whose plain anchor named something else while live.

An adapter is `build_documents(<collection>, <source directory>)` and nothing else, so
its collection stays in `document_id` and no ID moves.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import NamedTuple

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from config import settings
from identity import anchor as make_anchor, unit_anchor
from ingest.pieces import (ORDINAL_ATTR, Segment, element_locator, name_pieces,
                           number_elements, pack_text, piece_reference, unique_unit_anchors)
from model import Document, Passage
from normalize.boilerplate import strip_boilerplate
from normalize.caps import smart_title_case
from normalize.footnotes import (drop_caller_elements, strip_bare_callers,
                                 strip_footnote_markers, strip_note_callers)
from normalize.text import clean_text, repair_sentence_joins
from registry import ANCHOR_SCHEME, resolve_document_id

log = logging.getLogger(__name__)

# "12. Text", "10 . Text", and "131.Later" where the source left out the space (not "1.5").
_NUM = re.compile(r"^(\d{1,4})\s*\.(?=\s|$|[^\d\s])\s*(.*)", re.DOTALL)
_UNDOTTED = re.compile(r"^(\d{1,3})\s+([A-Z“\"].*)", re.DOTALL)
_ROMAN = re.compile(r"^[IVX]+\.\s+\S")
# A short line closing on a Scripture reference: a heading quoting the verse.
_CITED_LINE = re.compile(r"\([^)]*\d+:\d+[^)]*\)$")
_BARE_NUMERAL = re.compile(r"^[IVX]+\.?$")
# A Roman numeral `smart_title_case` lowered with the point after it.
_ROMAN_WORD = re.compile(r"\b(?:Ii|Iii|Iv|Vi|Vii|Viii|Ix|Xi|Xii|Xiii)\b")
# A small letter opening the words after a numeral, a dash or a quotation mark.
_WORD_OPENING = re.compile(r"(?<=\s-\s)[a-z]|(?<=[“\"])[a-z]")
_NUMERAL_OPENING = re.compile(r"^(?:[IVX]+\.|\d+\.?|Part|Chapter) [a-z]")
_LABEL_CITATION = re.compile(r"^(.*?)(\s*\([^)]*\d[^)]*\).*)?$", re.DOTALL)
_BUCKET = 20
# A number counts as the next paragraph within this step, or further when the number
# after it follows on (a gap in the source's numbering, not a stray list item).
_MAX_STEP = 5
# papalencyclicals.net page chrome (nav/footer boilerplate that pollutes the stream and
# otherwise masquerades as bold section headers).
_CHROME = re.compile(
    r"automatically notified|more information about this site|fan of our facebook"
    r"|^search tips$|^sitemap$|return to (?:the )?home|^copyright\s*©|^©\s*copyright"
    r"|^last updated\b|^the holy see$", re.IGNORECASE)
_NOTES_HEADING = re.compile(r"^(?:END)?NOTES?$|^FOOTNOTES?$|^REFERENCES:?$", re.IGNORECASE)
# The same heading run on to the end of the last paragraph.
_TRAILING_NOTES_HEADING = re.compile(r"\s*REFERENCES:?\s*$")
# A list of the document's contents printed after its text.
_CONTENTS_HEADING = re.compile(r"^(?:INDEX|CONTENTS|TABLE OF CONTENTS)$", re.IGNORECASE)
_NOTE_TARGET = re.compile(r"^_(?:ftn|edn)\d+$")
_NOTE_ONE = re.compile(r"^\s*(?:[\[(]\s*1\s*[\])]|1\s*\.|1\s)")
# Tags that sit inside a line of text, tags that break one, and tags that hold blocks.
_INLINE = ("i", "em", "b", "strong", "span", "a", "u", "sup", "sub", "br")
_BLOCKS = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "blockquote", "table", "hr")
_CONTAINERS = ("div", "font", "blockquote", "td")
# How far after an <hr> the first note may sit.
_HR_REACH = 3
# Numbers that restart this low with entries this short are notes the source left unmarked.
_RESET_MAX = 3
_RESET_MEAN_CHARS = 150

# An unnumbered short line reads as a heading: no final punctuation, a capital first.
_HEADING_MAX = 90
_FINAL_PUNCTUATION = re.compile(r"[.!?:;,\"”’)\]…]$")
_NUMBERED_HEADING_MAX = 80
_BOLD_HEADING_MAX = 200
# As `structure.CHAPTER_SIZE_LIMIT`: no document should open with this much under one label.
_LONG_OPENING = 50_000
# Headings that name a division of the document. A document printing at least two has
# them as its chapters and every other heading opens a section inside one.
_MAJOR = re.compile(
    r"^(?:(?:CHAPTER|Chapter|PART|Part|SECTION|Section|INTRODUCTION|Introduction|CONCLUSION"
    r"|Conclusion|PREFACE|Preface|PROLOGUE|Prologue|PROEM|Proem|EPILOGUE|Epilogue)\b"
    r"|[IVXL]+\.?\s+\S|[IVXL]+$|[A-Z][a-z]+ (?:Part|Chapter)\b|(?:FIRST|SECOND|THIRD|FOURTH"
    r"|FIFTH|SIXTH) (?:PART|CHAPTER)\b)")
# A division marker with no title of its own: the next heading is its title.
_BARE_MAJOR = re.compile(
    r"^(?:(?:CHAPTER|Chapter|PART|Part|SECTION|Section)\s+\S+|[IVXL]+\.?|[A-Z][a-z]+ "
    r"(?:Part|Chapter)|(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH) (?:PART|CHAPTER))\.?:?$")
_DIVISION = re.compile(r"^(?:CHAPTER|Chapter|PART|Part)\b")
_INTRODUCTION = re.compile(r"(?:INTRODUCTION|Introduction|PREFACE|Preface|PROLOGUE|Prologue)\b")
_CONCLUSION = re.compile(r"(?:CONCLUSION|Conclusion)\b")
_PRAYER = re.compile(r"\bprayer\b", re.IGNORECASE)
# The greeting of a papal letter: its address, its salutation.
_GREETING = re.compile(
    r"^(?:To\b|Venerable\b|Beloved\b|Dearly\b|Dear\b|Greetings?\b|Health\b|Clement\b|Our Greetings"
    r"|Pius\b|Gregory\b|Leo\b|Benedict\b)|(?:Greetings?|Blessing|Benediction)[.!:]?$")
# A long paragraph is a greeting only as an address or when it ends in the salutation.
# An address names whom it is to ("To Our Venerable Brethren", "To all the Patriarchs"),
# which "To examine into the nature …" (Mirae Caritatis §1) does not.
_LONG_GREETING = re.compile(
    r"^To\s+(?:[A-Z]|all\b|the\b)|(?:Greetings?|Blessing|Benediction)[.!:]?$")
_SALUTATION = re.compile(r"(?:Greetings?|Blessing|Benediction)[.!:]?$")
_PREFACE_MIN = 100
_SENTENCE_END = re.compile(r"[.!?…;:,][\"”’)]*$")
# A "[N-M]" paragraph range, which only a table of contents prints.
_CONTENTS_RANGE = re.compile(r"\[\d+\s*[-–]\s*\d+\]")
_SENTENCE_STOP = re.compile(r"[.!?][\"”’]*$")
_IMPLICIT_MIN = 200
# Text under a heading shorter than this is an epigraph, whatever follows it.
_EPIGRAPH_MAX = 200
_DATING = re.compile(r"^(?:Given\b|Done\b|\[?Dated\b|From the Vatican\b|From Rome\b)")
# What marks a dating line as a date, in a line short enough to be one.
_DATED = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b|[Pp]ontificate")
_DATE_CARD_MAX = 300
# A citation's abbreviation: the number after it is no paragraph ("see vol. 2.").
_CITATION_END = re.compile(r"\b(?:cf|vol|no|nos|p|pp|n|ch|chap|bk|art|can|sess|sect|cap|tit)\.$",
                           re.IGNORECASE)
_SIGNED = re.compile(r"^.{0,30}\b(?:Pope|PP)\.?$")
_SHORT_PASSAGE = 20
# A signature line: a pope's name.
_SIGNATURE_MAX = 40

# Where a source runs on past the end of the document (C-06). The extracts the site
# appends after the Syllabus's last proposition are not the Syllabus.
_LAST_PARAGRAPH = {"syllabus-of-errors": 80}
# Where a list ends and the document's own prose follows it, unnumbered (C-01).
_LIST_END = {"exsurge-domine": 41}
# Site text inside a document (C-05), cut from the first match to the end of its unit.
_SITE_CUT = {
    "cum-sancta-mater-ecclesia": re.compile(r"\s*Perform bulk operations\b.*$", re.DOTALL),
    "exsurge-domine": re.compile(r"\s*\{.*$", re.DOTALL),
}
# Lines an editor or translator wrote about the document (C-18), never emitted.
_EDITORIAL = re.compile(r"Holy Father addressed|Translation by")
_ENTITY_FIXES = {"&quuot;": "”"}
# The number as misprinted, which a fix replaces: "Z 1. ", "1 4. " (split by markup), "28, ".
_MISPRINTED_NUMBER = re.compile(r"^(?:[A-Z] )?\d[\d ]*[.,]\s+")
# Printed numbers that are misprints, keyed by the paragraph's opening words (as 1.1's
# section fixes are): the number the run of paragraphs leaves free for them.
_NUMBER_FIXES = {
    "aeterni-patris": {"Z 1. But": 21},
    "humanae-vitae": {"1 4. Therefore": 14},
    "libertas": {"28, The Church": 28},
    "mediator-dei": {"100. These methods": 106},
    "menti-nostrae": {"63. Still another": 53, "64. Finally, We wish": 54,
                      "126. Ordinarily": 125},
    "pacem-in-terris": {"90. In the first place": 95},
}
# Documents whose text is vatican.va's translation in place of papalencyclicals.net's
# (1.3c): each unit keeps its anchor and ID where it is the same paragraph (aligned by
# `scripts/align_editions.py` and reviewed), and declares its text replaced for the release
# report's stability check. None marks every unit; a set names the units whose text changed
# where the rest of the document is the same translation.
TEXT_REPLACED = "vatican.va replaces papalencyclicals.net"
_NEW_TRANSLATION: dict[str, frozenset[str] | None] = {
    "ecclesiam-suam": None,
    "humanae-vitae": None,
    "mysterium-fidei": None,
    "pacem-in-terris": None,
    "pascendi-dominici-gregis": None,
}
# Sources that print their callers as plain numbers after a sentence.
_BARE_CALLERS = ("annus-qui-hunc", "mulieris-dignitatem")

# Sources whose HTML lost the space at each of its line ends (vatican.va's Divinum Illud
# Munus and Mirae Caritatis: "We haveseen good"). The space goes back only in the words
# `papal_spaces.json` lists, each checked against papalencyclicals.net's text of the same
# translation (1.3c), and after a comma or semicolon run into a word. Nothing else changes.
_SPACES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papal_spaces.json")
with open(_SPACES_FILE, encoding="utf-8") as _f:
    _LOST_SPACES: dict[str, dict[str, str]] = json.load(_f)
_JOINED = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
_LOST_SPACE_AFTER_PUNCTUATION = re.compile(r"(?<=[a-z])([,;])(?=[A-Za-z])")

# Units whose plain anchor is taken: while live it named other text, so the unit keeps
# the anchor holding its own ID, or takes one never live (D1). Keyed by slug, then by the
# plain anchor's last part: "preamble", "preface" or the paragraph's number as a string.
_ANCHOR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papal_anchors.json")
with open(_ANCHOR_FILE, encoding="utf-8") as _f:
    _UNIT_ANCHORS: dict[str, dict[str, str]] = json.load(_f)


class Token(NamedTuple):
    kind: str     # preamble, preface, section, heading, epigraph, para, text, prayer, closing
    number: int | None
    text: str
    segments: list[Segment]


class _Item(NamedTuple):
    el: object
    text: str
    segment: Segment


def strip_leading_caps(text: str) -> str:
    """Drop a leading run of ALL-CAPS words (a Latin incipit / title masthead that
    shares a paragraph with the greeting, e.g. 'IOANNES PAULUS PP. II EVANGELIUM
    VITAE To the Bishops…' → 'To the Bishops…'). Stops at the first word with a
    lowercase letter, so normal greetings ('To Our…', 'Venerable…') are untouched."""
    words = text.split()
    i = 0
    while i < len(words):
        letters = [c for c in words[i] if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            i += 1
        else:
            break
    return " ".join(words[i:])


def is_shouting(text: str) -> bool:
    """True for an ALL-CAPS masthead line (e.g. 'ENCYCLICAL LETTER … OF THE
    SUPREME PONTIFF …'); used to keep the document title block out of the
    preamble passage. Mixed-case greetings (~0–15% caps) are kept."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.7


def _is_bold_only(p) -> bool:
    kids = [c for c in p.children if getattr(c, "name", None)]
    bare = "".join(str(c) for c in p.children if not getattr(c, "name", None)).strip()
    t = p.get_text(strip=True)
    return (len(kids) == 1 and kids[0].name in ("b", "strong")
            and not bare and len(t) >= 8 and not t.endswith(":"))


def _is_centered(p) -> bool:
    return (p.get("align") or "").lower() == "center" \
        or "center" in (p.get("style") or "").lower()


def _is_italic_only(p) -> bool:
    kids = [c for c in p.children if getattr(c, "name", None)]
    bare = "".join(str(c) for c in p.children if not getattr(c, "name", None)).strip()
    return len(kids) == 1 and kids[0].name in ("i", "em") and not bare


def _all_link(el) -> bool:
    links = sum(len(a.get_text(strip=True)) for a in el.find_all("a"))
    return links >= len(el.get_text(strip=True)) > 0


def _short_line(text: str, limit: int = _HEADING_MAX) -> bool:
    return (0 < len(text) < limit and text[:1].isupper()
            and not _FINAL_PUNCTUATION.search(text))


# --------------------------------------------------------------------------- the stream

def _main(soup):
    """The element holding the document, as `checks.source_text` reads it."""
    for selector in ("div.entry-content", "div.documento"):
        found = soup.select(selector)
        if found:
            return max(found, key=lambda e: len(e.get_text(" ", strip=True)))
    return soup.body or soup


def _number_list_items(soup) -> None:
    """List items are named apart from `number_elements`' body elements (`l<k>`, the
    item's ordinal among the file's `<li>`), so reading them moves no `e<k>` locator."""
    for k, li in enumerate(soup.find_all("li"), 1):
        li[ORDINAL_ATTR] = f"l{k}"


def _wrap_loose_text(main) -> None:
    """Text sitting directly in a container, not in a block: lxml closes a `<p>` at a
    `<center>` and leaves the rest of its text loose, and some vatican.va pages set a
    paragraph straight in a `<font>`. Each run of it becomes a paragraph (`b<k>`, its
    ordinal in the file). The `<center>`s of papalencyclicals.net, lines the site adds,
    and vatican.va's language bar go."""
    for tag in main.find_all("center", recursive=False) + main.select("div.translation-field"):
        tag.decompose()
    k = 0

    def close(run: list) -> None:
        nonlocal k
        if "".join(str(n) for n in run).strip():
            k += 1
            wrapper = run[0].wrap(Tag(name="p"))
            for node in run[1:]:
                wrapper.append(node)
            wrapper[ORDINAL_ATTR] = f"b{k}"

    for container in [main] + main.find_all(_CONTAINERS):
        if container.find_parent(["p", "li", "h2", "h3", "h4"]) is not None:
            continue
        run: list = []
        for node in list(container.children):
            if isinstance(node, Comment):
                continue
            if isinstance(node, NavigableString) or node.name in _INLINE \
                    or (node.name == "font" and node.find(_BLOCKS) is None):
                run.append(node)
            else:
                close(run)
                run = []
        close(run)


def _locator(el) -> str:
    return element_locator(el) if el[ORDINAL_ATTR].isdigit() else el[ORDINAL_ATTR]


def _stream(main) -> list:
    """`p`, `li`, `h2` to `h4` and `hr` in document order, each block read once: an
    element whose ancestor is in the stream is skipped. A list item holding paragraphs is
    read through them, under their own locators."""
    out, taken = [], set()
    for el in main.find_all(["p", "li", "h2", "h3", "h4", "hr"]):
        if el.name == "li" and el.find("p") is not None:
            continue
        if id(el) in taken or any(id(parent) in taken for parent in el.parents):
            continue
        rule = el.find("hr") if el.name != "hr" else None
        if rule is not None and not el.get_text(strip=True):
            # A rule set inside inline markup (vatican.va's Quas Primas: `<i><font><hr>`),
            # which lxml moves into an empty paragraph: the rule is what the block holds.
            el = rule
        taken.add(id(el))
        out.append(el)
    return out


def _is_note_target(el) -> bool:
    first = next((c for c in el.children
                  if getattr(c, "name", None) or str(c).strip()), None)
    while getattr(first, "name", None) in ("sup", "font", "span", "b", "i"):
        first = next((c for c in first.children
                      if getattr(c, "name", None) or str(c).strip()), None)
    return getattr(first, "name", None) == "a" and bool(_NOTE_TARGET.match(first.get("name") or ""))


def _short_list_after(stream: list) -> bool:
    """Whether what follows is a list of short entries: notes that `<ol>` numbers."""
    entries = []
    for el in stream:
        if el.name != "li":
            break
        entries.append(len(el.get_text(" ", strip=True)))
    return bool(entries) and sum(entries) / len(entries) < _RESET_MEAN_CHARS


def _past_dating(stream: list, i: int) -> int:
    """`i`, or past the dating line a page sets after its rule, before the notes."""
    while i < len(stream) and _DATING.match(stream[i].get_text(" ", strip=True)):
        i += 1
    return i


def _notes_cut(stream: list) -> int:
    """The index in `stream` where the endnotes start, or its length. An `<hr>` counts
    only once a numbered paragraph has passed: mastheads rule themselves off too."""
    numbered = False
    for i, el in enumerate(stream):
        if el.name == "hr":
            if numbered:
                following = [x for x in stream[i + 1:i + 1 + _HR_REACH] if x.name != "hr"]
                if any(_NOTE_ONE.match(x.get_text(" ", strip=True)) for x in following) \
                        or _short_list_after(stream[i + 1:]):
                    return _past_dating(stream, i + 1)
            continue
        text = el.get_text(" ", strip=True)
        if _NOTES_HEADING.match(text) or _is_note_target(el) \
                or (numbered and _CONTENTS_HEADING.match(text)):
            return i
        if _NUM.match(text):
            numbered = True
    return len(stream)


def _chain(numbers: list[tuple[int, int]]) -> set[int]:
    """Which numbered items are the document's paragraphs: the longest strictly rising
    run through `numbers` ((index in the stream, number)), whose steps a section number
    can take. On a tie the later item wins, since a list in a section precedes the
    section's successor (… 5, list 1 to 7, 6, 7 …) and a table of contents the text."""
    best: list[int] = [1] * len(numbers)
    prior: list[int | None] = [None] * len(numbers)
    for j, (_, n) in enumerate(numbers):
        following = numbers[j + 1][1] if j + 1 < len(numbers) else None
        for i in range(j):
            m = numbers[i][1]
            if m < n and (n - m <= _MAX_STEP or following == n + 1) \
                    and best[i] + 1 >= best[j]:
                best[j], prior[j] = best[i] + 1, i
    if not best:
        return set()
    at: int | None = max(range(len(best)), key=lambda j: (best[j], j))
    chain = set()
    while at is not None:
        chain.add(numbers[at][0])
        at = prior[at]
    return chain


def _list_numbers(items: list[_Item]) -> dict[int, int]:
    """For a source that prints no numbers in its text: the numbers its `<ol>` items
    render with, honouring `start`, for the items of each list."""
    out: dict[int, int] = {}
    seen: dict[int, int] = {}
    for i, item in enumerate(items):
        if item.el.name != "li" or item.el.parent.name != "ol":
            continue
        parent = item.el.parent
        count = seen.get(id(parent), 0)
        seen[id(parent)] = count + 1
        out[i] = int(parent.get("start") or 1) + count
    return out


def _fix_numbers(items: list[_Item], slug: str | None) -> list[_Item]:
    out = []
    for item in items:
        for opening, n in _NUMBER_FIXES.get(slug, {}).items():
            if item.text.startswith(opening):
                text = f"{n}. {item.text[_MISPRINTED_NUMBER.match(item.text).end():]}"
                log.info("%s: %r is paragraph %d", slug, opening, n)
                item = item._replace(text=text, segment=Segment(item.segment.locator, text))
        out.append(item)
    return out


def _split_run_on(items: list[_Item], numbered: dict[int, tuple[int, str]]) -> list[_Item]:
    """A paragraph whose number sits inside the block before it ("… his mercy." <br> "37. The
    Church"): where the run of numbers has a gap, the block splits at the missing number."""
    out = list(items)
    keys = sorted(numbered)
    for a, b in reversed(list(zip(keys, keys[1:]))):
        missing = range(numbered[a][0] + 1, numbered[b][0])
        for n in reversed(missing):
            cut = re.compile(rf"(?<=[.!?\"”’)\]])\s+(?={n}\.\s+[A-Z“\"])")
            # A short head before the number is a heading run on to it.
            cut_short = re.compile(rf"^(?:[A-Z][\w’'-]*\s+){{1,6}}(?={n}\.\s+[A-Z“\"])")
            for i in range(b - 1, a - 1, -1):
                found = [x for x in cut.finditer(out[i].text)
                         if not _CITATION_END.search(out[i].text[:x.start()])]
                m = found[0] if found else cut_short.search(out[i].text)
                if m:
                    head, tail = out[i].text[:m.start()].rstrip() or out[i].text[:m.end()].rstrip(), \
                        out[i].text[m.end():]
                    loc = out[i].segment.locator
                    out[i:i + 1] = [out[i]._replace(text=head, segment=Segment(loc, head)),
                                    out[i]._replace(text=tail, segment=Segment(loc, tail))]
                    break
    return out


def _numbered(items: list[_Item]) -> dict[int, tuple[int, str]]:
    """Index in `items` to (number, text without it), for the document's paragraphs."""
    matches = {i: _NUM.match(item.text) for i, item in enumerate(items)}
    numbers = [(i, int(m.group(1))) for i, m in matches.items() if m]
    # The same number twice running is a misprint: the second continues the first. After a
    # short line, the first was a line of a table of contents.
    numbers = [x for k, x in enumerate(numbers) if k == 0 or numbers[k - 1][1] != x[1]
               or len(items[numbers[k - 1][0]].text) < _NUMBERED_HEADING_MAX]
    chain = _chain(numbers)
    if chain:
        found = {i: (int(matches[i].group(1)), matches[i].group(2).strip()) for i in chain}
        return _undotted(items, found)
    return {i: (n, items[i].text) for i, n in _list_numbers(items).items()}


def _undotted(items: list[_Item], numbered: dict[int, tuple[int, str]]) -> dict[int, tuple[int, str]]:
    """Paragraphs whose printed number lost its point ("14 If we read"), only where the
    number is the next one and the following paragraph is higher."""
    found = dict(numbered)
    for i, item in enumerate(items):
        m = _UNDOTTED.match(item.text)
        if not m or i in found:
            continue
        before = max((k for k in found if k < i), default=None)
        after = min((k for k in found if k > i), default=None)
        n = int(m.group(1))
        if before is not None and found[before][0] == n - 1 \
                and (after is None or found[after][0] > n):
            found[i] = (n, m.group(2))
    return found


def _reset_cut(items: list[_Item], numbered: dict[int, tuple[int, str]]) -> int:
    """Fallback for notes no marker announces: numbers restarting after the last paragraph
    with entries too short to be text."""
    last = max(numbered, default=-1)
    rest = [(i, _NUM.match(item.text)) for i, item in enumerate(items) if i > last]
    rest = [(i, m) for i, m in rest if m]
    if rest and int(rest[0][1].group(1)) <= _RESET_MAX:
        lengths = [len(items[i].text) for i, _ in rest]
        if sum(lengths) / len(lengths) < _RESET_MEAN_CHARS:
            return rest[0][0]
    return len(items)


def read_items(soup) -> list[_Item]:
    """The document's blocks up to its notes, callers dropped."""
    number_elements(soup)
    _number_list_items(soup)
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    main = _main(soup)
    _wrap_loose_text(main)
    stream = _stream(main)
    stream = stream[:_notes_cut(stream)]
    items = []
    for el in stream:
        if el.name == "hr":
            continue
        drop_caller_elements(el)
        text = " ".join(el.get_text(" ", strip=True).split())
        if any(c.isalnum() for c in text) and not _CHROME.search(text):
            items.append(_Item(el, text, Segment(_locator(el), text)))
    return items


# --------------------------------------------------------------------------- tokens

def _is_heading(item: _Item) -> bool:
    if item.el.name in ("h2", "h3", "h4"):
        return True
    if item.el.name == "li":
        return False
    if _short_line(item.text) or _BARE_NUMERAL.match(item.text) or _is_division(item):
        return True
    if len(item.text) < _HEADING_MAX and (is_shouting(item.text)
                                          or _CITED_LINE.search(item.text)
                                          or (_is_italic_only(item.el)
                                              and not item.text.endswith("."))):
        return True
    return bool(_is_bold_only(item.el) or _ROMAN.match(item.text)) \
        and len(item.text) < _BOLD_HEADING_MAX


def _is_division(item: _Item) -> bool:
    """A heading naming a division of the document, set apart from the text: a heading
    whatever follows it."""
    return len(item.text) < _BOLD_HEADING_MAX and bool(_MAJOR.match(item.text)) and (
        is_shouting(item.text) or _is_bold_only(item.el) or _is_centered(item.el))


def _chapter_test(headings: list[str]):
    """Which headings are the document's chapters: its named divisions when it prints at
    least two; else its ALL-CAPS headings where lesser ones sit under them; else all."""
    divisions = [t for t in headings if _MAJOR.match(t) and not _INTRODUCTION.match(t)
                 and not _CONCLUSION.match(t)]
    if len(divisions) >= 2:
        return lambda t: bool(_MAJOR.match(t))
    caps = sum(1 for t in headings if is_shouting(t))
    if 2 <= caps < len(headings):
        return is_shouting
    return lambda t: True


def _closing(tail: list[_Item]) -> tuple[list[_Item], list[Token]]:
    """What follows the last numbered paragraph: lines that stay in it (dating lines and
    signatures among them), and each prayer under its heading as a token of its own. Any
    dating line after the prayers joins the last of them, the document's last passage."""
    start = next((j for j, item in enumerate(tail)
                  if _short_line(item.text) and _PRAYER.search(item.text)), len(tail))
    prayers: list[Token] = []
    for item in tail[start:]:
        if _short_line(item.text) and _PRAYER.search(item.text):
            prayers.append(Token("prayer", None, item.text, []))
        else:
            prayers[-1].segments.append(item.segment)
    return tail[:start], [t for t in prayers if t.segments]


def _body_tokens(items: list[_Item], numbered: dict[int, tuple[int, str]],
                 start: int) -> list[Token]:
    """Tokens from `start`, which leaves only headings before the first numbered
    paragraph. An item is a heading when only headings stand between it and the next
    numbered paragraph; a heading with prose after it stays in the text it sits in."""
    last = max(numbered)
    heads: set[int] = set()
    for i in range(last, start - 1, -1):
        if i not in numbered and _is_heading(items[i]) \
                and (_is_division(items[i])
                     or next(j for j in range(i + 1, last + 1) if j not in heads) in numbered):
            heads.add(i)
    is_chapter = _chapter_test([items[i].text for i in heads])
    # A document whose first division comes very late: its earlier headings are chapters too.
    first = min((i for i in heads if is_chapter(items[i].text)
                 and not _INTRODUCTION.match(items[i].text)), default=start)
    early = {i for i in heads if i < first} \
        if sum(len(items[i].text) for i in range(start, first)) > _LONG_OPENING else set()

    toks: list[Token] = []
    cur: list | None = None   # [number, [parts], [segments]]

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            toks.append(Token("para", cur[0], "\n\n".join(x for x in cur[1] if x),
                              [seg for seg in cur[2] if seg.text]))
            cur = None

    i = start
    while i <= last:
        item = items[i]
        if i in numbered:
            flush()
            n, body = numbered[i]
            cur = [n, [body] if body else [], [Segment(item.segment.locator, body)]]
        elif i in heads:
            flush()
            if is_chapter(item.text) or i in early:
                label, segments = item.text, [item.segment]
                if _BARE_MAJOR.match(item.text) and i < last and i + 1 not in numbered \
                        and len(items[i + 1].text) < _BOLD_HEADING_MAX \
                        and (is_shouting(items[i + 1].text)
                             or not _SENTENCE_STOP.search(items[i + 1].text)):
                    i += 1
                    label = f"{label}: {items[i].text}"
                    segments = segments + [items[i].segment]
                toks.append(Token("section", None, label, segments))
            else:
                toks.append(Token("heading", None, item.text, [item.segment]))
        elif cur is not None:
            cur[1].append(item.text)
            cur[2].append(item.segment)
        else:                      # text under a division's heading, before any number
            toks.append(Token("epigraph", None, item.text, [item.segment]))
        i += 1
    kept, prayers = _closing(items[last + 1:])
    if cur is not None:
        cur[1] += [item.text for item in kept]
        cur[2] += [item.segment for item in kept]
    flush()
    return toks + prayers


def _is_pre_heading(item: _Item) -> bool:
    text = item.text
    return ((_short_line(text) or _INTRODUCTION.match(text) is not None)
            and not _GREETING.search(text) and not _CONTENTS_RANGE.search(text)
            and (not is_shouting(text) or _MAJOR.match(text) is not None))


def _is_prose(item: _Item) -> bool:
    """Not a table of contents' line: a sentence, once any caller is off its end."""
    text = strip_note_callers(item.text).rstrip()
    return (_SENTENCE_END.search(text) is not None and not _CONTENTS_RANGE.search(text)
            and not _all_link(item.el) and (len(text) >= _PREFACE_MIN or text[:1] == '"'))


def _saluted(out: list[Token]) -> bool:
    """Whether the greeting has closed on its salutation ("… Health and Apostolic
    Benediction."): the prose after it is the text, however short (Pacem in Terris §1)."""
    return bool(out) and out[-1].kind == "preamble" and _SALUTATION.search(out[-1].text) is not None


def _pre_tokens(items: list[_Item], first_number: int) -> tuple[list[Token], list[_Item]]:
    """Tokens before the first printed number, and the items left over: the headings of
    the paragraph that follows. The greeting is the preamble, up to the
    first ALL-CAPS line: a shouting line is the title masthead or an embedded
    table-of-contents header (modern vatican.va docs), never greeting prose. In a document
    numbering from 2, the prose after the greeting is its unprinted §1. Other prose after
    a masthead is the preface."""
    contents = next((i for i, x in enumerate(items) if _CONTENTS_HEADING.match(x.text)), None)
    if contents is not None:
        # A table of contents runs to the heading that opens the text, if one is printed.
        tail = items[contents:]
        opening = next((k for k in range(len(tail) - 1, -1, -1)
                        if _INTRODUCTION.fullmatch(tail[k].text)), None)
        items = items[:contents] + (tail[opening:] if opening is not None else [])
    end = len(items)
    while end and _is_pre_heading(items[end - 1]):
        end -= 1
    # Two divisions running are a table of contents, not this paragraph's headings.
    if sum(1 for x in items[end:] if _DIVISION.match(x.text)) >= 2:
        last = items[-1] if _INTRODUCTION.match(items[-1].text) else None
        items, end = items[:end] + ([last] if last else []), end
    out: list[Token] = []
    para: list[_Item] = []
    prose: list[_Item] = []
    shouted = False

    def close_prose() -> None:
        if prose:
            out.append(Token("preface", None, "\n\n".join(x.text for x in prose),
                             [x.segment for x in prose]))
            prose.clear()

    for item in items[:end]:
        text = item.text
        if item.el.name in ("h2", "h3", "h4") or _EDITORIAL.search(text):
            continue
        if is_shouting(text) or _is_division(item):
            if (_INTRODUCTION.match(text) or _ROMAN.match(text) or _MAJOR.match(text)) \
                    and not _CONTENTS_RANGE.search(text):
                close_prose()
                if out and out[-1].kind == "section":   # no text of its own: a contents line
                    out.pop()
                out.append(Token("section", None, text, [item.segment]))
            shouted = True
        elif first_number == 2:
            if para or (len(text) > _IMPLICIT_MIN and not _LONG_GREETING.search(text)) \
                    or (_saluted(out) and _is_prose(item) and _SENTENCE_STOP.search(text)
                        and not _GREETING.search(text)):
                para.append(item)
            elif not _short_line(text) or _GREETING.search(text):
                out.append(Token("preamble", None, text, [item.segment]))
        elif not shouted:
            out.append(Token("preamble", None, text, [item.segment]))
        elif _is_prose(item):
            prose.append(item)
    close_prose()
    rest = items[end:]
    # A contents line, when a division opens the text straight after it.
    if rest and out and out[-1].kind == "section" and _MAJOR.match(rest[0].text):
        out.pop()
    if para:
        out.append(Token("para", 1, "\n\n".join(x.text for x in para),
                         [x.segment for x in para]))
    return out, rest


def _unnumbered_tokens(items: list[_Item]) -> list[Token]:
    """A source with no paragraph numbers. Each `<p>` keeps the running count earlier
    builds gave it, because it is that unit's anchor; only the citation drops the number.
    Headings are sections, a masthead is skipped, and closing lines join the last text."""
    toks: list[Token] = []
    n = 0
    for item in items:
        text = item.text
        if item.el.name != "p":
            continue
        if not item.el[ORDINAL_ATTR].isdigit():       # loose text: no earlier build read it
            kind = "preamble" if _GREETING.search(text) else "preface"
            toks.append(Token(kind, None, text, [item.segment]))
            continue
        opened = any(t.kind == "text" for t in toks)
        if is_shouting(text) or (_ROMAN.match(text) and len(text) < _BOLD_HEADING_MAX):
            if opened:
                toks.append(Token("section", None, text, [item.segment]))
            continue
        n += 1
        if _EDITORIAL.search(text):
            continue
        last = toks[-1] if toks and toks[-1].kind == "text" else None
        if _DATING.match(text) or _SIGNED.match(text) \
                or (last and _short_line(text, _SIGNATURE_MAX) and item is items[-1]):
            if last:
                toks[-1] = last._replace(text=f"{last.text}\n\n{text}",
                                         segments=last.segments + [item.segment])
        elif (_is_bold_only(item.el) or (_is_centered(item.el) and _is_italic_only(item.el))
              or _short_line(text)) and len(text) < _BOLD_HEADING_MAX:
            if opened:          # before the text it is the masthead: a title, a date
                toks.append(Token("section", None, text, [item.segment]))
        else:
            toks.append(Token("text", n, text, [item.segment]))
    return toks


def _unnumbered_heading(item: _Item) -> _Item:
    """A number outside the paragraphs' run on a short line ("1. Full of Grace") numbers a
    heading, and the heading is the line without it."""
    m = _NUM.match(item.text)
    if m and item.el.name != "li" and _short_line(m.group(2).strip(), _NUMBERED_HEADING_MAX):
        text = m.group(2).strip()
        return item._replace(text=text, segment=Segment(item.segment.locator, text))
    return item


def _end_of(numbered: dict[int, tuple[int, str]], number: int | None) -> int | None:
    return next((i for i, (n, _) in sorted(numbered.items()) if n == number), None)


def tokens(soup, slug: str | None = None) -> list[Token]:
    """The document as an ordered list of tokens (see the module's docstring). `slug`
    selects the per-document ends in `_LAST_PARAGRAPH` and `_LIST_END`."""
    items = _fix_numbers(read_items(soup), slug)
    numbered = _numbered(items)
    if numbered:
        items = _split_run_on(items, numbered)
        numbered = _numbered(items)
    if not numbered:
        return _unnumbered_tokens(items)
    items = items[:_reset_cut(items, numbered)]
    # A site numbers the closing date as a last paragraph; it joins the one before.
    last = max(numbered)
    if len(numbered) > 1 and _DATING.match(numbered[last][1]) \
            and _DATED.search(numbered[last][1]) and len(numbered[last][1]) < _DATE_CARD_MAX:
        body = numbered.pop(last)[1]
        items[last] = items[last]._replace(text=body,
                                           segment=Segment(items[last].segment.locator, body))
    closing: list[_Item] = []
    end = _end_of(numbered, _LAST_PARAGRAPH.get(slug))
    if end is not None:
        items = items[:end + 1]
    end = _end_of(numbered, _LIST_END.get(slug))
    if end is not None:
        items, closing = items[:end + 1], items[end + 1:]
    items = [_unnumbered_heading(item) if i not in numbered else item
             for i, item in enumerate(items)]
    first = min(numbered)
    pre, kept = _pre_tokens(items[:first], numbered[first][0])
    body = items[first:]
    numbered = {i - first + len(kept): v for i, v in numbered.items()}
    toks = pre + _body_tokens(kept + body, numbered, 0)
    if closing:
        toks.append(Token("closing", None, "\n\n".join(x.text for x in closing),
                          [x.segment for x in closing]))
    return toks


# --------------------------------------------------------------------------- building

def _label_part(part: str) -> str:
    """One part of a label in title case; a citation closing it is left as printed."""
    head, citation = _LABEL_CITATION.match(part).groups()
    head = smart_title_case(head.upper() if is_shouting(head) else head)
    return head + (citation or "")


def _chapter_label(text: str) -> str:
    label = ": ".join(_label_part(part) for part in clean_text(text).rstrip(" -–").split(": "))
    label = _ROMAN_WORD.sub(lambda m: m.group(0).upper(), label)
    label = _NUMERAL_OPENING.sub(lambda m: m.group(0)[:-1] + m.group(0)[-1].upper(), label)
    return _WORD_OPENING.sub(lambda m: m.group(0).upper(), label)


def _clean(text: str, slug: str) -> str:
    for wrong, right in _ENTITY_FIXES.items():
        text = text.replace(wrong, right)
    spaces = _LOST_SPACES.get(slug)
    if spaces:
        text = _LOST_SPACE_AFTER_PUNCTUATION.sub(r"\1 ", text)
        text = _JOINED.sub(lambda m: spaces.get(m.group(0), m.group(0)), text)
    cut = _SITE_CUT.get(slug)
    if cut:
        text = cut.sub("", text)
    text = _TRAILING_NOTES_HEADING.sub("", text)
    text = strip_note_callers(clean_text(strip_footnote_markers(strip_boilerplate(text))))
    # A caller between two sentences ('soul?"(23) This') leaves them joined once it goes.
    text = repair_sentence_joins(text)
    return strip_bare_callers(text) if slug in _BARE_CALLERS else text


def _disambiguate_title(title: str, slug: str, year: int) -> str:
    base_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return title if slug == base_slug else f"{title} ({year})"


def _anchor(slug: str, part: str) -> str:
    return make_anchor(slug, _UNIT_ANCHORS.get(slug, {}).get(part, part))


class _Unit(NamedTuple):
    content: str
    pieces: list[str]
    reference: str | None
    base_anchor: str
    chapter_key: str
    chapter_label: str
    unit_label: str | None
    segments: list[Segment]


def build_document(entry: dict, collection: str, src_dir: str) -> Document:
    path = os.path.join(src_dir, entry["file"])
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    slug, author = entry["slug"], entry["author"]
    toks = tokens(soup, slug)
    title = _disambiguate_title(entry["title"], slug, entry["year"])
    source_key = f"{collection}/{slug}"
    did = resolve_document_id(collection, source_key, (collection, slug))
    has_sec = any(t.kind == "section" for t in toks)
    meta = {"pope": author, "url": entry["url"], "source_url": entry["url"]}
    units: list[_Unit] = []

    def emit(content: str, ref: str | None, base_anchor: str, ckey: str, clabel: str,
             unit: str | None, segments: list[Segment]) -> None:
        content = _clean(content, slug)
        if not content:
            return
        pieces = pack_text(content, segments, settings.MAX_PASSAGE_CHARS)
        units.append(_Unit(content, pieces, ref, base_anchor, ckey, clabel, unit, segments))

    pre = [t for t in toks if t.kind == "preamble"]
    if pre:
        text = strip_leading_caps("\n\n".join(t.text for t in pre).strip()).strip()
        emit(text, f"{title} — Preamble", _anchor(slug, "preamble"),
             make_anchor(slug, "preamble"), "Preamble", None,
             [s for t in pre for s in t.segments])

    paragraphs = [t.number for t in toks if t.kind in ("para", "text")]
    bucket_range: dict[int, tuple[int, int]] = {}
    if not has_sec:
        for n in paragraphs:
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range.get(b, (n, n))
            bucket_range[b] = (min(lo, n), max(hi, n))
    # With at most 20 paragraphs there is one chapter, named for the document. So too with
    # no printed numbers: a paragraph range would name numbers the source does not have.
    single = not has_sec and (len(paragraphs) <= _BUCKET
                              or not any(t.kind == "para" for t in toks))

    sec_ord = 0
    cur_key = cur_label = None
    empty_chapter = False
    pending: list[Token] = []
    for t in toks:
        if t.kind == "section":
            label = _chapter_label(t.text)
            if cur_key is not None and sum(
                    len(h.text) for h in pending if h.kind == "epigraph") >= _EPIGRAPH_MAX:
                # Text under a heading with no number after it, the Syllabus's section IV.
                # It is its own unit: it opens no numbered paragraph of another section.
                part = f"text-{sec_ord}"
                emit("\n\n".join(h.text for h in pending), f"{title}, {cur_label}",
                     _anchor(slug, part), cur_key, cur_label, None,
                     _with_headings(pending[:-1], pending[-1].segments))
                pending = []
            elif cur_key is not None and empty_chapter and _MAJOR.match(cur_label):
                label = f"{cur_label}: {label}"     # the division has its subsection's text
            sec_ord += 1
            cur_key = make_anchor(slug, f"sec-{sec_ord}")
            cur_label = label
            empty_chapter = True
            pending.append(t)
            continue
        if t.kind in ("heading", "epigraph"):
            pending.append(t)
            continue
        if t.kind == "prayer":
            label = _chapter_label(t.text)
            k = sum(1 for u in units if "/prayer-" in u.base_anchor) + 1
            part = make_anchor(slug, f"prayer-{k}")
            emit("\n\n".join(s.text for s in t.segments), f"{title}, {label}", part, part, label,
                 None, t.segments)
            continue
        if t.kind == "closing":
            part = make_anchor(slug, "closing")
            emit(t.text, f"{title}, Conclusion", part, part, "Conclusion", None, t.segments)
            continue
        if t.kind not in ("para", "text", "preface"):
            continue
        n = t.number
        if has_sec:
            if cur_key is None:
                cur_key, cur_label = make_anchor(slug, "sec-0"), "Introduction"
            ckey, clabel = cur_key, cur_label
        elif single:
            ckey, clabel = make_anchor(slug, "bucket-0"), title
        elif t.kind == "preface":
            ckey, clabel = make_anchor(slug, "bucket-0"), _bucket_label(*bucket_range[0])
        else:
            b = (n - 1) // _BUCKET
            ckey, clabel = make_anchor(slug, f"bucket-{b}"), _bucket_label(*bucket_range[b])
        text = "\n\n".join([h.text for h in pending] + [t.text])
        segments = _with_headings(pending, t.segments)
        pending = []
        empty_chapter = False
        if t.kind == "preface":
            label = cur_label or "Preface"
            emit(text, f"{title}, {label}", _anchor(slug, "preface"), ckey, clabel, None, segments)
        elif t.kind == "para":
            emit(text, f"{title}, §{n}", _anchor(slug, str(n)), ckey, clabel, f"§{n}", segments)
        else:
            emit(text, None, _anchor(slug, str(n)), ckey, clabel, None, segments)

    passages = _passages(units, title, meta)
    if slug in _NEW_TRANSLATION:
        changed = _NEW_TRANSLATION[slug]
        for p in passages:
            if changed is None or unit_anchor(p.anchor).split("/", 1)[1] in changed:
                p.metadata = {**p.metadata, "text_replaced": TEXT_REPLACED}
    _log_short(title, passages)
    metadata = {"url": entry["url"], "source_url": entry["url"], "pope": author,
                "source_key": source_key, "anchor_scheme": ANCHOR_SCHEME,
                "genre": _genre(entry, source_key)}
    if entry.get("form"):
        metadata["form"] = entry["form"]
    return Document(id=did, collection=collection, title=title, author=author,
                    year=entry["year"], metadata=metadata, passages=passages)


def _genre(entry: dict, source_key: str) -> str:
    """The manifest's genre (1.3b), which the release report shows and 2.3 copies into the
    registry. A manifest vendored before 1.3b has none: re-vendor rather than guess."""
    if not entry.get("genre"):
        raise ValueError(f"{source_key}: the manifest has no genre; run "
                         "`python3 scripts/vendor_sources.py --collection <collection>` "
                         "to copy it from papal_genres.csv")
    return entry["genre"]


def _with_headings(headings: list[Token], segments: list[Segment]) -> list[Segment]:
    """`segments` with the headings opening the first of them, so that packing never
    leaves a heading alone on a card."""
    if not headings or not segments:
        return segments
    opening = "\n\n".join([h.text for h in headings] + [segments[0].text])
    return [Segment(segments[0].locator, opening)] + segments[1:]


def _bucket_label(lo: int, hi: int) -> str:
    return f"Paragraphs {lo}–{hi}" if lo != hi else f"Paragraph {lo}"


def _passages(units: list[_Unit], title: str, meta: dict) -> list[Passage]:
    """Passages in reading order. A unit with no citation of its own (an unnumbered
    source's paragraph) cites its chapter and its place among the chapter's passages."""
    counts: dict[str, int] = {}
    for u in units:
        if u.reference is None:
            counts[u.chapter_key] = counts.get(u.chapter_key, 0) + len(u.pieces)
    seen: dict[str, int] = {}
    passages: list[Passage] = []
    anchors = unique_unit_anchors([u.base_anchor for u in units], [len(u.pieces) > 1 for u in units])
    for u, anc in zip(units, anchors):
        named = name_pieces(anc, u.content, u.pieces, u.segments)
        for k, (piece, (anchor, held)) in enumerate(zip(u.pieces, named), 1):
            if u.reference is None:
                seen[u.chapter_key] = seen.get(u.chapter_key, 0) + 1
                base = title if u.chapter_label == title else f"{title}, {u.chapter_label}"
                reference = piece_reference(base, None, None, seen[u.chapter_key],
                                            counts[u.chapter_key])
            else:
                reference = piece_reference(u.reference, None, None, k, len(u.pieces))
            passages.append(Passage(content=piece, reference=reference, anchor=anchor,
                                    chapter_key=u.chapter_key, chapter_label=u.chapter_label,
                                    position=len(passages), unit_label=u.unit_label, metadata=meta,
                                    source_units=held))
    return passages


def _log_short(title: str, passages: list[Passage]) -> None:
    """A passage this short is logged: the health rule's exceptions are read from here."""
    for p in passages:
        if len(p.content) < _SHORT_PASSAGE:
            log.info("%s: %s holds %d characters", title, p.anchor, len(p.content))


def build_documents(collection: str, src_dir: str) -> list[Document]:
    with open(os.path.join(src_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e, collection, src_dir) for e in manifest]
