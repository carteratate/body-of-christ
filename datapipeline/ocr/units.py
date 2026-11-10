"""Which parts of a cleaned text a work publishes, one unit per passage.

A work's config may name its units. Without one, passages are whole paragraphs grouped to
about 350 words. With one, only the units go on: correction, the unrecognized-word rate
and the person's sample all see the text the adapter publishes, and nothing of the
editor's that surrounds it (1.2e). Each new kind of unit comes with the work that needs
it, as layouts do.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
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
              closes: tuple[str, ...] = (), bounds: tuple[dict, ...] = ()) -> list[Unit]:
        """The units of a work's paragraphs, in order. `series` gives the number of units
        in each series of a work printed in more than one; `closes` are patterns of the
        editor's paragraphs that carry no label; `bounds` are the texts a work takes from
        pages that print others. Raises when the text does not have the shape the work's
        config says."""


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
    # "Comment." inside a paragraph, after a sentence end: the clean-up missed the break
    # before it (Constantinople IV canon 17, p. 171). The canon ends there.
    _CLOSE_INSIDE = re.compile(r"(?<=[.:;!?”’)\]])\W{0,3}\s+\W{0,2}Comment[.,:]\s+(?=[A-Z])")
    # His citation of the decree in the Clementines, closing its text (Vienne): "(C. 1, in
    # Clem., De rescript., I, 2.)". Editor's matter (rule G).
    _CITATION = re.compile(r"\s*\(C\.\s?(?:\d+|un\.),?\s+in\s+C[il]em\.[^()]{0,80}\)\s*$")
    _FIRST_WORD = re.compile(r"^\W{0,2}([A-Za-z][A-Za-z'’]{1,11})[.,:]\s")

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = (), bounds: tuple[dict, ...] = ()) -> list[Unit]:
        if bounds:
            raise ValueError("Schroeder's canons are found by their labels, not by bounds")
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
            closed = self._CLOSE_INSIDE.search(body)
            unit = Unit(uid, [_with_text(para, body[:closed.start()] if closed else body)])
            units.append(unit)
            return None if closed else unit

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
            inside = self._CLOSE_INSIDE.search(text)
            if inside:
                open_unit.paragraphs.append(_with_text(para, text[:inside.start()]))
                open_unit = None
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
            unit.paragraphs[-1] = replace(last, text=self._CITATION.sub("", last.text))
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
    return replace(para, text=strip_stray_quotes(strip_note_calls(text)))


class Bounded:
    """Texts a work takes from pages that print other matter around them, each named by
    its first and last paragraph: Giles's Matthew Paris prints the deposition bull and
    Lyons I's decrees inside his chronicle (1.2e). A bound is `{"id", "first", "last"}`,
    `first` and `last` patterns searched in the paragraphs' text; the text runs from the
    first paragraph `first` matches to the next one `last` matches, inclusive.

    A text longer than a passage is cut, between paragraphs, into passages of about
    `PASSAGE_WORDS` (`<id>-01`, `<id>-02`, ...), so correction and the person's check see
    a few pages at a time; a work's `max_paragraph_words` keeps its paragraphs short
    enough for that. Double quotation marks are taken out: Giles quotes the whole
    document, opening each of its paragraphs with one, and its own quotations are single."""
    name = "bounded"

    _DOUBLE_QUOTES = re.compile(r"\s?[\"“”]\s?")

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = (), bounds: tuple[dict, ...] = ()) -> list[Unit]:
        from ocr.work import PASSAGE_WORDS, group_passages

        if series or closes or not bounds:
            raise ValueError("bounded units take bounds, and no series or closes")
        units: list[Unit] = []
        after = 0
        for bound in bounds:
            first = next((k for k in range(after, len(paragraphs))
                          if re.search(bound["first"], paragraphs[k].text)), None)
            if first is None:
                raise ValueError(f"{bound['id']}: no paragraph after the last text opens "
                                 f"with {bound['first']!r}")
            last = next((k for k in range(first, len(paragraphs))
                         if re.search(bound["last"], paragraphs[k].text)), None)
            if last is None:
                raise ValueError(f"{bound['id']}: no paragraph closes it with {bound['last']!r}")
            if paragraphs[first].continues:
                raise ValueError(f"{bound['id']}: opens inside a paragraph")
            text = [replace(p, text=self._unquoted(p.text)) for p in paragraphs[first:last + 1]]
            groups = group_passages(text, PASSAGE_WORDS)
            units.extend(Unit(bound["id"] if len(groups) == 1 else f"{bound['id']}-{k:02d}", g)
                         for k, g in enumerate(groups, 1))
            after = last + 1
        return units

    def _unquoted(self, text: str) -> str:
        def mend(m: re.Match) -> str:
            before, after = m.string[:m.start()], m.string[m.end():]
            return "" if not before or not after else " "
        text = self._DOUBLE_QUOTES.sub(mend, text)
        return re.sub(r" {2,}", " ", text).strip()


class Headed:
    """Texts a work names in its config, in the order printed, where the print gives no
    label every text shares: Schroeder's numbered decrees of Constance and Basel, Lateran
    V's bulls ("From the bull …"), Deferrari's extracts (1.2e). A bound is
    `{"id", "first", "last"?, "heading"?}`: `first` is searched in the paragraph that
    opens the text, after the last text's end; the text runs to the paragraph `last`
    matches, or, without `last`, to the paragraph before the next text's `first`. The
    last text needs `last`. `heading` is the editor's heading the opening paragraph
    starts with, taken off ("From the bull … (session …):", "Can. 3."); a paragraph that
    holds only the heading goes.

    Nothing between a text's opening and its end is let out but a bare number set as a
    heading ("4") where it ends the text: the next decree's number. A bare number
    anywhere else, or a paragraph a work's `closes` patterns match (a heading no bound
    names), raises, so a person looks. A text longer than a passage is cut into passages
    of about `PASSAGE_WORDS`, `<id>-01`, `<id>-02`, ..., as `Bounded` does."""
    name = "headed"

    _BARE_NUMBER = re.compile(r"^\W{0,2}[0-9IlOo]{1,2}\W{0,2}$")

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = (), bounds: tuple[dict, ...] = ()) -> list[Unit]:
        from ocr.work import PASSAGE_WORDS, group_passages

        if series or not bounds:
            raise ValueError(f"{self.name} units take bounds, and no series")
        if "last" not in bounds[-1]:
            raise ValueError(f"{bounds[-1]['id']}: the last text needs `last`")
        close_res = [re.compile(c) for c in closes]
        starts, after = [], 0
        for bound in bounds:
            k = next((k for k in range(after, len(paragraphs))
                      if re.search(bound["first"], paragraphs[k].text)), None)
            if k is None:
                raise ValueError(f"{bound['id']}: no paragraph after the last text opens "
                                 f"with {bound['first']!r}")
            if paragraphs[k].continues:
                raise ValueError(f"{bound['id']}: opens inside a paragraph")
            starts.append(k)
            after = k + 1
        units: list[Unit] = []
        for i, (bound, start) in enumerate(zip(bounds, starts)):
            end = starts[i + 1] if i + 1 < len(starts) else len(paragraphs)
            if "last" in bound:
                last = next((j for j in range(start, end)
                             if re.search(bound["last"], paragraphs[j].text)), None)
                if last is None:
                    raise ValueError(f"{bound['id']}: no paragraph before the next text "
                                     f"closes it with {bound['last']!r}")
                end = last + 1
            body = list(paragraphs[start:end])
            while body and self._BARE_NUMBER.match(body[-1].text):
                body.pop()
            if bound.get("heading"):
                opening = re.sub(bound["heading"], "", body[0].text, count=1).strip()
                if opening == body[0].text.strip():
                    raise ValueError(f"{bound['id']}: its opening does not start with "
                                     f"{bound['heading']!r}")
                body = ([replace(body[0], text=opening)] if opening else []) + body[1:]
            for para in body:
                if self._BARE_NUMBER.match(para.text) or any(c.search(para.text) for c in close_res):
                    raise ValueError(f"{bound['id']}: a heading inside the text: {para.text[:80]!r}")
            text = [q for q in (self._cleaned(p) for p in body) if q.text]
            if not text:
                raise ValueError(f"{bound['id']}: no text")
            groups = group_passages(text, PASSAGE_WORDS)
            units.extend(Unit(bound["id"] if len(groups) == 1 else f"{bound['id']}-{k:02d}", g)
                         for k, g in enumerate(groups, 1))
        return units

    def _cleaned(self, para):
        return _with_text(para, para.text)


class DeferrariExtracts(Headed):
    """Deferrari's *Sources of Catholic Dogma* (1957), decree text only (R9, Carter, 4 Nov
    2026): Denzinger's headings, notes and numbers stay out. Beyond `Headed`:

    - a paragraph wholly in square brackets is an editor's label, and one wholly in
      round brackets an editor's remark ("(The decrees for Greeks and Armenians ...
      follow.)"), even where the clean-up set it over two paragraphs: both go;
    - so does a label opening a paragraph before its first sentence ("[The procession
      of the Holy Spirit] In the name of ...", "[De novissimis] It has likewise ..."),
      with the note call after it that the text layer reads as a digit;
    - a bracketed reference goes: a Bible reference with chapter and verse ("[Ps.
      18:9]", "[II Thess. 2: 14]", the OCR often reading "]" as "J") or a reference to
      Denzinger's numbers ("[see n. 595]", "[n. 696]");
    - words in brackets that the sentence reads ("Thy light [law]") are the translator's
      and stay.

    The margin numbers are furniture (`furniture.py`, `margin_numbers`), and a list's
    own numbers ("6. God ought to obey the devil.") stand in the text and stay."""
    name = "deferrari"

    _LABEL = re.compile(r"^\s*(?:\[[^\[\]]*[\]J]|\([^()]*\))\W*$")
    _OPENING_LABEL = re.compile(r"^\s*\[[^\[\]\d]{1,60}[\]J](?:\s+\d)?\s+(?=[A-Z])")
    _REFERENCE = re.compile(r"\s?\[(?:(?:see|cf\.)\s[^\[\]]{0,60}|n\.\s?\d+[a-z]?|[^\[\]]{0,30}?\d+\s?:\s?\d+"
                            r"[^\[\]]{0,40}?)[\]J](?=\W|$)")

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = (), bounds: tuple[dict, ...] = ()) -> list[Unit]:
        return super().split(self._labels_joined(paragraphs), series, closes, bounds)

    def _labels_joined(self, paragraphs: list) -> list:
        """`paragraphs` with a label or remark the clean-up set over two or more joined
        into one, where together they are wholly bracketed."""
        out, k = [], 0
        while k < len(paragraphs):
            para = paragraphs[k]
            opening = para.text.lstrip()[:1]
            if opening in "([" and opening and not self._LABEL.match(para.text):
                closing = ")" if opening == "(" else "]"
                for j in range(k + 1, min(k + 3, len(paragraphs))):
                    text = " ".join(p.text for p in paragraphs[k:j + 1])
                    if text.count(opening) == text.count(closing) and self._LABEL.match(text):
                        group = paragraphs[k:j + 1]
                        para = replace(para, text=text, raw="\n".join(p.raw for p in group),
                                       leaves=sorted({x for p in group for x in p.leaves}))
                        k = j
                        break
            out.append(para)
            k += 1
        return out

    def _cleaned(self, para):
        if self._LABEL.match(para.text):
            return replace(para, text="")
        text = self._OPENING_LABEL.sub("", para.text, count=1)
        text = re.sub(r" {2,}", " ", self._REFERENCE.sub("", text)).strip()
        return _with_text(para, text)


UNITS: dict[str, Units] = {SchroederCanons.name: SchroederCanons(), Bounded.name: Bounded(),
                           Headed.name: Headed(), DeferrariExtracts.name: DeferrariExtracts()}


def get_units(name: str) -> Units:
    try:
        return UNITS[name]
    except KeyError:
        raise ValueError(f"no OCR units {name!r}; known: {', '.join(sorted(UNITS))}")
