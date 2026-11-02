"""Reading order: which lines of a page are read, and in what order.

A work's config names its layout. Only `single-column` exists: one block of text read
top to bottom. A page in two columns, or in parallel Latin and English columns (R8:
Unam Sanctam, Ubi Primum 1849), is another `Layout` that returns the lines it keeps in
reading order; `furniture.py` works on whatever a layout returns, so adding one does not
change the clean-up. Each new layout comes in its own small PR with the work that needs
it (5.6c's rule).
"""
from __future__ import annotations

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


LAYOUTS: dict[str, Layout] = {SingleColumn.name: SingleColumn()}


def get_layout(name: str) -> Layout:
    try:
        return LAYOUTS[name]
    except KeyError:
        raise ValueError(f"no OCR layout {name!r}; known: {', '.join(sorted(LAYOUTS))}. "
                         "A new layout is added in its own PR with the work that needs it.")
