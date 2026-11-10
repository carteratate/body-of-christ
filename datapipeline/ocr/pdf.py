"""Scanned pages as positioned lines, read from a PDF's text layer (1.2e, Deferrari).

Some scans come as a PDF whose pages are images under an OCR text layer (Deferrari's
*Sources of Catholic Dogma*, Loreto reprint: Acrobat's Paper Capture over JBIG2 images).
This reads that layer with pypdfium2 into the same `Page` and `Line` objects
`pages.py` reads from the Internet Archive's `_djvu.xml`, so the clean-up after it is
the same. A leaf is the PDF's page index, counted from 0, and a work's `pdf_page_offset`
maps it to the printed page: printed = leaf - offset.

Each line keeps its words with their positions (`Line.words`), which a layout needs to
cut parallel columns apart and the clean-up needs to find margin numbers. Superscript
digits (note calls, "Dionysius,³") are left out here, by size and height above the
line, since the text layer gives them as ordinary digits: each is logged. Where the text
layer reads "m" as "n1" or "111" and "w" as "\\v", the word is mended if that makes it
a known word; the raw lines keep what the layer read.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path

from ocr.pages import Line, Page

# Line coordinates are PDF points times this, so the clean-up's whole-pixel boxes keep
# the detail of a 300 dpi scan.
SCALE = 4
# A digit is a superscript when it is this much smaller than the line's letters and its
# foot stands this far above their baseline, as fractions of their height.
SUPERSCRIPT_HEIGHT = 0.8
SUPERSCRIPT_RAISE = 0.25


@dataclass(frozen=True)
class Char:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top


# The text layer's usual misreadings of letters inside a word: "m" as "n1", "111", "nl"
# or "ln" ("con1mand", "trans111it", "sonletimes", "eculnenical"), "w" as "\\v"
# ("\\vhich"), "f" as "£" ("£rom"), "o" as "0" ("n10ve"). Applied in this order, and kept
# only where the result is a known word and the reading is not (`_mended`).
_MISREAD = ((re.compile(r"(?<=[a-z])0|0(?=[a-z])"), "o"), (re.compile(r"111"), "m"),
            (re.compile(r"(?<=[a-z])n1|n1(?=[a-z])"), "m"), (re.compile(r"nl|ln"), "m"),
            (re.compile(r"\\v"), "w"), (re.compile(r"£"), "f"))


def _mended(word: str) -> str:
    """`word` with the text layer's misreadings of letters mended, where that makes it a
    known word. Punctuation around the word is kept."""
    from ocr.words import is_known

    lead, core, tail = re.match(r"^([^\w\\£]*)(.*?)(\W*)$", word).groups()
    if not core or is_known(core):
        return word
    mended = core
    for pattern, letter in _MISREAD:
        mended = pattern.sub(letter, mended)
    return lead + mended + tail if mended != core and is_known(mended) else word


@dataclass(frozen=True)
class NoteCall:
    leaf: int
    text: str
    after: str       # the word it was attached to


# The text layer marks a word broken at a line end with a soft hyphen or U+FFFE.
_LINE_END_HYPHENS = {"\u00ad": "-", "\ufffe": "-"}


def _chars(textpage, crop: tuple[float, float, float, float]) -> list[Char | None]:
    """The text layer's characters in page coordinates (y down); None for a space or a
    line end, which separate words."""
    left, _, _, top = crop
    n = textpage.count_chars()
    text = textpage.get_text_range(0, n) if n else ""
    out: list[Char | None] = []
    for k in range(n):
        ch = text[k] if k < len(text) else ""
        if not ch.strip():
            out.append(None)
            continue
        x0, y0, x1, y1 = textpage.get_charbox(k)
        out.append(Char(_LINE_END_HYPHENS.get(ch, ch), x0 - left, top - y1, x1 - left, top - y0))
    return out


def _words(chars: list[Char | None]) -> list[list[Char]]:
    words: list[list[Char]] = []
    current: list[Char] = []
    for c in chars:
        # A word also ends where the next character starts back to the left or on
        # another line: the text layer does not always put a space there.
        if c is None or (current and (c.x0 < current[-1].x0 - 1
                                      or c.top > current[-1].bottom)):
            if current:
                words.append(current)
            current = [] if c is None else [c]
            continue
        current.append(c)
    if current:
        words.append(current)
    return words


def _box(chars: list[Char]) -> tuple[float, float, float, float]:
    return (min(c.x0 for c in chars), min(c.top for c in chars),
            max(c.x1 for c in chars), max(c.bottom for c in chars))


def _lines(words: list[list[Char]]) -> list[list[list[Char]]]:
    """Words grouped into printed lines, each left to right. A word joins the line whose
    letters its middle falls between; superscripts, raised above it, still do."""
    lines: list[list[list[Char]]] = []
    for word in sorted(words, key=lambda w: _box(w)[1]):
        x0, top, x1, bottom = _box(word)
        middle = (top + bottom) / 2
        for line in lines:
            ltop = statistics.median(_box(w)[1] for w in line)
            lbottom = statistics.median(_box(w)[3] for w in line)
            if ltop - 1 <= middle <= lbottom + 1:
                line.append(word)
                break
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: _box(w)[0]) for line in lines]


def _strip_superscripts(line: list[list[Char]], leaf: int,
                        log: list[NoteCall]) -> list[list[Char]]:
    # Measured on capitals and ascenders: the height a full-size digit has.
    tall = [c for w in line for c in w if c.text.isupper() or c.text in "bdfhklt"]
    feet = [c.bottom for w in line for c in w if c.text.isalpha() and c.text not in "gjpqy"]
    if not tall or not feet:
        return line
    height = statistics.median(c.height for c in tall)
    baseline = statistics.median(feet)
    out = []
    for word in line:
        keep = [c for c in word if not (c.text.isdigit() and c.height < SUPERSCRIPT_HEIGHT * height
                                        and c.bottom < baseline - SUPERSCRIPT_RAISE * height)]
        if len(keep) < len(word):
            log.append(NoteCall(leaf, "".join(c.text for c in word if c not in keep),
                                "".join(c.text for c in keep)))
        if keep:
            out.append(keep)
    return out


def read_pdf(path: str | Path, leaves: range, page_offset: int,
             note_calls: list[NoteCall] | None = None) -> list[Page]:
    """The PDF's pages whose index is in `leaves`, numbered `index - page_offset`."""
    import pypdfium2 as pdfium

    log = note_calls if note_calls is not None else []
    pdf = pdfium.PdfDocument(str(path))
    pages: list[Page] = []
    try:
        for leaf in leaves:
            page = pdf[leaf]
            crop = page.get_cropbox()
            width, height = crop[2] - crop[0], crop[3] - crop[1]
            out = Page(leaf, round(width * SCALE), round(height * SCALE),
                       number=str(leaf - page_offset))
            for line in _lines(_words(_chars(page.get_textpage(), crop))):
                line = _strip_superscripts(line, leaf, log)
                if not line:
                    continue
                words = tuple((_mended("".join(c.text for c in w)), round(_box(w)[0] * SCALE),
                               round(_box(w)[2] * SCALE)) for w in line)
                x0, top, x1, bottom = _box([c for w in line for c in w])
                out.lines.append(Line(" ".join(w[0] for w in words), round(x0 * SCALE),
                                      round(top * SCALE), round(x1 * SCALE),
                                      round(bottom * SCALE), words=words))
            pages.append(out)
    finally:
        pdf.close()
    return pages


def render_page(path: str | Path, leaf: int, dpi: int = 150):
    """The page image, as a PIL image, for the person's check."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        return pdf[leaf].render(scale=dpi / 72).to_pil()
    finally:
        pdf.close()
