"""A papal document published only as a PDF (corpus-cleanup 5.4): Amoris Laetitia, whose
English vatican.va gives only as the printed booklet's PDF (R6; Carter, 5 Oct 2026).

`soup` reads the PDF's text layer with pypdfium2 and writes the document as the plain
HTML the papal parser reads (`papal_common.tokens`): one `<p>` per printed paragraph, an
`<h2>` for a chapter's number and for its title, `<h3>` and `<h4>` for the two tiers of
headings inside a chapter. The parser then builds it as it builds any vatican.va page.

The booklet's text layer is born digital, not OCR, so nothing is corrected. What a line
is, it tells by the size its glyphs are drawn at (`Layout`):

- the body text, and the headings at their own sizes;
- the notes at the foot of each page, at a smaller size: left out, as the parser leaves
  out a page's endnotes;
- the note callers, superscript digits smaller still: dropped from the line they sit in;
- the running page number (a line holding only the page's own number), the title page, the
  "* * *" between sections and the index of contents after the text: left out.

A printed paragraph starts at a numbered line ("31. The welfare …"), or at a line set in
from the margin after a line that stops short of it; any other line runs on, verse lines
included, as the parser joins a `<p>`'s lines. A word broken at a line end carries the
text layer's mark (U+FFFE) and is joined again. A line the text layer splits at a note
caller is one printed line, told by its baseline.
"""
from __future__ import annotations

import ctypes
import html
import re
from collections import Counter
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# The text layer's mark for a hyphen at a line end, kept through the line join as a soft
# hyphen until `_joined` decides it.
_LINE_END_HYPHEN = "\ufffe"
_HELD = "\u00ad"
_HELD_JOIN = re.compile(r"(\w+)\u00ad\s*(\w+)")
_NUMBERED = re.compile(r"^(\d{1,3})\.\s")
# A line set in from the page's margin by more than this opens a paragraph.
_INDENT = 12.0
# A line ending this far short of the right margin ends a paragraph (or a verse line).
_SHORT = 15.0
# Two parts of one printed line, split by the text layer at a note caller.
_SAME_BASELINE = 3.0
# A line that is only a separator between sections.
_SEPARATOR = re.compile(r"^[*\s]+$")


@dataclass(frozen=True)
class Layout:
    """The sizes (the text matrix's vertical scale, rounded to 0.1) a booklet draws each
    kind of line at, and the page its text starts on (1-based)."""
    body: float
    chapter: float              # "CHAPTER ONE"; its title follows at body size, in small caps
    heading: float              # a section heading inside a chapter
    subheading: float           # a heading one tier below
    notes: frozenset[float]     # the notes at a page's foot
    callers_below: float        # a digit drawn smaller than this is a note caller
    index: str                  # the heading of the contents printed after the text
    first_page: int
    small_caps: str = "SC700"   # a font whose name holds this sets the chapter titles
    # Words the booklet breaks at a line end with an ordinary hyphen, not the text
    # layer's mark, as joined (printed, word); every other hyphen there is kept.
    broken_words: tuple[tuple[str, str], ...] = ()
    # The text layer marks every hyphen at a line end alike, a printer's break or a
    # compound's own; a mark is a break, and the word is joined, except in these
    # compounds, each two words the dictionary knows that do not make one.
    compounds: tuple[str, ...] = ()


# Amoris Laetitia (2016), vatican.va's PDF of the Vatican Press booklet, 264 pages.
AMORIS_LAETITIA = Layout(body=13.0, chapter=9.0, heading=8.8, subheading=12.8,
                         notes=frozenset({10.0, 7.0}), callers_below=8.0, index="INDEX",
                         first_page=3, broken_words=(("deep-est", "deepest"),),
                         compounds=("self-giving", "God-given", "age-old", "self-absorption",
                                    "self-control", "never-ending"))
LAYOUTS = {"amoris-laetitia": AMORIS_LAETITIA}


@dataclass
class Line:
    page: int
    text: str
    size: float
    font: str
    x0: float
    x1: float
    baseline: float
    italic: float = 0.0     # the share of its letters set in an italic font


@dataclass
class _Block:
    tag: str
    lines: list[str] = field(default_factory=list)

    def text(self) -> str:
        out = ""
        for line in self.lines:
            line = line.strip()
            if not out:
                out = line
            elif out.endswith("-") and not out.endswith(" -"):
                out += line            # a compound broken at its own hyphen
            else:
                out += " " + line
        return " ".join(out.split())


def read_lines(path: str, first_page: int = 1, callers_below: float = 0.0) -> list[Line]:
    """Every printed line from `first_page` on, in reading order, with any digit drawn
    smaller than `callers_below` (a note caller) dropped, a hyphen at a line end held as a
    soft hyphen for `_joined`, and a line split at a note caller joined again. Also read
    by `ingest/universal_law.py`."""
    return _merge_split(_lines(path, first_page, callers_below))


def _lines(path: str, first_page: int, callers_below: float) -> list[Line]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    out: list[Line] = []
    name = ctypes.create_string_buffer(256)
    pdf = pdfium.PdfDocument(path)
    try:
        for index in range(first_page - 1, len(pdf)):
            textpage = pdf[index].get_textpage()
            n = textpage.count_chars()
            text = textpage.get_text_range(0, n) if n else ""
            chars: list[tuple[str, float, str, tuple]] = []

            def close() -> None:
                kept = [c for c in chars if c[0].strip()]
                if kept:
                    sizes = Counter(c[1] for c in kept)
                    fonts = Counter(c[2] for c in kept)
                    size = sizes.most_common(1)[0][0]
                    # The text layer runs a line ending in a hyphen on into the next
                    # printed line; the baseline is the last printed line's.
                    held = max((i for i, c in enumerate(kept) if c[0] == _HELD), default=-1)
                    body = [c for c in kept[held + 1:] if c[1] == size] or kept
                    out.append(Line(
                        index + 1, "".join(c[0] for c in chars), size,
                        fonts.most_common(1)[0][0], min(c[3][0] for c in kept),
                        max(c[3][2] for c in kept),
                        sorted(c[3][1] for c in body)[len(body) // 2],
                        sum("Italic" in c[2] for c in kept) / len(kept)))
                chars.clear()

            for k in range(n):
                ch = text[k] if k < len(text) else ""
                if ch == "\n":
                    close()
                    continue
                if ch == "\r":
                    continue
                if ch == _LINE_END_HYPHEN:
                    ch = _HELD
                matrix = raw.FS_MATRIX()
                raw.FPDFText_GetMatrix(textpage.raw, k, ctypes.byref(matrix))
                size = round(abs(matrix.d), 1)
                if ch.isdigit() and size < callers_below:
                    continue                   # a note caller
                raw.FPDFText_GetFontInfo(textpage.raw, k, name, 256, None)
                chars.append((ch, size, name.value.decode("latin-1"),
                              textpage.get_charbox(k)))
            close()
    finally:
        pdf.close()
    return out


def _merge_split(lines: list[Line]) -> list[Line]:
    """A line the text layer split at a note caller is joined again: same page, same
    baseline, starting to the right of where the first part ends."""
    out: list[Line] = []
    for line in lines:
        prev = out[-1] if out else None
        if (prev is not None and prev.page == line.page and prev.size == line.size
                and abs(prev.baseline - line.baseline) < _SAME_BASELINE
                and line.x0 >= prev.x1 - 1):
            out[-1] = Line(prev.page, prev.text.rstrip() + " " + line.text.strip(),
                            prev.size, prev.font, prev.x0, line.x1, prev.baseline,
                            min(prev.italic, line.italic))
        else:
            out.append(line)
    return out


def blocks(path: str, layout: Layout) -> list[_Block]:
    """The document's headings and paragraphs, in order, as `_Block`s."""
    lines = read_lines(path, layout.first_page, layout.callers_below)
    body = [ln for ln in lines if ln.size == layout.body]
    margin = {p: Counter(round(ln.x0) for ln in body if ln.page == p).most_common(1)[0][0]
              for p in {ln.page for ln in body}}
    right = {p: Counter(round(ln.x1) for ln in body if ln.page == p).most_common(1)[0][0]
             for p in margin}
    out: list[_Block] = []
    expected = 1
    prev: Line | None = None
    title: _Block | None = None       # a chapter's title, read after its number
    alone = False                     # the last block is a line that stands alone
    for i, line in enumerate(lines):
        text = line.text.strip()
        if text == str(line.page):
            continue                       # the running page number, head or foot
        if text == layout.index:
            break
        if line.size in layout.notes or not text or _SEPARATOR.match(text):
            continue
        last = out[-1] if out else None
        if line.size == layout.chapter:
            out.append(_Block("h2", [text]))
            title = _Block("h2")
        elif title is not None and line.size == layout.body and layout.small_caps in line.font:
            if not title.lines:
                out.append(title)
            title.lines.append(text)       # one heading over the title's lines
        elif line.size in (layout.heading, layout.subheading):
            title = None
            tag = "h3" if line.size == layout.heading else "h4"
            if last is not None and last.tag == tag and prev is not None \
                    and prev.size == line.size:
                last.lines.append(text)    # a heading set over two lines
            else:
                out.append(_Block(tag, [text]))
        elif line.size == layout.body:
            title = None
            m = _NUMBERED.match(text)
            numbered = m is not None and int(m[1]) == expected
            if numbered:
                expected += 1
            indented = line.x0 > margin[line.page] + _INDENT
            short = line.x1 < right[line.page] - _SHORT
            after_short = prev is not None and prev.size == layout.body and (
                prev.x1 < right[prev.page] - _SHORT)
            # A short line set wholly in italic between lines in roman stands alone: the
            # title of the closing prayer, not a line of a poem quoted in italics.
            following = lines[i + 1] if i + 1 < len(lines) else None
            titled = (after_short and short and line.italic == 1.0 and prev.italic < 1.0
                      and following is not None and following.italic < 1.0)
            if numbered or last is None or last.tag != "p" or alone or titled \
                    or (indented and after_short):
                out.append(_Block("p", [text]))
            else:
                last.lines.append(text)
            alone = titled
        else:
            raise ValueError(f"page {line.page}: a line at size {line.size} the layout "
                             f"does not name: {text[:60]!r}")
        prev = line
    return out


def _joined(text: str, layout: Layout) -> str:
    """`text` with each word broken at a line end joined, or hyphenated where the layout
    names the compound."""
    def join(m: re.Match) -> str:
        hyphenated = f"{m[1]}-{m[2]}"
        return hyphenated if hyphenated in layout.compounds else m[1] + m[2]
    return _HELD_JOIN.sub(join, text).replace(_HELD, "")


def html_text(path: str, layout: Layout) -> str:
    """The document as plain HTML in a vatican.va-like `div.documento`."""
    texts = [(b.tag, _joined(b.text(), layout)) for b in blocks(path, layout)]
    for compound in layout.compounds:
        if not any(compound in text for _, text in texts):
            raise ValueError(f"{compound!r} is not in the text: update the layout")
    for printed, word in layout.broken_words:
        found = sum(text.count(printed) for _, text in texts)
        if found != 1:
            raise ValueError(f"{printed!r} occurs {found} times, not once: update the layout")
        texts = [(tag, text.replace(printed, word)) for tag, text in texts]
    parts = [f"<{tag}>{html.escape(text)}</{tag}>" for tag, text in texts]
    return '<html><body><div class="documento">' + "".join(parts) + "</div></body></html>"


def soup(path: str, slug: str) -> BeautifulSoup:
    """The document a papal manifest entry names as a PDF, as the soup the papal parser
    reads. A PDF with no layout here stops the build."""
    if slug not in LAYOUTS:
        raise ValueError(f"{slug}: a PDF source needs its layout in ingest/papal_pdf.py")
    return BeautifulSoup(html_text(path, LAYOUTS[slug]), "lxml")
