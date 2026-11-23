"""Ecumenical Councils ingestion.

One Document per council (ecumenical 1-20) or per Vatican II document. Each council
is built from its own source: Percival (1.2c), Schroeder (1.2e), Waterworth (Trent,
1.2b), Schaff (Vatican I, 1.2d) and vatican.va's Vatican II pages (1.1), here.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import NamedTuple

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

import headings
from config import settings
from identity import anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import smart_title_case
from normalize.footnotes import drop_caller_elements
from normalize.boilerplate import strip_boilerplate
from ingest.councils_percival import (COUNCILS as PERCIVAL_COUNCILS, SOURCE_FILE as PERCIVAL_FILE,
                                      build_percival, read_divs)
from ingest.councils_schaff import SOURCE_FILE as SCHAFF_FILE, build_schaff
from ingest.councils_schroeder import WORKS as SCHROEDER_WORKS, build_schroeder
from ingest.councils_trent import build_trent
from ingest.pieces import (ORDINAL_ATTR, Segment, name_pieces,
                           number_elements, pack_text, piece_reference,
                           unique_unit_anchors)
from registry import ANCHOR_SCHEME, resolve_document_id

log = logging.getLogger(__name__)

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_CHROME = re.compile(
    r"automatically notified|more information about this site|fan of our facebook"
    r"|^search tips$|^sitemap$|return to (?:the )?home", re.IGNORECASE)
_BUCKET = 20   # §-paragraphs per chapter when a doc has no chapter headings


def _strip_chrome(soup) -> None:
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "form"]):
        tag.decompose()


class _Builder:
    """Accumulates the units of one council document, then names them: each unit's
    anchor is unique (`ingest.pieces.unique_unit_anchors`) and its pieces are named by
    the source element they open with."""

    def __init__(self, clean):
        self.units: list[tuple] = []
        self.clean = clean

    def add(self, *, body: str, ref: str, base_anchor: str, ckey: str,
            clabel: str, unit: str | None, meta: dict, segments: list[Segment],
            heads: dict[str, dict] | None = None) -> None:
        """`heads` marks the segments that are headings (issue #445), by locator: the
        keyword arguments of `headings.mark`."""
        body = self.clean(body)
        if len(body) < 1:
            return
        marks, cursor = [], 0
        for seg in segments:
            if seg.locator not in (heads or {}):
                continue
            words = self.clean(seg.text)
            at = body.find(words, cursor)
            if not words or at < 0:
                raise ValueError(f"{ref}: heading {seg.locator} {seg.text[:60]!r} not in its text")
            marks.append(headings.mark(at, at + len(words), **heads[seg.locator]))
            cursor = at + len(words)
        pieces = pack_text(body, segments, settings.MAX_PASSAGE_CHARS)
        self.units.append((body, pieces, ref, base_anchor, ckey, clabel, unit, meta, segments,
                           headings.split_marks(body, pieces, marks)))

    @property
    def passages(self) -> list[Passage]:
        out: list[Passage] = []
        anchors = unique_unit_anchors([u[3] for u in self.units],
                                      [len(u[1]) > 1 for u in self.units])
        for (body, pieces, ref, _, ckey, clabel, unit, meta, segments, marks), anc in zip(
                self.units, anchors):
            for k, (piece, (anchor, held), piece_marks) in enumerate(
                    zip(pieces, name_pieces(anc, body, pieces, segments), marks), 1):
                out.append(Passage(content=piece,
                                   reference=piece_reference(ref, None, None, k, len(pieces)),
                                   anchor=anchor,
                                   chapter_key=ckey, chapter_label=clabel, position=len(out),
                                   unit_label=unit,
                                   metadata=headings.with_headings(meta, piece_marks),
                                   source_units=held))
        return out


def _source_key(entry: dict) -> str:
    """The council manifest has no slug; its file name, without extension, serves."""
    return "councils/" + os.path.splitext(entry["file"])[0]


# --------------------------------------------------------------------------- Vatican II
# vatican.va's English pages (1.1). A section ("12.") runs on through the unnumbered
# paragraphs after it, and everything after the notes heading is the notes. The words are
# kept as the page prints them (Decision log "LEV texts from vatican.va"): only footnote
# callers and the section numbers, which become labels, are taken out.

_V2_NOTES = re.compile(r"^(?:END|FOOT)?NOTES?$", re.IGNORECASE)
_V2_NUM = re.compile(r"^(\d{1,3})\s*\.(?=\s|$)\s*(.*)", re.DOTALL)        # "12.", "9 . Hence"
_V2_ROMAN = re.compile(r"^([IVXLC]+)\.?$")                                 # "II."
_V2_ROMAN_TITLE = re.compile(r"^([IVXLC]+)\.?\s+(\S.*)$", re.DOTALL)       # "VI SACRED MUSIC"
_V2_CHAPTER = re.compile(r"^CHAPTER\b\s*(?:([IVXLC]+)\b\.?)?\s*(.*)$", re.DOTALL)
_V2_PART = re.compile(r"^PART\s+([IVXLC]+)\b\.?\s*(.*)$", re.DOTALL)
_V2_OPENING = re.compile(r"^(?:PREFACE|INTRODUCTION|PREAMBLE)$")
_V2_PROMULGATION = re.compile(r"^Each and all these (?:matters|items)\b")
_V2_FINAL = re.compile(r"[.!?;,\"”’]$")
_V2_HEADING_MAX = 130
# The language bar, "[ AR - BE - … - ZH ]": the page's own language is not a link.
_V2_LANGUAGES = re.compile(r"^\[\s*[A-Z]{2}(?:\s*-\s*[A-Z]{2})*\s*\]$")
# A heading the page sets as one line that is two.
_V2_LABELS = {"INTRODUCTORY STATEMENT THE SITUATION OF MEN IN THE MODERN WORLD":
              "Introductory Statement: The Situation of Men in the Modern World"}
_V2_INLINE = ("i", "em", "b", "strong", "span", "a", "u", "sup", "sub", "br", "font")
_V2_BLOCKS = ("p", "h1", "h2", "h3", "h4", "li")
_V2_NESTED = ("p", "li", "center", "table", "div", "blockquote", "ul", "ol")
# Footnote callers (C-17): "(9)" and the starred "(21*)" after a word, punctuation or a
# closing quote, so "(Rom. 12:10)" stays, and "[9]" or "[ 40 ]".
_V2_PAREN_CALLER = re.compile(r"(?<=[A-Za-z\"”’.,;:!?)\]])\s?\(\d{1,3}\*?\)")
_V2_BRACKET_CALLER = re.compile(r"(?<=\S)\s*\[\s*\d{1,3}\s*\]")
_V2_EMPTY_CALLER = re.compile(r"\s*\[\s*\]")      # "[ ]" once a linked number goes

# Sections the English page numbers otherwise than the Latin, keyed by the document and
# the paragraph's opening words: the Latin number. The words stay as printed.
_SECTION_NUMBER_FIXES = {
    ("Sacrosanctum Concilium", "81. In order that the divine office"): 87,
    # The English prints no "21.": Latin 21 runs on in its section 20, and its "21." is
    # Latin 22 (Carter, 10 Nov 2026).
    ("Optatam Totius", "But since it is necessary for the students"): 21,
    ("Optatam Totius", "21. Since priestly training"): 22,
}
# Sections whose number is a live anchor of another unit, which a section never takes
# (D1): `optatam-totius/21` held Latin 22, which keeps that ID as `/22`; Gravissimum
# Educationis's `/2` to `/11` held its footnotes, the sections themselves never having
# been read (its `/1`, `/7` and `/12` held their headings, and keep them).
_SECTION_ANCHORS = {("Optatam Totius", 21): "para-21",
                    **{("Gravissimum Educationis", n): f"para-{n}"
                       for n in (2, 3, 4, 5, 6, 8, 9, 10, 11)}}


class _Appendix(NamedTuple):
    """A named appendix after the last section: where it starts, its anchor namespace,
    its chapter label and citation, and whether it numbers its own sections."""
    opens: re.Pattern
    name: str
    label: str
    numbered: bool


_APPENDICES = {
    # The Acts of the Council printed with the Constitution (Carter, 4 and 10 Nov 2026).
    "Lumen Gentium": (
        _Appendix(re.compile(r"^APPENDIX\b"), "notificationes",
                  "Notificationes of the Secretary General", False),
        _Appendix(re.compile(r"^Preliminary Note of Explanation$"), "nota-praevia",
                  "Preliminary Note of Explanation", True)),
    "Sacrosanctum Concilium": (
        _Appendix(re.compile(r"^APPENDIX$"), "appendix",
                  "Appendix: Declaration on the Revision of the Calendar", False),),
}


def _v2_blocks(soup) -> list:
    """The page's blocks in reading order: each paragraph, heading or list item, and each
    run of text set loose in a container (`<center><b>CHAPTER I</b>`, which lxml leaves
    outside any paragraph), wrapped in a paragraph named `b<k>`."""
    out: list = []
    k = 0

    def visit(container) -> None:
        nonlocal k
        run: list = []

        def close() -> None:
            nonlocal k, run
            if any((n.get_text() if isinstance(n, Tag) else str(n)).strip() for n in run):
                k += 1
                wrapper = run[0].wrap(soup.new_tag("p"))
                for node in run[1:]:
                    wrapper.append(node)
                wrapper[ORDINAL_ATTR] = f"b{k}"
                out.append(wrapper)
            run = []

        for node in list(container.children):
            if isinstance(node, Comment):
                continue
            if isinstance(node, NavigableString) \
                    or (node.name in _V2_INLINE and node.find(_V2_NESTED) is None):
                run.append(node)
                continue
            close()
            if node.name in _V2_BLOCKS and node.find(_V2_NESTED) is None:
                out.append(node)
            elif node.name != "hr":
                visit(node)
        close()

    visit(soup.body or soup)
    return out


def _v2_locator(el) -> str:
    ordinal = el[ORDINAL_ATTR]
    return f"e{ordinal}" if ordinal.isdigit() else ordinal


def _v2_text(el) -> str:
    """An element's text as the page shows it: its strings joined, a `<br>` a space."""
    parts = []
    for node in el.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif node.name == "br":
            parts.append(" ")
    return " ".join("".join(parts).split())


def _v2_emphasis(el, text: str, tags: tuple) -> bool:
    """Whether nearly all of a block's text is set in `tags` (bold, italic)."""
    inner = sum(len(t.get_text(strip=True)) for t in el.find_all(tags)
                if t.find_parent(tags) is None)
    return inner >= 0.8 * len(text.replace(" ", ""))


def _v2_shouting(text: str) -> bool:
    """A line in capitals ("PREFACE", "THE LAITY")."""
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) >= 0.8 * len(letters)


def _v2_centered(el) -> bool:
    return (el.get("align") or "").lower() == "center" or el.find_parent("center") is not None


def _v2_label(el) -> str:
    """A heading in capitals as a chapter label, its lines (split at `<br>`) joined
    with a colon: "Introductory Statement: The Situation of Men in the Modern World"."""
    lines, line = [], []
    for node in el.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            line.append(str(node))
        elif node.name == "br":
            lines.append("".join(line))
            line = []
    lines.append("".join(line))
    text = " ".join(" ".join(lines).split())
    if text in _V2_LABELS:
        return _V2_LABELS[text]
    return ": ".join(smart_title_case(" ".join(x.split())) for x in lines if x.strip())


def _v2_heading(el, text: str) -> bool:
    """A heading line: short, set off (bold, centred or in capitals), and no sentence."""
    if len(text) > _V2_HEADING_MAX:
        return False
    if not (_v2_emphasis(el, text, ("b", "strong")) or _v2_centered(el) or _v2_shouting(text)):
        return False
    return not _V2_FINAL.search(text) or bool(_V2_ROMAN.match(text))


def _v2_clean(body: str) -> str:
    body = _V2_BRACKET_CALLER.sub("", _V2_PAREN_CALLER.sub("", body))
    body = _V2_EMPTY_CALLER.sub("", body)
    return clean_text(strip_boilerplate(body))


# The level of a heading set inside a section (issue #445): the chapters are labels, so
# a "SECTION", "ARTICLE" or Roman-numbered head is the tier below them (2), and a
# lettered or numbered one ("A) General norms", "2. The diocesan curia") deeper (3).
_V2_LEVEL_2 = re.compile(r"^(?:SECTION|ARTICLE)\b|^[IVXLC]+\.\s", re.IGNORECASE)
# Heads the page numbers out of step with their siblings, by document and text: the
# level their place gives them. Sacrosanctum Concilium's first section prints "1." where
# the rest of its chapter prints "II.", "III.".
_V2_LEVEL_FIXES = {
    ("Sacrosanctum Concilium",
     "1. The Nature of the Sacred Liturgy and Its Importance in the Church's Life"): 2,
}


def _v2_level(title: str, text: str) -> int:
    fixed = _V2_LEVEL_FIXES.get((title, text))
    if fixed is not None:
        return fixed
    return 2 if _V2_LEVEL_2.match(text) else 3


class _Unit:
    def __init__(self, anchor: str, ref: str, label: str, ckey: str, clabel: str):
        self.anchor, self.ref, self.label = anchor, ref, label
        self.ckey, self.clabel = ckey, clabel
        self.paragraphs: list[Segment] = []


def build_vatican2(entry: dict, soup: BeautifulSoup) -> Document:
    number_elements(soup)
    for k, li in enumerate(soup.find_all("li"), 1):
        li[ORDINAL_ATTR] = f"l{k}"
    _strip_chrome(soup)
    title = entry["document"]
    dslug = slugify(title)
    did = resolve_document_id("councils", _source_key(entry),
                              ("councils", "Second Vatican Council", title))
    meta = {"council": "Second Vatican Council",
            "document_type": entry.get("document_type"), "year": entry["year"],
            "url": entry["url"]}

    blocks = []
    for el in _v2_blocks(soup):
        drop_caller_elements(el)
        text = _v2_text(el)
        if not text or _CHROME.search(text) or _V2_LANGUAGES.match(text):
            continue
        if _V2_NOTES.match(text):
            break                                   # the notes, to the end of the page
        blocks.append((el, text))

    units: list[_Unit] = []
    current: _Unit | None = None
    pending: list[Segment] = []                     # subheadings, for the next paragraph
    heads: dict[str, dict] = {}                     # heading segments' marks, by locator
    expected = 1                                    # the next section number
    namespace, appendix = dslug, None
    chap_ord, ckey, clabel = 0, make_anchor(dslug, "chap-0"), "Preface"
    headed = False                                  # any chapter heading at all
    waiting: tuple | None = None                    # a heading line still to take a title
    part: str | None = None
    started = False                                 # past the masthead

    def open_chapter(label: str, key: str | None = None) -> None:
        nonlocal current, chap_ord, ckey, clabel, headed
        close_unit()
        headed = True
        if key is None:
            chap_ord += 1
            key = make_anchor(dslug, f"chap-{chap_ord}")
        ckey, clabel = key, label

    def close_unit() -> None:
        nonlocal current
        if pending and current is not None:
            # Lines left over at a unit's close introduce nothing (the Nota praevia's
            # signature): they stay as text, unmarked.
            for seg in pending:
                heads.pop(seg.locator, None)
            current.paragraphs.extend(pending)
            pending.clear()
        current = None

    def open_unit(anchor: str, ref: str, label: str) -> None:
        nonlocal current
        current = _Unit(anchor, ref, label, ckey, clabel)
        units.append(current)

    def add(segment: Segment) -> None:
        current.paragraphs.extend(pending)
        pending.clear()
        current.paragraphs.append(segment)

    def take_title(text: str) -> None:
        nonlocal waiting, part
        kind, numeral = waiting
        waiting = None
        if kind == "bare-chapter":
            m = _V2_ROMAN_TITLE.match(text)
            numeral, text = (m.group(1), m.group(2)) if m else (None, text)
            kind = "chapter"
        name = smart_title_case(text)
        if kind == "chapter":
            label = f"Chapter {numeral}: {name}" if numeral else name
            open_chapter(f"Part {part}, {label}" if part else label)
        elif kind == "part":
            part = numeral
            open_chapter(f"Part {numeral}: {name}")
        elif kind == "roman":
            open_chapter(f"{numeral}. {name}")
        # an appendix's own title is its heading only: its label is fixed

    for el, text in blocks:
        seg = Segment(_v2_locator(el), text)
        if not started:
            if title.upper() in text:
                continue                            # the masthead
            started = True
        rule = next((a for a in _APPENDICES.get(title, ())
                     if a is not appendix and a.opens.match(text)), None)
        if rule is not None:
            appendix, namespace, expected = rule, make_anchor(dslug, rule.name), 1
            open_chapter(rule.label, make_anchor(dslug, rule.name))
            waiting = ("appendix", None)
            continue
        heading = _v2_heading(el, text)
        if waiting is not None and heading:
            take_title(text)
            continue
        waiting = None
        fixed = next((n for (doc, words), n in _SECTION_NUMBER_FIXES.items()
                      if doc == title and text.startswith(words)), None)
        if fixed is not None:
            log.info("%s: section number fix applied, %r -> %d", title, text[:40], fixed)
        m = _V2_NUM.match(text)
        number = fixed if fixed is not None else (int(m.group(1)) if m else None)
        numbered = appendix is None or appendix.numbered
        if number == expected and numbered:
            body = m.group(2) if m else text
            if appendix is None and m and _v2_heading(el, body):
                open_chapter(f"{number}. {body}")   # a numbered heading opens a chapter
                heads[seg.locator] = {"level": 1, "chapter_title": True}
            if appendix is None:
                anchor = make_anchor(dslug, _SECTION_ANCHORS.get((title, number), number))
                open_unit(anchor, f"{title}, §{number}", f"§{number}")
            else:
                open_unit(f"{namespace}/{number}",
                          f"{title}, {appendix.label}, {number}",
                          f"{appendix.label}, {number}")
            expected = number + 1
            add(Segment(seg.locator, body))
            continue
        if heading:
            if m is None and (mc := _V2_CHAPTER.match(text)):
                if mc.group(2):
                    rest = mc.group(2)
                    open_chapter(f"Chapter {mc.group(1)}: {smart_title_case(rest)}"
                                 if mc.group(1) else smart_title_case(rest))
                    if part:
                        clabel = f"Part {part}, {clabel}"
                else:
                    waiting = ("chapter", mc.group(1)) if mc.group(1) else ("bare-chapter", None)
                continue
            if mp := _V2_PART.match(text):
                if mp.group(2):
                    part = mp.group(1)
                    open_chapter(f"Part {part}: {smart_title_case(mp.group(2))}")
                else:
                    waiting = ("part", mp.group(1))
                continue
            if mr := _V2_ROMAN.match(text):
                waiting = ("roman", mr.group(1))
                continue
            if _v2_shouting(text):
                name = _v2_label(el)
                if expected == 1 and appendix is None and _V2_OPENING.match(text):
                    open_chapter(name, make_anchor(dslug, "chap-0"))
                else:
                    open_chapter(name)
                continue
            pending.append(seg)                     # a subheading: the next section's
            heads[seg.locator] = {"level": _v2_level(title, text)}
            continue
        if appendix is None and _V2_PROMULGATION.match(text):
            open_chapter("Promulgation", make_anchor(dslug, "promulgation"))
            open_unit(make_anchor(dslug, "promulgation"), f"{title}, Promulgation",
                      "Promulgation")
        elif current is None:
            if appendix is not None and appendix.numbered:
                pending.append(seg)                 # the appendix's opening words
                continue
            if appendix is not None:
                name, label = namespace, appendix.label
            elif expected == 1:
                name, label = make_anchor(dslug, "preface"), clabel
            else:
                name, label = make_anchor(dslug, slugify(clabel)), clabel
            open_unit(name, f"{title}, {label}", label)
        add(seg)
    close_unit()

    b = _Builder(clean=_v2_clean)
    for u in units:
        ckey_, clabel_ = u.ckey, u.clabel
        if not headed and u.label.startswith("§"):
            # A declaration with no headings at all: §-number buckets, so the reader
            # still has chapters (as the encyclicals fall back).
            n = int(u.label[1:])
            bk = (n - 1) // _BUCKET
            ckey_ = make_anchor(dslug, f"bucket-{bk}")
            clabel_ = f"Paragraphs {bk * _BUCKET + 1}–{bk * _BUCKET + _BUCKET}"
        b.add(body="\n\n".join(s.text for s in u.paragraphs), ref=u.ref, base_anchor=u.anchor,
              ckey=ckey_, clabel=clabel_, unit=u.label, meta=meta, segments=u.paragraphs,
              heads=heads)
    return Document(id=did, collection="councils", title=title,
                    author="Second Vatican Council", year=entry["year"],
                    metadata={**meta, "source_key": _source_key(entry),
                              "anchor_scheme": ANCHOR_SCHEME},
                    passages=b.passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    docs: list[Document] = []
    percival = None
    for entry in manifest:
        if entry["council"] in PERCIVAL_COUNCILS:
            # Percival (1.2c); the Tanner page stays vendored, unread (Carter, 4 Nov 2026).
            percival = percival or read_divs(os.path.join(_SRC, PERCIVAL_FILE))
            docs.append(build_percival(
                entry, resolve_document_id("councils", _source_key(entry),
                                           ("councils", entry["council"], entry["council"])),
                _source_key(entry), percival))
            continue
        if entry["council"] in SCHROEDER_WORKS:
            # The Tanner page stays vendored; no builder reads it (Carter, 4 Nov 2026).
            docs.append(build_schroeder(
                entry, resolve_document_id("councils", _source_key(entry),
                                           ("councils", entry["council"], entry["council"])),
                _source_key(entry)))
            continue
        if entry["council"] == "First Vatican Council":
            # Manning's English in Schaff (1.2d); the Tanner page stays vendored, unread.
            docs.append(build_schaff(
                entry, resolve_document_id("councils", _source_key(entry),
                                           ("councils", entry["council"], entry["council"])),
                _source_key(entry), os.path.join(_SRC, SCHAFF_FILE)))
            continue
        with open(os.path.join(_SRC, entry["file"]), "rb") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        if entry["council"] == "Council of Trent":
            # Waterworth's text, parsed whole by session (1.2b).
            docs.append(build_trent(
                entry, soup, resolve_document_id("councils", _source_key(entry),
                                                 ("councils", entry["council"], entry["council"])),
                _source_key(entry)))
        elif entry["group"] == "vatican-ii":
            docs.append(build_vatican2(entry, soup))
        else:
            raise ValueError(f"councils: no builder for {entry['council']}")
    return docs
