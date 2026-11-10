"""Reading order: which lines of a page are read, and in what order.

A work's config names its layout. `single-column` is one block of text read top to
bottom. `parallel-left` keeps the left of two parallel columns (Deferrari's Constantinople
IV: Anastasius's Latin on the left, the Greek on the right). A page in two columns of
running text, or in parallel Latin and English columns (R8: Unam Sanctam, Ubi Primum
1849), would be another `Layout` that returns the lines it keeps in reading order;
`furniture.py` works on whatever a layout returns, so adding one does not change the
clean-up. Each new layout comes with the work that needs it (5.6c's rule).
"""
from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Protocol

from ocr.pages import Line, Page


class Layout(Protocol):
    name: str

    def reading_order(self, page: Page) -> list[Line]:
        """The page's lines in reading order, leaving out any it does not read."""


class SingleColumn:
    name = "single-column"

    def reading_order(self, page: Page) -> list[Line]:
        # djvu's PAGECOLUMN and PARAGRAPH split a single column at arbitrary points, so
        # order by position only.
        return sorted(page.lines, key=lambda ln: (ln.top, ln.x0))


class ParallelLeft:
    """The left column where a page sets two texts side by side, and every line that runs
    the full width. Deferrari prints Constantinople IV's canons in Anastasius's Latin
    (left) beside the Greek (right); where one column ends, the other runs on across the
    page, and the text layer gives each printed line as one line across both columns.

    It needs each line's words (`Line.words`, from `pdf.py`). A line whose words leave a
    gutter across the middle of the text block is cut there, and its left part kept. A
    gutter is wider than a word space, and the words right of it start where the page's
    right column starts (or a paragraph's indent later): a justified line of running
    text can have one wide space near the middle, but not there. A line that starts right
    of the middle is in the right column alone, and is left out. A page with fewer than
    `MIN_CUT_LINES` gutters has no parallel columns."""
    name = "parallel-left"

    # Fractions of the page width: how far from the text block's middle a gutter may
    # lie; how wide it is at least (Deferrari's are 0.033 to 0.065, his widest word
    # spaces 0.029); and how far the words after it may start before or after the
    # right column's usual start (an indent is about 0.03).
    GUTTER_SLACK = 0.04
    GUTTER_WIDTH = 0.031
    START_BEFORE = 0.01
    START_AFTER = 0.045
    MIN_CUT_LINES = 3

    def reading_order(self, page: Page) -> list[Line]:
        lines = sorted(page.lines, key=lambda ln: (ln.top, ln.x0))
        if any(not ln.words for ln in lines):
            raise ValueError(f"{page.ref()}: the parallel-left layout needs each line's words")
        full = [ln for ln in lines if len(ln.words) >= 6]
        if not full:
            return lines
        middle = (statistics.median(ln.x0 for ln in full) + statistics.median(ln.x1 for ln in full)) / 2
        slack, width = self.GUTTER_SLACK * page.width, self.GUTTER_WIDTH * page.width
        gaps = {id(ln): k for ln in lines
                if (k := self._gutter(ln.words, middle, slack, width)) is not None}
        if len(gaps) < self.MIN_CUT_LINES:
            return lines
        start = statistics.median(ln.words[gaps[id(ln)]][1] for ln in lines if id(ln) in gaps)
        lo, hi = start - self.START_BEFORE * page.width, start + self.START_AFTER * page.width
        out = []
        for ln in lines:
            k = gaps.get(id(ln))
            if k is not None and lo <= ln.words[k][1] <= hi:
                kept = ln.words[:k]
                out.append(replace(ln, text=" ".join(w[0] for w in kept), x1=kept[-1][2],
                                   words=kept))
            elif ln.x0 < middle - slack:
                out.append(ln)
        return out

    @staticmethod
    def _gutter(words, middle: float, slack: float, width: float) -> int | None:
        """The index of the first word right of a gutter across `middle`, if any."""
        for k in range(1, len(words)):
            end, start = words[k - 1][2], words[k][1]
            if start - end >= width and end < middle + slack and start > middle - slack:
                return k
        return None


LAYOUTS: dict[str, Layout] = {SingleColumn.name: SingleColumn(), ParallelLeft.name: ParallelLeft()}


def get_layout(name: str) -> Layout:
    try:
        return LAYOUTS[name]
    except KeyError:
        raise ValueError(f"no OCR layout {name!r}; known: {', '.join(sorted(LAYOUTS))}. "
                         "A new layout is added in its own PR with the work that needs it.")
