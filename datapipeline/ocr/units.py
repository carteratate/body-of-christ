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
from typing import Protocol

_ROMAN_FOR_DIGIT = str.maketrans({"I": "1", "l": "1", "O": "0", "o": "0"})


@dataclass
class Unit:
    id: str
    paragraphs: list          # furniture.Paragraph, editor's labels taken off


class Units(Protocol):
    name: str

    def split(self, paragraphs: list) -> list[Unit]:
        """The units of a work's paragraphs, in order. Raises when the text does not
        have the shape the work's config says."""


class SchroederCanons:
    """Schroeder's layout (`docs/research/council-translation-inventory.md`): "CANON N",
    "Summary." (his digest), "Text." (the translation), "Comment." (his commentary).

    "Text." is the mark to trust. The OCR loses a few headings (Lateran II's 24, Lateran
    IV's 67 and 71) and more summaries, but every canon has its "Text.", so a canon is
    numbered by counting them, and a heading that can be read must agree."""
    name = "schroeder-canons"

    # A heading can share its paragraph with the summary after it.
    _HEADING = re.compile(r"^CANON\s+([0-9IlOo]{1,3})\.?(?:\s+Summary\b.*)?$", re.DOTALL)
    _TEXT = re.compile(r"^Text[.,:]\s+")
    # Editor's parts that close a canon's text.
    _CLOSE = re.compile(r"^(?:Comment|Summary)[.,:]\s")

    def split(self, paragraphs: list) -> list[Unit]:
        units: list[Unit] = []
        open_unit: Unit | None = None
        heading: int | None = None
        for para in paragraphs:
            m = self._HEADING.match(para.text)
            if m:
                open_unit = None
                heading = int(m.group(1).translate(_ROMAN_FOR_DIGIT))
                continue
            if self._CLOSE.match(para.text):
                open_unit = None
                continue
            if self._TEXT.match(para.text):
                number = len(units) + 1
                if heading is not None and heading != number:
                    raise ValueError(f"canon heading {heading} where canon {number} comes next")
                heading = None
                body = self._TEXT.sub("", para.text, count=1)
                open_unit = Unit(f"canon-{number}", [_with_text(para, body)])
                units.append(open_unit)
            elif open_unit is not None:
                open_unit.paragraphs.append(_with_text(para, para.text))
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


def _with_text(para, text: str):
    return type(para)(strip_note_calls(text), para.raw, para.leaves)


UNITS: dict[str, Units] = {SchroederCanons.name: SchroederCanons()}


def get_units(name: str) -> Units:
    try:
        return UNITS[name]
    except KeyError:
        raise ValueError(f"no OCR units {name!r}; known: {', '.join(sorted(UNITS))}")
