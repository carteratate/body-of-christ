"""Split pieces named by the first source unit they hold (corpus-cleanup 2.1, C-10, D1).

A unit longer than one card is cut by `split_display_passage`. Its first piece takes the
unit's anchor; each later piece takes the unit's anchor plus `identity.PIECE_MARK` and the
locator of the source unit it opens with (a ThML or Summa paragraph id, a CCC number, a
verse, an HTML element's ordinal). A piece that opens inside a source unit adds `-<k>`:
the unit's start counts as 1, so the first cut inside it is `-2`. A piece therefore keeps
its name while its opening unit still opens a piece, however the cuts around it move.

Adapters clean a unit's text after reading it (footnote markers, apparatus, whitespace),
so offsets in the cleaned text are mapped back to the source units by aligning words.

Where the cuts fall is `pack_units`'s job (1.10c): a split unit is packed from whole source
units (verses, paragraphs), and only a source unit longer than a card is cut inside. Each
piece then cites its own text (`piece_reference`): the range of the labelled units it
holds ("Genesis 1:14–31"), or, where the units carry no label, its place among the
unit's pieces ("(part 2 of 3)", D5).
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from identity import PIECE_MARK
from ingest.common import split_display_passage

_WORD = re.compile(r"[^\W_]+")


@dataclass(frozen=True)
class Segment:
    """One source unit of a passage's unit, as the adapter read it before cleaning."""
    locator: str
    text: str


def _words(text: str) -> list[tuple[int, str]]:
    """(offset in `text`, normalized word): offsets index the text as given, so a
    normalization that changes length (NFKC turns "…" into "...") never moves them."""
    return [(m.start(), unicodedata.normalize("NFKC", m.group(0)).lower())
            for m in _WORD.finditer(text)]


class SourceMap:
    """Offsets in a cleaned unit text, mapped to the segments it was read from."""

    def __init__(self, text: str, segments: list[Segment]):
        self.segments = segments
        raw: list[str] = []
        self.seg_of: list[int] = []
        for s, seg in enumerate(segments):
            for _, word in _words(seg.text):
                raw.append(word)
                self.seg_of.append(s)
        clean = _words(text)
        self.starts = [at for at, _ in clean]
        words = [word for _, word in clean]
        self.raw_index = [0] * len(words)
        if raw:
            matcher = SequenceMatcher(None, raw, words, autojunk=False)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                for j in range(j1, j2):
                    if tag == "equal":
                        i = i1 + (j - j1)
                    elif tag == "replace":
                        i = i1 + (j - j1) * (i2 - i1) // (j2 - j1)
                    else:                 # an inserted word: the raw word after it
                        i = i1
                    self.raw_index[j] = min(i, len(raw) - 1)

    def segment_at(self, offset: int) -> tuple[int, bool]:
        """The segment holding the first word at or after `offset`, and whether that
        word opens the segment (the word before it comes from an earlier segment)."""
        if not self.starts or not self.seg_of:
            return 0, offset == 0
        j = min(bisect.bisect_left(self.starts, offset), len(self.starts) - 1)
        s = self.seg_of[self.raw_index[j]]
        opens = j == 0 or self.seg_of[self.raw_index[j - 1]] < s
        return s, opens

    def openings(self) -> list[tuple[int, int]]:
        """(segment, offset) for each segment whose first word is in the text."""
        out, last = [], -1
        for j, start in enumerate(self.starts):
            s = self.seg_of[self.raw_index[j]] if self.seg_of else 0
            if s > last:
                out.append((s, start))
                last = s
        return out


def piece_spans(text: str, pieces: list[str]) -> list[int]:
    """Each piece's start in its unit text, found moving forward
    (`split_display_passage` keeps every word once, in order)."""
    starts, cursor = [], 0
    for piece in pieces:
        start = text.find(piece, cursor)
        if start < 0:
            raise ValueError("a display piece is not in its unit's text")
        starts.append(start)
        cursor = start + len(piece)
    return starts


def name_pieces(unit: str, text: str, pieces: list[str], segments: list[Segment],
                source: SourceMap | None = None, offset: int = 0
                ) -> list[tuple[str, tuple[tuple[str, int], ...]]]:
    """(anchor, source_units) for each piece of the unit whose anchor is `unit`.

    `text` is the cleaned unit text `pieces` were cut from, `segments` the source units
    it was read from, in order. `source_units` lists the locators of the units whose
    text starts in that piece, with their offsets in the piece; a piece that opens
    inside a unit lists that unit first, at offset 0. A unit that is not split lists
    none: it holds them all. When `source` maps a longer text
    that holds this unit (a Summa article holding one part), `offset` is where `text`
    starts in it."""
    if len(pieces) == 1:
        # A whole unit holds every source unit it was read from; nothing to name.
        return [(unit, ())]
    source = source or SourceMap(text, segments)
    starts = [offset + at for at in piece_spans(text, pieces)]
    ends = starts[1:] + [offset + len(text) + 1]
    openings = source.openings()
    out = []
    cuts: dict[int, int] = {}
    for k, (start, end) in enumerate(zip(starts, ends)):
        s, opens = source.segment_at(start)
        units = [(segments[t].locator, max(0, at - start)) for t, at in openings
                 if start <= at < end]
        if not opens and segments:
            units.insert(0, (segments[s].locator, 0))
        if k == 0:
            anchor = unit
        elif opens:
            anchor = f"{unit}{PIECE_MARK}{segments[s].locator}"
        else:
            cuts[s] = cuts.get(s, 1) + 1
            anchor = f"{unit}{PIECE_MARK}{segments[s].locator}-{cuts[s]}"
        out.append((anchor, tuple(units)))
    return out


@dataclass(frozen=True)
class Packed:
    """One piece from `pack_units`: its text, the index of the unit it opens with and of
    the last unit whose text it holds, and whether it opens at that first unit's start (a
    later fragment of a unit longer than the cap opens inside it)."""
    text: str
    first: int
    last: int
    opens: bool = True


def pack_units(units: list[tuple[str | None, str]], max_chars: int,
               sep: str = "\n\n") -> list[Packed]:
    """Cut a unit read as `units`, `(label, text)` in reading order, into pieces that
    hold whole units (1.10c). A unit is a verse, a numbered paragraph, a source `<p>`.

    The cuts are `split_display_passage`'s over the joined text, so a piece is at most
    `max_chars`, or up to `DISPLAY_PASSAGE_MAX_OVERSHOOT` more where it ends with a unit,
    except that no cut falls inside a unit no longer than the cap: one chosen there moves
    to that unit's start (or its end, where the piece opens with it). Only a unit longer
    than the cap is cut inside, and the units around it may share its first and last
    pieces. Where no cut moves, the pieces are those `split_display_passage` gives.

    The joined text is the units' texts joined with `sep`, stripped. With `sep=""` the
    units are consecutive slices of one text, each keeping the whitespace that follows it
    (`cut_at_units`), so every piece is a slice of that text."""
    texts = [text for _, text in units]
    joined = sep.join(texts)
    lead = len(joined) - len(joined.lstrip())
    spans: list[tuple[int, int]] = []        # each unit's stripped text in `joined`
    at = 0
    for k, text in enumerate(texts):
        if k:
            at += len(sep)
        body = text.strip()
        begin = at + (len(text) - len(text.lstrip()))
        spans.append((begin - lead, begin - lead + len(body)))
        at += len(text)
    text = joined.strip()
    keep = [span for span, unit in zip(spans, texts)
            if unit.strip() and span[1] - span[0] <= max_chars]
    pieces = split_display_passage(text, max_chars, keep)
    out: list[Packed] = []
    for piece, begin in zip(pieces, piece_spans(text, pieces)):
        finish = begin + len(piece)
        held = [k for k, (a, b) in enumerate(spans) if a < finish and b > begin and b > a]
        out.append(Packed(piece, held[0], held[-1], spans[held[0]][0] >= begin))
    return out


def cut_at_units(text: str, segments: list[Segment],
                 source: SourceMap | None = None) -> list[tuple[int, str]]:
    """`text`, a cleaned unit text read from `segments`, cut where each segment's text
    starts: (segment index, slice), each slice keeping the whitespace after it so the
    slices join back to `text`. A cut falls before the whole token holding the segment's
    first word (an opening quote stays with its paragraph). A segment with no word in
    `text` adds nothing; its text, if any, is in the slice before it."""
    source = source or SourceMap(text, segments)
    cuts: list[tuple[int, int]] = []
    for s, at in source.openings():
        while at > 0 and not text[at - 1].isspace():
            at -= 1
        if cuts and at <= cuts[-1][1]:
            continue
        cuts.append((s, 0 if not cuts else at))
    if not cuts:
        return [(0, text)] if text else []
    ends = [at for _, at in cuts[1:]] + [len(text)]
    return [(s, text[at:end]) for (s, at), end in zip(cuts, ends)]


def pack_text(text: str, segments: list[Segment], max_chars: int) -> list[str]:
    """The pieces of a cleaned unit text, packed from the source units it was read from
    (`cut_at_units`), for adapters whose units carry no label of their own."""
    units = [(None, t) for _, t in cut_at_units(text, segments)]
    return [p.text for p in pack_units(units, max_chars, sep="")]


RANGE = "\u2013"   # EN DASH, as Bible references write ranges ("Matthew 5:1–4")
# The suffix `piece_reference` adds to a piece of a unit with no labels.
PART_SUFFIX = re.compile(r" \(part (\d+) of (\d+)\)$")


def unit_reference(reference: str) -> str:
    """A piece's reference without its "(part 2 of 3)": the citation of its whole unit,
    which checks read numbers from ("Lumen Gentium, §8")."""
    return PART_SUFFIX.sub("", reference)


def piece_reference(base: str, first_label: str | None, last_label: str | None,
                    part: int, parts: int) -> str:
    """The citation of one piece of a unit cited as `base` (1.10c, D5).

    With labels, the range the piece holds: `base first–last`, the last label shortened
    where it repeats the first's chapter ("Genesis 1:14–31", "Genesis 1:31–2:3"), or
    `base first` for one label. Without labels, `base` alone for a unit in one piece,
    otherwise `base (part 2 of 3)`: the only piece suffix in the corpus."""
    if first_label is not None:
        last = last_label if last_label is not None else first_label
        if last == first_label:
            return f"{base} {first_label}"
        head, colon, _ = first_label.rpartition(":")
        if colon and last.startswith(head + colon):
            last = last[len(head) + 1:]
        return f"{base} {first_label}{RANGE}{last}"
    if parts <= 1:
        return base
    return f"{base} (part {part} of {parts})"


ORDINAL_ATTR = "data-source-ordinal"
# The HTML elements adapters read text from; an element's locator counts them all.
BODY_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6")


def number_elements(soup) -> None:
    """Record each body element's ordinal among all `BODY_TAGS` elements of the vendored
    HTML file, before an adapter removes chrome or regroups anything, so moving a heading
    or dropping a note never renumbers them (2.1). Only a change to the file can."""
    for k, el in enumerate(soup.find_all(BODY_TAGS), 1):
        el[ORDINAL_ATTR] = str(k)


def element_locator(el) -> str:
    """`e<k>`: an element's ordinal from `number_elements`."""
    return f"e{el[ORDINAL_ATTR]}"


def unique_unit_anchors(bases: list[str], split: list[bool]) -> list[str]:
    """A unique anchor for each unit of a document whose structural bases may repeat (a
    source that numbers two units alike). Units that are not split take `base`,
    `base-2`, ... in document order, exactly as before 2.1, so no live anchor moves;
    split units then take the next free name. (Before 2.1 a split unit's first piece was
    `base/p1`, which left `base` to the next unit.) Only units sharing a base are affected,
    and those are source-numbering defects the Phase 1 items rebuild."""
    taken: set[str] = set()
    out: list[str] = [""] * len(bases)
    for wanted in (False, True):
        for i, (base, is_split) in enumerate(zip(bases, split)):
            if is_split != wanted:
                continue
            anchor, k = base, 1
            while anchor in taken:
                k += 1
                anchor = f"{base}-{k}"
            taken.add(anchor)
            out[i] = anchor
    return out
