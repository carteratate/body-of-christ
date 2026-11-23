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
    first paragraph `first` matches to the next one `last` matches, inclusive. A bound may
    also name `start` and `end`, patterns searched in that first and last paragraph, where a
    text opens or closes inside a paragraph: it then runs from the start of `start`'s match
    to the end of `end`'s (Hefele's four anathemas, among the other acclamations of the
    session, 1.2c).

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
            text = self._kept(_cut(paragraphs[first:last + 1], bound), bound)
            groups = group_passages(text, PASSAGE_WORDS)
            units.extend(Unit(bound["id"] if len(groups) == 1 else f"{bound['id']}-{k:02d}", g)
                         for k, g in enumerate(groups, 1))
            after = last + 1
        return units

    def _kept(self, paragraphs: list, bound: dict) -> list:
        """A bounded text's paragraphs as they go on. A bound with `keep_quotes` keeps its
        double quotation marks: a text printed on its own quotes in them (the Dublin
        Review's Quanta Cura, 1.3d), where Giles's quote the whole document."""
        if bound.get("keep_quotes"):
            return list(paragraphs)
        return [replace(p, text=self._unquoted(p.text)) for p in paragraphs]

    def _unquoted(self, text: str) -> str:
        def mend(m: re.Match) -> str:
            before, after = m.string[:m.start()], m.string[m.end():]
            return "" if not before or not after else " "
        text = self._DOUBLE_QUOTES.sub(mend, text)
        return re.sub(r" {2,}", " ", text).strip()


def _cut(paragraphs: list, bound: dict) -> list:
    """`paragraphs` with the first opened at `bound`'s `start` and the last closed at the
    end of its `end`, where it names them."""
    paragraphs = list(paragraphs)
    if bound.get("end"):
        m = re.search(bound["end"], paragraphs[-1].text)
        if m is None:
            raise ValueError(f"{bound['id']}: its last paragraph holds no {bound['end']!r}")
        paragraphs[-1] = replace(paragraphs[-1], text=paragraphs[-1].text[:m.end()].strip())
    if bound.get("start"):
        m = re.search(bound["start"], paragraphs[0].text)
        if m is None:
            raise ValueError(f"{bound['id']}: its first paragraph holds no {bound['start']!r}")
        paragraphs[0] = replace(paragraphs[0], text=paragraphs[0].text[m.start():].strip())
    return paragraphs


class ChrystalLetter(Bounded):
    """Nestorius's second letter to Cyril in James Chrystal's *Authoritative
    Christianity*, vol. 1 (1895), pp. 155–166, without his summaries or notes (R9; Carter,
    4 Nov 2026; 1.2c). Beyond `Bounded`:

    - his summaries go: each opens a paragraph with "[Section" and runs, over as many
      paragraphs and pages as it takes, to the paragraph that closes its bracket ("]",
      or "|" as the OCR reads it);
    - so do his note calls ("(290)"), with the comma a call between two commas leaves
      doubled ("long suffering, (292), and", "“Anointed,” (299), and"); his notes are kept apart by `note_opens`;
    - quotation marks stay: they are the letter's own, quoting Scripture and Cyril;
    - words in square brackets inside a sentence ("[at Nicaea]", "[that is]") are his
      insertions in the translation and stay, as Deferrari's do."""
    name = "chrystal"

    _SUMMARY_OPENS = re.compile(r"^\W{0,2}\[Section\b", re.IGNORECASE)
    _SUMMARY_CLOSES = re.compile(r"[\]|]\W*$")
    _CALL = re.compile(r"\s?\(\d{3}\)([,.;:]?)")

    def _kept(self, paragraphs: list, bound: dict) -> list:
        out, summary = [], False
        for para in paragraphs:
            if not summary and self._SUMMARY_OPENS.match(para.text):
                summary = True
            if summary:
                summary = not self._SUMMARY_CLOSES.search(para.text)
                continue
            out.append(replace(para, text=self._without_calls(para.text)))
        if summary:
            raise ValueError(f"{bound['id']}: a summary opens and does not close")
        return out

    def _without_calls(self, text: str) -> str:
        def drop(m: re.Match) -> str:
            mark = m.group(1)
            before = text[:m.start()].rstrip().rstrip("’”'\"")
            return "" if mark and before.endswith(mark) else mark
        text = self._CALL.sub(drop, text)
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


class ChadwickSections:
    """Clement's *Stromata* III in Henry Chadwick's translation (*Alexandrian Christianity*,
    1954, pp. 40–92; #399), one unit per Stählin section, `ch03/s012`, as the print
    numbers them: "12. If Plato himself …". The adapter rejoins the sections and cuts
    them where ANF's passages begin (`ingest/stromata_chadwick.py`).

    - The heading lines above chapter I ("On Marriage", "Miscellanies, Book III", "THE
      TEXT") go, and each "CHAPTER N" heading, which only says where a chapter starts;
    - the sections are found in order, 1 to `unit_count`, each number where a paragraph
      opens or after a sentence's end, so a section that opens inside a paragraph (15)
      is found too. The OCR splits a number ("1 06.", "6 1 .") or reads its digits as
      letters ("i." for 1, "no." for 110); all 110 must be found, in order;
    - the number itself goes: it is Stählin's reference, not Clement's text;
    - so do the note calls, which the OCR reads as a number standing alone after a
      word ("necessity." 1 And"), sometimes with a mark ("5 *");
    - a verse line, or a line the clean-up opened as a paragraph though the one before
      does not end a sentence, continues the paragraph before it."""
    name = "chadwick"
    SECTIONS = 110

    _TITLE = re.compile(r"^(On Marriage|Miscellanies, Book III|THE TEXT)$")
    _CHAPTER = re.compile(r"^CHAPTER ([IVXL]+)\b\s*")
    _ENDS = re.compile(r"[.?!:;\"”’'*)]\W*(\d{1,2}\W*)?$")
    _DIGIT = {"0": "[0oO]", "1": "[1Iil]", "5": "[5S]"}
    # A note call: a number standing alone after a word or a stop, with any mark the OCR
    # read beside it; or glued to a closing quotation mark ('ofGod."83').
    _CALL = re.compile(r"(?<=[\w.,;:!?\"”’')\]*])(?:\s?/)?\s+\d{1,2}(?:\s?\*)?(?=\s|$)"
                       r"|(?<=[\"”’])\d{1,2}(?=\s|$)")

    def _number(self, n: int) -> str:
        digits = r"\s?".join(self._DIGIT.get(d, d) for d in str(n))
        return rf"(?:{digits}|no)" if n == 110 else digits

    def split(self, paragraphs: list, series: tuple[int, ...] | None = None,
              closes: tuple[str, ...] = (), bounds: tuple[dict, ...] = ()) -> list[Unit]:
        from ocr.work import PASSAGE_WORDS, group_passages

        if series or closes or bounds:
            raise ValueError("chadwick units take no series, closes or bounds")
        start = next((k for k, p in enumerate(paragraphs) if self._CHAPTER.match(p.text)), None)
        if start is None or any(not self._TITLE.match(p.text.strip()) for p in paragraphs[:start]):
            raise ValueError("chadwick: the text does not open with its title lines and CHAPTER I")
        body, chapters = self._body(paragraphs[start:])
        units: list[Unit] = []
        n, at = 1, (0, 0)
        cuts = []
        while True:
            found = self._find(body, n, at)
            if found is None:
                break
            cuts.append((n, found))
            at, n = (found[0], found[1] + 1), n + 1
        if not cuts or cuts[0][1] != (0, 0):
            raise ValueError("chadwick: section 1 does not open the text")
        if len(cuts) != self.SECTIONS:
            raise ValueError(f"chadwick: sections 1 to {len(cuts)} found, Book III has "
                             f"{self.SECTIONS}; section {len(cuts) + 1} is not where expected")
        for k, (n, (para, off)) in enumerate(cuts):
            end = cuts[k + 1][1] if k + 1 < len(cuts) else (len(body), 0)
            section = self._section(body, (para, off), end)
            chapter = max(c for c, at_para in chapters if at_para <= para)
            groups = group_passages(section, PASSAGE_WORDS)
            uid = f"ch{chapter:02d}/s{n:03d}"
            units.extend(Unit(uid if len(groups) == 1 else f"{uid}-{j:02d}", g)
                         for j, g in enumerate(groups, 1))
        return units

    def _body(self, paragraphs: list) -> tuple[list, list[tuple[int, int]]]:
        """The paragraphs without the chapter headings, verse lines joined to the line
        before, and (chapter, first paragraph) for each chapter."""
        body, chapters = [], []
        for para in paragraphs:
            m = self._CHAPTER.match(para.text)
            if m:
                chapters.append((_roman(m.group(1)), len(body)))
                rest = para.text[m.end():].strip()
                if not rest:
                    continue
                para = replace(para, text=rest, continues=False)
            elif body and (not self._ENDS.search(body[-1].text) or para.text[:1].islower()):
                para = replace(para, continues=True)
            body.append(para)
        numbers = [c for c, _ in chapters]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(f"chadwick: chapters out of order: {numbers}")
        return body, chapters

    def _find(self, body: list, n: int, at: tuple[int, int]) -> tuple[int, int] | None:
        """Where section `n` opens, at or after `at`: its number opening a paragraph, or
        after a sentence's end (and any note call there)."""
        pattern = re.compile(rf"(?:^|(?<=[.?!:\"”’'*)])\s+(?:\S{{1,3}}\s+)?)"
                             rf"(?={self._number(n)}\s?[.,]{{1,2}}\s)")
        for k in range(at[0], len(body)):
            text = body[k].text
            for m in pattern.finditer(text, at[1] if k == at[0] else 0):
                pos = m.end()
                return k, pos
        return None

    def _section(self, body: list, start: tuple[int, int], end: tuple[int, int]) -> list:
        """The section's paragraphs from `start` to `end`, its number and note calls
        taken out."""
        (p0, o0), (p1, o1) = start, end
        out = []
        for k in range(p0, p1 + 1 if o1 else p1):
            para = body[k]
            text = para.text[o0 if k == p0 else 0:o1 if k == p1 else None]
            if k == p0:
                text = re.sub(rf"^{self._number_any()}\s?[.,]{{1,2}}\s+", "", text)
                para = replace(para, continues=False)
            text = re.sub(r" {2,}", " ", self._CALL.sub("", text)).strip()
            if text:
                out.append(replace(para, text=text))
        return out

    def _number_any(self) -> str:
        return r"(?:[0-9IilOoS](?:\s?[0-9IilOoS]){0,2}|no)"


def _roman(numeral: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for k, ch in enumerate(numeral):
        v = values[ch]
        total += -v if k + 1 < len(numeral) and values[numeral[k + 1]] > v else v
    return total


UNITS: dict[str, Units] = {SchroederCanons.name: SchroederCanons(), Bounded.name: Bounded(),
                           Headed.name: Headed(), DeferrariExtracts.name: DeferrariExtracts(),
                           ChrystalLetter.name: ChrystalLetter(),
                           ChadwickSections.name: ChadwickSections()}


def get_units(name: str) -> Units:
    try:
        return UNITS[name]
    except KeyError:
        raise ValueError(f"no OCR units {name!r}; known: {', '.join(sorted(UNITS))}")
