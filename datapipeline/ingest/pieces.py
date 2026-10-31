"""Split pieces named by the first source unit they hold (corpus-cleanup 2.1, C-10, D1).

A unit longer than one card is cut by `split_display_passage`. Its first piece takes the
unit's anchor; each later piece takes the unit's anchor plus `identity.PIECE_MARK` and the
locator of the source unit it opens with (a ThML or Summa paragraph id, a CCC number, a
verse, an HTML element's ordinal). A piece that opens inside a source unit adds `-<k>`:
the unit's start counts as 1, so the first cut inside it is `-2`. A piece therefore keeps
its name while its opening unit still opens a piece, however the cuts around it move.

Adapters clean a unit's text after reading it (footnote markers, apparatus, whitespace),
so offsets in the cleaned text are mapped back to the source units by aligning words.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from identity import PIECE_MARK

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
