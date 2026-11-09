"""Which parts of a cleaned text a work publishes, one unit per passage.

A work's config may name its units. Without one, passages are whole paragraphs grouped to
about 350 words. With one, only the units go on: correction, the unrecognized-word rate
and the person's sample all see the text the adapter publishes, and nothing of the
editor's that surrounds it (1.2e). Each new kind of unit comes with the work that needs
it, as layouts do.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from ocr.words import is_known

_ROMAN_FOR_DIGIT = str.maketrans({"I": "1", "l": "1", "O": "0", "o": "0", "§": "5", "S": "5"})


@dataclass
class Unit:
    id: str
    paragraphs: list          # furniture.Paragraph, editor's labels taken off


class Units(Protocol):
    name: str

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = ()) -> list[Unit]:
        """The units of a work's paragraphs, in order. `series` gives the number of units
        in each series of a work printed in more than one; `closes` are patterns of the
        editor's paragraphs that carry no label. Raises when the text does not have the
        shape the work's config says."""


_LABELS = ("summary", "comment", "text", "canon")


def _label_like(word: str) -> str | None:
    """The label a misread word stands for ("Conrment", "Summar'y", "Sunmnary")."""
    key = re.sub(r"[^a-z]", "", word.lower())
    best = max(_LABELS, key=lambda lab: SequenceMatcher(None, key, lab).ratio())
    return best if len(key) >= 3 and SequenceMatcher(None, key, best).ratio() >= 0.6 else None


class SchroederCanons:
    """Schroeder's layout (`docs/research/council-translation-inventory.md`): "CANON N",
    "Summary." (his digest), "Text." (the translation), "Comment." (his commentary).

    "Text." is the mark to trust. The OCR loses a few headings (Lateran II's 24, Lateran
    IV's 67 and 71) and more summaries, but every canon has its "Text.", so a canon is
    numbered by counting them, and a heading that can be read must agree. A heading
    whose number holds a letter read as a digit ("CANON I10" for 10, "CANON II" for 11)
    is not trusted where it disagrees; the count, and the work's `unit_count`, decide. A council
    printed in two series (Lyons I, Vienne) restarts the count where the config's
    `series` says, and its unit ids carry the series.

    A paragraph is never let into a canon's text on doubt: one that opens with a misread
    label ("Conrment.") closes the canon, and one that opens with an unknown word and a
    stop raises, so a person looks."""
    name = "schroeder-canons"

    _NUMBER = r"([0-9IlOo§S]{1,3})"
    # A heading can share its paragraph with the summary after it, past a rule or a mark
    # read as "|".
    _HEADING = re.compile(r"^\W{0,2}CANON\s+" + _NUMBER + r"\.?(?:[\s|]+\W{0,2}\S{0,12}?\s*"
                          r"Su\S{3,6}[.,:]\s.*)?$", re.DOTALL)
    _SERIES = re.compile(r"(?i)^\W*second\s+series\W*$")
    _TEXT = re.compile(r"^\W{0,2}Text[.,:]\s+")
    # "Text." inside a paragraph: after a summary set on the same line.
    _TEXT_INSIDE = re.compile(r"(?<=[.:;!?”’)\]])\W{0,3}\s+\W{0,2}Text[.,:]\s+")
    # Editor's parts that close a canon's text.
    _CLOSE = re.compile(r"^\W{0,2}(?:Comment|Summary)[.,:]\s")
    # His citation of the decree in the Clementines, closing its text (Vienne): "(C. 1, in
    # Clem., De rescript., I, 2.)". Editor's matter (rule G).
    _CITATION = re.compile(r"\s*\(C\.\s?(?:\d+|un\.),?\s+in\s+C[il]em\.[^()]{0,80}\)\s*$")
    _FIRST_WORD = re.compile(r"^\W{0,2}([A-Za-z][A-Za-z'’]{1,11})[.,:]\s")

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = ()) -> list[Unit]:
        close_res = [re.compile(c) for c in closes]
        bounds = list(series or ())
        units: list[Unit] = []
        open_unit: Unit | None = None
        heading: int | None = None
        misread = False     # the heading's number holds a letter read as a digit
        in_series = 1
        number = 0

        def begin(para, body: str) -> Unit:
            nonlocal heading, misread, in_series, number
            if bounds and number == bounds[in_series - 1]:
                if in_series == len(bounds):
                    raise ValueError(f"more canons than the series {bounds} hold")
                in_series, number = in_series + 1, 0
            number += 1
            if heading is not None and heading != number and not misread:
                raise ValueError(f"canon heading {heading} where canon {number} "
                                 f"comes next" + (f" in series {in_series}" if bounds else ""))
            heading = None
            uid = f"series-{in_series}-canon-{number}" if bounds else f"canon-{number}"
            unit = Unit(uid, [_with_text(para, body)])
            units.append(unit)
            return unit

        for para in paragraphs:
            text = para.text
            m = self._HEADING.match(text)
            if m:
                open_unit = None
                heading = int(m.group(1).translate(_ROMAN_FOR_DIGIT))
                misread = not m.group(1).isdigit()
                continue
            if self._SERIES.match(text) or any(c.search(text) for c in close_res):
                open_unit = None
                continue
            if self._TEXT.match(text):
                open_unit = begin(para, self._TEXT.sub("", text, count=1))
                continue
            inside = self._TEXT_INSIDE.search(text)
            if inside:
                before = text[:inside.start()]
                if open_unit is not None and not (self._CLOSE.match(before)
                                                  or self._HEADING.match(before)):
                    raise ValueError(f"'Text.' inside a canon's text: {text[:80]!r}")
                open_unit = begin(para, text[inside.end():])
                continue
            if self._CLOSE.match(text):
                open_unit = None
                continue
            if open_unit is None:
                continue
            first = self._FIRST_WORD.match(text)
            if first and not is_known(first.group(1)):
                if _label_like(first.group(1)):
                    open_unit = None
                    continue
                if text[first.end(1)] == ",":     # "Quoniam, ut ait Apostolus"
                    open_unit.paragraphs.append(_with_text(para, text))
                    continue
                raise ValueError(f"a paragraph in {open_unit.id} opens with an unknown "
                                 f"word and a stop: {text[:80]!r}")
            open_unit.paragraphs.append(_with_text(para, text))
        if bounds and (in_series, number) != (len(bounds), bounds[-1]):
            raise ValueError(f"series {bounds}: read {number} canons in series {in_series}")
        for unit in units:
            last = unit.paragraphs[-1]
            unit.paragraphs[-1] = type(last)(self._CITATION.sub("", last.text), last.raw, last.leaves)
        return units


# A note call after punctuation, as the OCR reads a superscript: "arise.°", "Church.’®",
# "justice.**", "void.*?". It holds at least one mark no sentence ends with.
_NOTE_CALL = re.compile(r"(?<=[.,;:!?”)])['’”\"‘“]*[*°®¢™©]['’”\"‘“*°®¢™©?!]*(?=\s|$)")
# The same call read as a quotation mark or a question mark after a stop: "dignity.”",
# "benefices.’", "life.?°".
_QUOTE_CALL = re.compile(r"(?<=[.,;])[”’“‘](?=\s|$)")
_QUESTION_CALL = re.compile(r"(?<=[.,;])\?(?=\s|$)")
# Marks alone between spaces.
_LONE_MARK = re.compile(r"(?<=\s)[*°®¢™©|\\]+[?]?(?=\s|$)")


def strip_note_calls(text: str) -> str:
    """The text without the page-foot note calls the OCR read as marks. A quotation mark
    after a stop is a note call only where no quotation is open: Schroeder's notes are
    left out, and his quotations are kept."""
    text = _LONE_MARK.sub("", _NOTE_CALL.sub("", text))
    text = _QUESTION_CALL.sub("", text)
    out, last, opened = [], 0, 0
    for m in re.finditer(r"[“”]|(?<=[.,;])[’‘](?=\s|$)", text):
        mark = m.group(0)
        if mark == "“":
            opened += 1
        elif mark == "”" and opened:
            opened -= 1
        elif not opened and _QUOTE_CALL.match(text, m.start()):
            out.append(text[last:m.start()])
            last = m.end()
    out.append(text[last:])
    return re.sub(r" {2,}", " ", "".join(out)).strip()


# A closing single quotation mark: after a letter or stop, not between letters ("God’s").
_CLOSE_SINGLE = re.compile(r"(?<=\S)’(?![A-Za-z])")


def strip_stray_quotes(text: str) -> str:
    """The text without opening single quotation marks that nothing closes: specks the
    OCR read as "‘" before a word ("clear ‘proof", "ought ‘to be"). Schroeder's single
    quotations are always closed."""
    opens = [m.start() for m in re.finditer("‘", text)]
    closes = [m.start() for m in _CLOSE_SINGLE.finditer(text)]
    stray, stack = [], []
    for pos, kind in sorted([(o, "o") for o in opens] + [(c, "c") for c in closes]):
        if kind == "o":
            stack.append(pos)
        elif stack:
            stack.pop()
    stray = set(stack)
    out = "".join(ch for k, ch in enumerate(text) if k not in stray)
    return re.sub(r" {2,}", " ", out)


def _with_text(para, text: str):
    return type(para)(strip_stray_quotes(strip_note_calls(text)), para.raw, para.leaves)


UNITS: dict[str, Units] = {SchroederCanons.name: SchroederCanons()}


def get_units(name: str) -> Units:
    try:
        return UNITS[name]
    except KeyError:
        raise ValueError(f"no OCR units {name!r}; known: {', '.join(sorted(UNITS))}")
