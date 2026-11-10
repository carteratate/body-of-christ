"""Scanned pages as positioned lines, read from the Internet Archive's `_djvu.xml`.

The plain `_djvu.txt` runs the whole book together; the XML keeps each page apart and
gives every word a box, which is what lets `furniture.py` remove running heads, page
numbers and notes by where they sit. `_page_numbers.json` maps each scan image (leaf) to
the number printed on the page.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class Line:
    """One printed line: its words and its box in image pixels (y grows downwards)."""
    text: str
    x0: int
    top: int
    x1: int
    bottom: int
    column: int = 0      # index of the djvu PAGECOLUMN the line came from

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass
class Page:
    leaf: int                     # 0-based scan image index, as in `_page_numbers.json`
    width: int
    height: int
    lines: list[Line] = field(default_factory=list)
    number: str | None = None     # the printed page number, where the scan has one

    def ref(self) -> str:
        return f"p. {self.number}" if self.number else f"scan image {self.leaf}"


def _line(el, column: int) -> Line | None:
    words, boxes = [], []
    for w in el.iter("WORD"):
        text = (w.text or "").strip()
        coords = w.get("coords")
        if not text or not coords:
            continue
        # djvu coords are "left,bottom,right,top".
        left, bottom, right, top = (int(v) for v in coords.split(",")[:4])
        words.append(text)
        boxes.append((left, top, right, bottom))
    if not words:
        return None
    return Line(" ".join(words), min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes), column)


def read_djvu_xml(path: str | Path, leaves: range | None = None) -> list[Page]:
    """The pages of a `_djvu.xml`, or only those whose leaf is in `leaves`."""
    pages: list[Page] = []
    leaf = -1
    for _, obj in etree.iterparse(str(path), tag="OBJECT", resolve_entities=False,
                                  no_network=True, huge_tree=True):
        leaf += 1
        if leaves is None or leaf in leaves:
            page = Page(leaf, int(obj.get("width", 0)), int(obj.get("height", 0)))
            for column, col in enumerate(obj.iter("PAGECOLUMN")):
                for el in col.iter("LINE"):
                    line = _line(el, column)
                    if line:
                        page.lines.append(line)
            pages.append(page)
        obj.clear()
        if leaves is not None and leaf >= leaves.stop - 1:
            break
    return pages


def read_page_numbers(path: str | Path, leaf_offset: int = 0) -> dict[int, str]:
    """Leaf → printed page number, from `_page_numbers.json` (leaves without one omitted).

    The map counts the scan's leaves; the XML holds only the leaves the Archive puts in
    its page images, counted from 0. Where it leaves out leaves before the first page (a
    colour card), `leaf_offset` says how many, so a map's leaf L is the XML's L - offset."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {int(p["leafNum"]) - leaf_offset: str(p["pageNumber"])
            for p in data.get("pages", []) if p.get("pageNumber")}


def leaves_for_pages(numbers: dict[int, str], first: str, last: str) -> range:
    """The leaves from printed page `first` to printed page `last`, inclusive."""
    by_number = {n: leaf for leaf, n in numbers.items()}
    if first not in by_number or last not in by_number:
        raise ValueError(f"pages {first}–{last} not both in the page-number map")
    return range(by_number[first], by_number[last] + 1)


def load_pages(xml: str | Path, page_numbers: str | Path | None,
               leaves: range | None = None, leaf_offset: int = 0) -> list[Page]:
    pages = read_djvu_xml(xml, leaves)
    if page_numbers:
        numbers = read_page_numbers(page_numbers, leaf_offset)
        for page in pages:
            page.number = numbers.get(page.leaf)
    return pages
