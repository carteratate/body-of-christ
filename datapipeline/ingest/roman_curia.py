"""Roman Curia (corpus-cleanup 5.3a, issue #202): the doctrinal documents of the Dicastery
for the Doctrine of the Faith, 1966 to 2026.

Source: each document's English page on vatican.va, vendored in `sources/roman-curia/`
with `manifest.json` (title, the office's name as the page prints it, year, the page's
own kind of document, URL). Built from the parked branch `feat/roman-curia-collection`,
whose tokenizer this keeps.

vatican.va pages for this office come in two shapes. Newer documents number their
paragraphs ("12. ..."); older ones and short responses do not. Both carry a language bar,
a title block in capitals, a signature block, and an endnote list at the foot.

The adapter keeps real paragraph numbers where the document has them and never invents
them where it does not. Unnumbered text is grouped by section heading into passages of
readable size. Endnotes are cut: bracketed note lists, runs of marked note lines, and a
plain-numbered tail that counts down to note 1.

Headings stay in the text of the passage they open and are marked (issue #445). A
document's headings fall into tiers: a Part or Chapter, then a roman-numbered section
("I. Liberation in the Old Testament"), then plain headings. Its highest tier opens the
reader's chapters (level 1); the tiers below are levels 2 and 3. A bare label printed on
its own line ("CHAPTER II", "Part One") pairs with the title after it.

Document facts (2.3): `genre` is the page's own kind in D5's Roman Curia values
(`GENRES`), the issuer is the office, `ddf`, under the name the page prints (the Sacred
Congregation until 1988, the Congregation until 5 June 2022, the Dicastery since; Carter,
26 Nov 2026), and the date is the one the page's dateline prints or, failing that, the
one in its address, which is often the day it was published. The AAS citation and the sentence recording the Pope's approval, where a page
prints them, are kept in the document's metadata (`aas`, `papal_approval`).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from dataclasses import replace
from datetime import date

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import headings  # noqa: E402
from config import settings  # noqa: E402
from identity import anchor as make_anchor  # noqa: E402
from ingest.common import split_display_passage  # noqa: E402
from ingest.pieces import piece_reference  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.boilerplate import strip_boilerplate  # noqa: E402
from normalize.caps import smart_title_case  # noqa: E402
from normalize.footnotes import strip_footnote_markers  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from registry import ANCHOR_SCHEME, resolve_document_id  # noqa: E402

COLLECTION = "roman-curia"
ISSUER = "ddf"
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "sources", COLLECTION)

# The page's kind of document (the manifest's `genre`) in D5's Roman Curia values
# (`registry.genres.CURIA_GENRES`), `letter` for a letter, and `other` for the rest.
GENRES = {
    "Declaration": "declaration", "Instruction": "instruction",
    "Doctrinal Note": "doctrinal-note", "Note": "note",
    "Response": "response", "Responses": "response", "Responsum": "response",
    "Norms": "norms", "Considerations": "considerations",
    "Doctrinal Commentary": "commentary", "Letter": "letter",
    "Clarification": "other", "Study": "other",
}
# The address's date: year first ("_19660724_"), or, on a few older pages, day first
# ("_28051992_").
_URL_DATE = re.compile(r"_((?:19|20)\d{2})(\d{2})(\d{2})(?:_|\b)")
_URL_DATE_DMY = re.compile(r"_(\d{2})(\d{2})((?:19|20)\d{2})(?:_|\b)")
_AAS = re.compile(r"\bAAS\s+\d+\s*\(\d{4}\)[^.;]*")
# The approval formula: "The Sovereign Pontiff John Paul II, in the Audience granted to
# the undersigned Prefect, approved this Declaration ... and ordered its publication."
_APPROVAL = re.compile(
    r"(?:Supreme|Sovereign|Roman) Pontiff|Holy Father|Pope [A-Z][a-z]+ [IVXL]+",
)
_APPROVED = re.compile(r"\b(?:approved|confirmed|ratified|gave (?:his )?(?:approval|assent))\b")
_AUDIENCE = re.compile(r"\b[Aa]udience\b")

# Pages that print other texts ahead of the document itself. Each entry names the last
# line before the document starts; everything up to and including it is skipped.
# The Professio fidei commentary page opens with the Profession of Faith, the Oath of
# Fidelity, and John Paul II's motu proprio Ad Tuendam Fidem, which are not the
# commentary and are not all this office's.
_START_AFTER = {
    "doctrinal-commentary-on-the-concluding-formula-of-the-professio-fidei": "***",
}

_NUM = re.compile(r"^(\d{1,3})\s*\.\s+(\S.*)", re.DOTALL)
# An endnote line: "[3] ...", "(3) ...", "3. ...", "3) ...", or bare "3 Cf. ...".
_NOTE = re.compile(r"^(?:\[(\d{1,3})\]|\((\d{1,3})\)|(\d{1,3})\s*[.)]|(\d{1,3})\s+(?=[A-Z“\"(*]))\s*\S")
_ACTA_NOTE = re.compile(r"^[A-Z]\)\s*\[In\b")
_BRACKET_NOTE = re.compile(r"^[\[(]\s*\d{1,3}\s*[\])]\s*\S")
_MARKER_ONLY = re.compile(r"^[\[(]?\s*\d{1,3}\s*[\])]?\.?$")
# Inline note markers that survive as text: "(12)" after a word, and "[12]".
_INLINE_MARKER = re.compile(r"(?<=[\w.,;:?!”\"»’')\]])\s?(?:\(\d{1,3}\)|\[\d{1,3}\])")
# Source lines: "* AAS 82 (1990) 362-379.", "* L'Osservatore Romano, English Edition ...".
_SOURCE_LINE = re.compile(r"^\*\s*(?:AAS\s+\d|OR\s+\d|L['’]Osservatore)")
_LANG_BAR = re.compile(r"^\[\s*(?:[A-Z]{2}(?:_[A-Z]{2})?\s*-\s*)*[A-Z]{2}(?:_[A-Z]{2})?\s*\]$")
_ROMAN = re.compile(r"^[IVXLC]{1,6}\.?$")
# A line of asterisks between parts of the text ("* * *"): neither text nor a heading.
_SEPARATOR = re.compile(r"^[*\s]+$")
_ROMAN_TITLE = re.compile(r"^[IVXLC]{1,6}\.\s+\S")
_ROMAN_PREFIX = re.compile(r"^([IVXLC]{1,6})\b")
_NOTES_HEADING = re.compile(r"^(?:END)?NOTES?$|^FOOTNOTES?$", re.IGNORECASE)
_SIGNATURE = re.compile(r"\b(?:Prefect|Secretary|Under-?Secretary|Prefetto|Segretario)\b")
_PAPAL_SIGNATURE = re.compile(r"\bP[Pp]\.\s?[IVXL]+\b")
_DATELINE = re.compile(r"^(?:Given (?:at|in) |Rome, |From the Offices?|Vatican City|Vatican, |From the Vatican)")
_OPENER = re.compile(r"^(?:Presentation|Introduction|Preface|Foreword|Premise|Prologue)$", re.IGNORECASE)
_TOC = re.compile(r"^(?:table of )?contents$|^index$", re.IGNORECASE)
_ORDINAL = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
# A question heading opens a section; the answer heading does not, so each question
# stays in one passage with its answer.
_QUESTION_HEADING = re.compile(rf"^(?:{_ORDINAL}\s+)?(?:question|dubium)(?:\s+\d+)?\s*[.:]?$", re.IGNORECASE)
_ANSWER_HEADING = re.compile(r"^(?:response|reply|answer|responsum)\s*[.:]?$", re.IGNORECASE)
_SENTENCE_END = (".", ":", ";", "?", "!", "”", '"', "»", ")")
_ENGLISH = frozenset("the of and to in is that a for it with as be by this which on not are or "
                     "his from their has have was an they we our its".split())
# Unnumbered text is grouped into passages of about this size before the display split.
_GROUP_TARGET = 1200
# An unnumbered paragraph shorter than this ("R. Negative.", "Sincerely yours in Christ,")
# is joined to the paragraph before it rather than standing alone.
_MIN_PARAGRAPH = 40


def _is_english(text: str) -> bool:
    """False for a paragraph in Latin or Italian (an untranslated note or source line)."""
    words = re.findall(r"[a-z’']+", text.lower())
    if len(words) < 8:
        return True
    return sum(w in _ENGLISH for w in words) / len(words) >= 0.12


def _texts(soup, start_after: str | None = None) -> list[tuple[object, str]]:
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    for sup in soup.find_all("sup"):
        m = re.fullmatch(r"\s*[\[(]?(\d{1,3})[\])]?\s*", sup.get_text())
        if not m:
            continue
        if _opens_paragraph(sup):
            # An endnote's own number ("<sup>6</sup> Vatican Council II, ..."): kept as
            # "[6]" so cut_notes knows the line for a note.
            sup.replace_with(f"[{m[1]}] ")
        else:
            sup.decompose()  # a note caller; left in, it reads as a stray number
    out = []
    for p in soup.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        if t and not _LANG_BAR.match(t) and not _SOURCE_LINE.match(t) \
                and not _MARKER_ONLY.match(t) \
                and (t == start_after or not _SEPARATOR.match(t)):
            out.append((p, t))
    if start_after:
        idx = [i for i, (_, t) in enumerate(out) if t == start_after]
        if idx:
            out = out[idx[-1] + 1:]
    return out


def _opens_paragraph(tag) -> bool:
    """Whether `tag` is the first text of its paragraph."""
    p = tag.find_parent("p")
    if p is None:
        return False
    for node in p.descendants:
        if node is tag:
            return True
        if isinstance(node, str) and node.strip():
            return False
    return False


def _note_number(text: str) -> int | None:
    m = _NOTE.match(text)
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def cut_notes(lines: list[str]) -> list[str]:
    """Drop endnotes: a Notes heading, runs of marked note lines, or a numbered tail.

    The numbered tail is found walking back from the end: numbered lines must descend
    by one, and unnumbered lines are continuations of the note above them. The cut
    happens only when the walk reaches note 1, so a document whose body paragraphs are
    numbered keeps them.
    """
    for i, t in enumerate(lines):
        # Lettered source notes ("A) [In Nr. 1 ...: Act Syn III/II ...]") quote the
        # Council's Latin acts and close the page.
        if _ACTA_NOTE.match(t):
            lines = lines[:i]
            break
    for i, t in enumerate(lines):
        # "Note" is also a genre heading at the top of a page, so a Notes heading counts
        # only when note 1 follows it.
        if _NOTES_HEADING.match(t) and i + 1 < len(lines) and _note_number(lines[i + 1]) == 1:
            return lines[:i]
    # A note block in the middle of a page (a second document's notes, or a
    # presentation's) is a run of three or more marked lines.
    runs, i = [], 0
    while i < len(lines):
        j = i
        while j < len(lines) and _BRACKET_NOTE.match(lines[j]):
            j += 1
        if j - i >= 3:
            runs.append((i, j))
        i = max(j, i + 1)
    for a, b in reversed(runs):
        lines = lines[:a] + lines[b:]
    # Bracketed markers ("[12] ...") never open a body paragraph, so they settle it: cut
    # at the first one whose tail is mostly notes (note 1 is sometimes fused into the
    # paragraph before it), and drop any stray bracketed note lines.
    for i, t in enumerate(lines):
        if _BRACKET_NOTE.match(t):
            tail = lines[i:]
            if sum(1 for x in tail if _BRACKET_NOTE.match(x)) / len(tail) >= 0.6:
                return [x for x in lines[:i] if not _BRACKET_NOTE.match(x)]
    expected = None
    for i in range(len(lines) - 1, -1, -1):
        n = _note_number(lines[i])
        if n is None:
            continue  # a note running over more than one paragraph
        if expected is not None and n != expected:
            return lines
        if n > 1:
            expected = n - 1
            continue
        # Reached note 1. A body that numbers its own paragraphs 1..N also counts down to
        # 1, so cut only when this tail looks like notes: bracketed markers, or short
        # entries after a body longer than the tail.
        tail, body = lines[i:], lines[:i]
        bracketed = lines[i].lstrip().startswith("[")
        short = sum(len(t) for t in tail) / len(tail) < 500
        longer_body = sum(len(t) for t in body) > sum(len(t) for t in tail)
        return body if bracketed or (short and longer_body) else lines
    return lines


def _is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def _is_heading(text: str) -> bool:
    """A heading line, including one that ends in a closing bracket or quotation mark
    ("Intracytoplasmic sperm injection (ICSI)", 'The "Poor of Yahweh"'), which the
    passage-headings classifier also takes for one."""
    return (len(text) <= 120 and not text.endswith(_SENTENCE_END + (",",))) \
        or headings.looks_like_heading(text)


def _numbered_heading(rest: str) -> bool:
    """ "1. A Growing Awareness of Human Dignity": a numbered section title, not a paragraph."""
    return (len(rest) <= 100 and not rest.endswith(_SENTENCE_END + (",",))) \
        or (len(rest) <= 100 and headings.looks_like_heading(rest))


def _drop_contents(items: list[tuple[object, str]]) -> list[tuple[object, str]]:
    """Remove a table of contents: its entries repeat as headings further down."""
    for i, (_, t) in enumerate(items):
        if _TOC.match(t) and i + 1 < len(items):
            first = items[i + 1][1]
            for j in range(i + 2, len(items)):
                if items[j][1] == first:
                    return items[:i] + items[j:]
            return items
    return items


def _is_signature(t: str) -> bool:
    if len(t) >= 140 or t.endswith("."):
        return False
    return bool(_SIGNATURE.search(t)) or (len(t) < 80 and bool(_PAPAL_SIGNATURE.search(t)))


def tokens(soup, start_after: str | None = None) -> list[tuple[str, int | None, str]]:
    """Return ("title"|"section"|"numhead"|"para", number, text) tokens for one page;
    a "numhead" is a numbered unit's heading line, its number the unit's.

    Before the first sentence of body text, lines are the title block (office name,
    genre, title, subtitle) and are dropped: the manifest carries the title.
    """
    items = _texts(soup, start_after)
    keep = cut_notes([t for _, t in items])
    kept, j = [], 0
    for p, t in items:  # keep is an order-preserving subsequence of the texts
        if j < len(keep) and t == keep[j]:
            kept.append((p, t))
            j += 1
    lines = [_INLINE_MARKER.sub("", t).strip() for _, t in _drop_contents(kept)]
    lines = [t for t in lines if t and not _is_signature(t) and _is_english(t)]
    toks: list[tuple[str, int | None, str]] = []
    body_started = False
    answer_next = False
    last_number = 0
    section_since_number = False
    for t in lines:
        m = _NUM.match(t)
        rest = m.group(2).strip() if m else ""
        heading_like = m is not None and (_numbered_heading(rest) or _is_shouting(rest))
        # Numbering that starts over under a new section (Donum Vitae's Part II).
        restart = m is not None and int(m.group(1)) == 1 and section_since_number
        if heading_like and (int(m.group(1)) == last_number + 1 or restart):
            # A numbered heading that continues the paragraph numbering opens that
            # numbered unit ("2. IS PRENATAL DIAGNOSIS MORALLY LICIT?", Donum Vitae): the
            # unit keeps its number, and the line is its heading.
            body_started = True
            last_number = int(m.group(1))
            toks.append(("numhead", last_number, rest))
            section_since_number = False
        elif heading_like and body_started:
            toks.append(("section", None, t))
            section_since_number = True
        elif m:
            body_started = True
            last_number = int(m.group(1))
            section_since_number = False
            toks.append(("para", last_number, rest))
        elif _ROMAN.match(t) or (_ROMAN_TITLE.match(t) and len(t) <= 120):
            toks.append(("section", None, t))
            section_since_number = True
        elif _DATELINE.match(t) and len(t) < 250:
            if toks and toks[-1][0] == "para":
                k, n, prev = toks[-1]
                toks[-1] = (k, n, prev + "\n\n" + t)  # the closing dateline stays with the text
        elif _ANSWER_HEADING.match(t):
            answer_next = True
        elif _QUESTION_HEADING.match(t):
            toks.append(("section", None, t))
            section_since_number = True
        elif not body_started and (_is_shouting(t) or not t.endswith(_SENTENCE_END)):
            toks.append(("title", None, t))
        elif _is_heading(t):
            toks.append(("section", None, t))
            section_since_number = True
        else:
            body_started = True
            if answer_next:
                t, answer_next = f"Response: {t}", False
            if len(t) < _MIN_PARAGRAPH and not t.endswith("?") and toks and toks[-1][0] == "para":
                k, n, prev = toks[-1]
                toks[-1] = (k, n, prev + "\n\n" + t)
            else:
                toks.append(("para", None, t))
    # An opening heading directly after the title block (Presentation, Introduction) is
    # a section.
    for i, (k, n, t) in enumerate(toks):
        if k == "para":
            if i and toks[i - 1][0] == "title" and _OPENER.match(toks[i - 1][2]):
                toks[i - 1] = ("section", None, toks[i - 1][2])
            break
    return toks


_ENUMERATOR = re.compile(
    r"^((?:(?:Part|Chapter)\s+[IVXLC0-9]+\.?\s+|(?:[IVXLC]{1,6}|\d{1,3})\s*\.\s*"
    r"|[IVXLC]{1,6}\s+))([a-z])")
_TITLE_CASED_ROMAN = re.compile(r"\b[IVXLC][ivxlc]*\b")
_VALID_ROMAN = re.compile(r"^(?=[IVXLC])C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")


def _section_label(text: str) -> str:
    """A heading as a chapter label, title-cased, with its Roman numerals in capitals
    ("Chapter II", not "Chapter Ii") and its first word capitalized after a numeral
    ("I. The Nature of Marriage", not "I. the Nature")."""
    label = smart_title_case(clean_text(text))
    label = _TITLE_CASED_ROMAN.sub(
        lambda m: m[0].upper() if _VALID_ROMAN.match(m[0].upper()) else m[0], label)
    return _ENUMERATOR.sub(lambda m: m[1] + m[2].upper(), label)


def _restarts(toks: list[tuple[str, int | None, str]]) -> bool:
    """True when paragraph numbering starts over in a later part (Libertatis Nuntius)."""
    last = 0
    for k, n, _ in toks:
        if k in ("para", "numhead") and n is not None:
            if n <= last:
                return True
            last = n
    return False



# --------------------------------------------------------------------------- facts

_MONTHS = ("January February March April May June July August September October "
           "November December").split()
_MONTH = "(" + "|".join(_MONTHS) + ")"
_DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+{_MONTH},?\s+((?:19|20)\d\d)\b")
_MONTH_DAY_YEAR = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}}),?\s+((?:19|20)\d\d)\b")


def dateline_date(lines: list[str]) -> date | None:
    """The date of the page's last dateline that prints a whole date ("Rome, from the
    Offices of the Congregation ..., September 8, 2008"), or None."""
    for line in reversed(lines):
        if not (_DATELINE.match(line) and len(line) < 250):
            continue
        m = _DAY_MONTH_YEAR.search(line)
        if m:
            return date(int(m[3]), _MONTHS.index(m[2]) + 1, int(m[1]))
        m = _MONTH_DAY_YEAR.search(line)
        if m:
            return date(int(m[3]), _MONTHS.index(m[1]) + 1, int(m[2]))
    return None


def document_date(entry: dict, lines: list[str] = ()) -> date | None:
    """The date the document carries: its dateline, else the date in its address (often
    the day it was published)."""
    printed = dateline_date(list(lines))
    if printed:
        return printed
    m = _URL_DATE.search(entry["url"])
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = _URL_DATE_DMY.search(entry["url"])
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def date_display(day: date | None) -> str | None:
    return f"{day.day} {day:%B} {day.year}" if day else None


# Pages whose own heading names another kind than the manifest's: A Journey of Hope
# prints "Note".
KINDS = {"a-journey-of-hope": "Note"}


def genre(entry: dict) -> str:
    return GENRES[KINDS.get(entry["slug"], entry["genre"])]


_OFFICE = re.compile(
    r"(sacred\s+)?congregation\s+for\s+the\s+doctrine\s+of\s+the\s+faith"
    r"|(dicastery\s+for\s+the\s+doctrine\s+of\s+the\s+faith|dicasterium\s+pro\s+doctrina\s+fidei)",
    re.IGNORECASE)


def printed_office(lines: list[str]) -> str | None:
    """The office's name as the page's title block prints it, in English, or None."""
    for line in lines[:8]:
        m = _OFFICE.search(line)
        if m and len(line) < 80:
            if m[2]:
                return "Dicastery for the Doctrine of the Faith"
            return ("Sacred " if m[1] else "") + "Congregation for the Doctrine of the Faith"
    return None


def _source_facts(soup) -> dict:
    """The AAS citation and the papal approval sentence a page prints, where it does."""
    out: dict = {}
    for p in soup.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if "aas" not in out and text.startswith("*"):
            m = _AAS.search(text)
            if m:
                out["aas"] = m.group(0).strip()
        if "papal_approval" not in out and _APPROVED.search(text) and _APPROVAL.search(text):
            for sentence in re.split(r"(?<=[.;])\s+", text):
                if _APPROVED.search(sentence) and _APPROVAL.search(sentence) \
                        and _AUDIENCE.search(sentence) and len(sentence) < 500:
                    out["papal_approval"] = clean_text(sentence)
                    break
    return out


# --------------------------------------------------------------------------- headings

_DIVISION_HEAD = re.compile(r"^(?:part|chapter)\b", re.IGNORECASE)
_BARE_LABEL = re.compile(
    r"^(?:(?:part|chapter)\s+(?:[0-9]+|[IVXLC]+|one|two|three|four|five|six)\.?|[IVXLC]{1,6}\.?)$",
    re.IGNORECASE)
# "I. The Nature of Marriage", "1. The text", and a numeral printed without its point
# before a title in capitals ("I AN INSPIRATION", Libertatis Nuntius).
_SECTION_HEAD = re.compile(
    r"^(?:[IVXLC]{1,6}\s*\.|[IVXLC]{1,6}\s+(?=[A-Z](?:[A-Z]|\s+[A-Z]))|\d{1,2}\.)\s*\S")
_FRAME = re.compile(r"^(?:introduction|conclusion|presentation|preface|foreword|premise|"
                    r"prologue|epilogue)\b", re.IGNORECASE)


def _tier(text: str) -> int:
    """0 for a Part or Chapter, 1 for a numbered section, 2 for any other heading."""
    if _DIVISION_HEAD.match(text):
        return 0
    if _SECTION_HEAD.match(text) or _ROMAN.match(text):
        return 1
    return 2


def heading_levels(runs: list[list[str]]) -> list[list[tuple[int, bool]]]:
    """(level, pairs_next) for each heading of one document, given its headings as runs
    printed one straight after another. The tiers the document uses become levels 1 to
    3, and an Introduction or Conclusion takes level 1. A bare label with another heading
    straight after it pairs with that heading at its level, and a heading straight under
    another never skips a level (1 then 3 becomes 1 then 2)."""
    used = sorted({_tier(t) for run in runs for t in run})
    out = []
    for run in runs:
        # A pair reads as one heading: the bare label takes its title's place.
        groups: list[list[str]] = []
        k = 0
        while k < len(run):
            pair = bool(_BARE_LABEL.match(run[k])) and k + 1 < len(run)
            groups.append(run[k:k + 2] if pair else [run[k]])
            k += 2 if pair else 1
        raw = [1 if _FRAME.match(g[0]) else min(3, min(used.index(_tier(t)) for t in g) + 1)
               for g in groups]
        # A heading printed above another is never deeper than it ("The Council on the
        # Devil" over "1. The text"), only the first level-1 heading of a stack opens a
        # chapter, and no heading skips a level under the one above it.
        for i in range(len(raw) - 2, -1, -1):
            raw[i] = min(raw[i], raw[i + 1])
        levels: list[tuple[int, bool]] = []
        seen_top = False
        for g, level in zip(groups, raw):
            if level == 1 and seen_top:
                level = 2
            seen_top = seen_top or level == 1
            if levels:
                level = min(level, levels[-1][0] + 1)
            levels.extend([(level, True), (level, False)] if len(g) == 2 else [(level, False)])
        out.append(levels)
    return out


# --------------------------------------------------------------------------- the build

def build_document(entry: dict, source_dir: str | None = None) -> Document:
    slug, title = entry["slug"], entry["title"]
    with open(os.path.join(source_dir or _SRC, entry["file"]), "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    facts = _source_facts(BeautifulSoup(str(soup), "lxml"))
    lines = [t for _, t in _texts(BeautifulSoup(str(soup), "lxml"), _START_AFTER.get(slug))]
    toks = tokens(soup, _START_AFTER.get(slug))
    source_key = f"{COLLECTION}/{entry['file']}"
    did = resolve_document_id(COLLECTION, source_key, (COLLECTION, slug))
    day = document_date(entry, lines)
    office = printed_office(lines) or entry["author"]
    # Where numbering restarts by part, a bare "§3" is ambiguous, so each number is
    # qualified by its part: "VIII, 3", the form the document itself is cited by.
    qualify = _restarts(toks)

    # Each heading's level and pairing, from the runs of headings printed together.
    runs: list[list[str]] = []
    previous = None
    for k, _, t in toks:
        if k == "section":
            if previous != "section":
                runs.append([])
            runs[-1].append(clean_text(t))
        if k != "title":
            previous = k
    levels = iter([lv for run in heading_levels(runs) for lv in run])

    passages: list[Passage] = []
    seen: set[str] = set()

    def emit(text: headings.MarkedText, ref: str, base: str, ckey: str, clabel: str,
             unit: str | None) -> None:
        content = text.text
        if not content:
            return
        pieces = split_display_passage(content, settings.MAX_PASSAGE_CHARS)
        pieces = headings.hold_headings(content, pieces, text.marks)
        for j, (piece, marks) in enumerate(zip(
                pieces, headings.split_marks(content, pieces, text.marks))):
            anc = base + (f"/p{j + 1}" if len(pieces) > 1 else "")
            k = 1
            while anc in seen:
                k += 1
                anc = f"{base}-{k}" + (f"/p{j + 1}" if len(pieces) > 1 else "")
            seen.add(anc)
            passages.append(Passage(content=piece, reference=ref, anchor=anc,
                                    chapter_key=ckey, chapter_label=clabel,
                                    position=len(passages), unit_label=unit,
                                    metadata=headings.with_headings(None, marks)))

    def cleaned(text: str) -> str:
        return clean_text(strip_footnote_markers(strip_boilerplate(text)))

    sec_ord = 0
    # Text before the first heading is the document's opening, under its own title.
    ckey, clabel = make_anchor(slug, "sec-0"), title
    pending: list[headings.Heading] = []   # headings held for the next passage
    group: list[str] = []
    group_ord = 0
    cur_num: int | None = None
    cur_parts: list[str] = []

    def opened() -> headings.MarkedText:
        out = headings.MarkedText()
        for held in pending:
            out.add(held)
        pending.clear()
        return out

    def part_name() -> str:
        if sec_ord == 0:
            return "Introduction"
        m = _ROMAN_PREFIX.match(clabel)
        return m.group(1) if m else (clabel if len(clabel) <= 30 else f"Part {sec_ord}")

    def flush_group() -> None:
        nonlocal group, group_ord
        if group:
            group_ord += 1
            base = make_anchor(slug, f"sec-{sec_ord}", f"part-{group_ord}")
            ref = title if clabel == title else f"{title}, {clabel}"
            text = opened()
            for g in group:
                text.paragraph(cleaned(g))
            emit(text, ref, base, ckey, clabel, None)
            group = []

    def flush_num() -> None:
        nonlocal cur_num, cur_parts
        if cur_num is not None:
            if qualify:
                unit = f"{part_name()}, {cur_num}"
                base = make_anchor(slug, f"sec-{sec_ord}", cur_num)
            else:
                unit, base = f"§{cur_num}", make_anchor(slug, cur_num)
            text = opened()
            for part in cur_parts:
                text.paragraph(cleaned(part))
            emit(text, f"{title}, {unit}", base, ckey, clabel, unit)
        cur_num, cur_parts = None, []

    # A level-1 heading opens a chapter; a pair's title joins its label to the chapter's.
    pair_open = False
    section_level = 1
    for kind, n, raw in toks:
        if kind == "title":
            continue
        if kind == "numhead":
            # A numbered unit opened by its heading, one level below the section it is in.
            flush_group()
            flush_num()
            pair_open = False
            pending.append(headings.Heading(clean_text(raw), level=min(3, section_level + 1)))
            cur_num, cur_parts = n, []
            continue
        if kind == "section":
            flush_num()
            flush_group()
            text = clean_text(raw)
            level, pairs_next = next(levels)
            section_level = level
            if level == 1:
                if pair_open:
                    clabel = f"{clabel}: {_section_label(text)}"
                else:
                    sec_ord += 1
                    ckey, clabel = make_anchor(slug, f"sec-{sec_ord}"), _section_label(text)
                    group_ord = 0
            # A level-1 heading (a pair's first line) repeats its chapter's label; the
            # reader hides it there.
            pending.append(headings.Heading(
                text, level=level, pairs_next=pairs_next,
                chapter_title=level == 1 and not pair_open))
            pair_open = pairs_next
            continue
        pair_open = False
        if n is not None:
            flush_group()
            flush_num()
            cur_num, cur_parts = n, [raw]
        elif cur_num is not None:
            cur_parts.append(raw)  # an unnumbered paragraph continues the numbered one
        else:
            group.append(raw)
            if sum(len(g) for g in group) >= _GROUP_TARGET:
                flush_group()
    flush_num()
    flush_group()

    # Passages that would share a citation (a section's grouped text, a long paragraph's
    # pieces) are cited in turn, "(part 2 of 3)", as the other adapters do (1.10c).
    shared = {ref: n for ref, n in Counter(p.reference for p in passages).items() if n > 1}
    seen_ref: Counter = Counter()
    for i, p in enumerate(passages):
        if p.reference in shared:
            seen_ref[p.reference] += 1
            passages[i] = replace(p, reference=piece_reference(
                p.reference, None, None, seen_ref[p.reference], shared[p.reference]))

    metadata = {"source": "vatican.va (English)", "source_key": source_key,
                "source_file": entry["file"], "url": entry["url"],
                "anchor_scheme": ANCHOR_SCHEME, "genre": genre(entry),
                "issuer_label": office, **facts}
    return Document(id=did, collection=COLLECTION, title=title, author=office,
                    year=day.year if day else entry["year"], metadata=metadata,
                    passages=passages, date_display=date_display(day))


def manifest(source_dir: str | None = None) -> list[dict]:
    with open(os.path.join(source_dir or _SRC, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def build_documents(source_dir: str | None = None) -> list[Document]:
    return [build_document(e, source_dir) for e in manifest(source_dir)]
