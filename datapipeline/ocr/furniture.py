"""The script clean-up step: page furniture out, broken words mended, paragraphs kept.

Removed, by position and by patterns repeated across pages, and logged per page:
- running heads: the top line of a page when it carries the page's number, or when its
  letters recur as the top line of other pages;
- page numbers: a top or bottom line that is only a number;
- signature marks: a short letter-and-number mark on the bottom line ("B2", "12*"), or
  Bohn's ("VOL. II. G", "g2");
- catchwords: a single word alone at the bottom right that repeats the next page's first
  word;
- specks: a "line" with no letter or digit (a scan edge or a smudge read as "|"), and
  whatever stands above a page's running head (a pen mark read as "i re tne pee").

Notes at the foot of a page (a block that opens with a note marker after a gap, set
tighter than the body) are not deleted: they go to their own stream, so a sentence that
runs across a page break is not split by them, and the body text the gate measures does
not include them. A work whose notes the measure misses names the line that opens each
page's notes (`note_opens`), and a printed rule the OCR reads as letters by its line
(`rule_lines`).

A word broken across a line end ("ec-" / "clesiastical") is joined when the joined form
is in the word list or occurs unbroken elsewhere in the work; otherwise it keeps its
hyphen ("Anglo-Saxon"). Paragraph breaks come from indentation, a short line before a
capital, or extra space between lines. Each paragraph then goes through the shared
cleaner, `normalize.text.clean_text`.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from normalize.text import clean_text
from ocr.layout import Layout, SingleColumn
from ocr.pages import Line, Page
from ocr.words import fold, is_known, words

# Fractions of the page height that count as its top and bottom margins.
TOP_BAND = 0.07
# Some pages are scanned lower (Schroeder pp. 301–442, at up to 14%). A first line down to
# here is a running head only on firm evidence: the page's number, or letters that recur
# as a head.
HEAD_BAND = 0.18
# Lines that can stand above a running head as marks on the scan.
MARKS_ABOVE_HEAD = 3
BOTTOM_BAND = 0.80
# A running head recurs as the top line of at least this many pages.
REPEATED_HEAD_PAGES = 3
HEAD_SIMILARITY = 0.85
# Fractions of the page width: a first line indented this much opens a paragraph; a line
# ending this short of the right margin closes one.
INDENT = 0.018
SHORT_LINE = 0.12
# Fractions of the body line height.
PARAGRAPH_GAP = 0.6
NOTE_GAP = 0.35
# Note lines sit closer together than body lines.
NOTE_PITCH = 0.92
# Notes start below this fraction of the span from the page's first line to its last.
NOTE_REGION = 0.4
# A note carried over from the previous page starts in this bottom fraction of the page.
CARRIED_NOTE_BAND = 0.25

_PAGE_NUMBER = re.compile(r"^\W*(?:\d{1,4}|[ivxlcdm]{1,8})\W*$", re.IGNORECASE)
_SIGNATURE = re.compile(r"^(?=.*\w)[A-Z]{0,3}\s?\d{0,3}\s?\*?$")
# Bohn's signatures: "VOL. II. G" on a gathering's first leaf, "g2" on its third page.
_VOLUME_SIGNATURE = re.compile(r"^VOL\.?\s+[IVXL]+\.?\s+[A-Z]{1,2}\d?$|^[a-z]{1,2}\d$")
# A note opens with its number or symbol ("1 Mansi", "4Mention", "* See"); OCR often
# reads the superscript as a stray mark ("$For", "® Zorell"). Opening quotes and
# brackets are left out: body lines start with them.
_NOTE_START = re.compile(r"^(?:\d{1,2}|[^\w\s(\[“\"])\s?\S")
# A heading set apart at the foot of a page ("CANON 10") is never a note, even after a
# speck the OCR reads as a mark ("‘CANON 10", Schroeder p. 166).
_HEADING = re.compile(r"^\W{0,2}[A-Z]{4,}\s+[0-9IlO]{1,3}\W*$")
_HEAD_NUMBER = re.compile(r"^\d{1,4}\s+\D|\D\s+\d{1,4}$")
_LINE_END_BREAK = re.compile(r"([^\W\d_]+)[-¬]$")
_LINE_START_WORD = re.compile(r"^([^\W\d_]+)")
_HAS_ALNUM = re.compile(r"[^\W_]")
# A line ending a sentence or a clause, with any closing quotation mark or bracket after it.
_CLAUSE_END = re.compile(r"[.,;:?!][\"'”’)\]]*$")


@dataclass
class Removal:
    leaf: int
    page: str | None
    kind: str        # running_head | page_number | signature | catchword | speck |
                     # margin_number | note_call (`pdf.py`) | rule | watermark | edge_strip
    text: str


@dataclass
class HyphenBreak:
    leaf: int
    broken: str      # "ec-|clesiastical"
    result: str
    joined: bool
    reason: str      # word list | elsewhere in the work | kept: unknown | kept: capital


@dataclass
class Note:
    leaf: int
    page: str | None
    text: str


@dataclass
class Paragraph:
    text: str                 # script-cleaned
    raw: str                  # the OCR lines as read, one per line
    leaves: list[int]
    continues: bool = False   # cut from the paragraph before it at a sentence end


@dataclass
class CleanResult:
    paragraphs: list[Paragraph] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    removals: list[Removal] = field(default_factory=list)
    hyphens: list[HyphenBreak] = field(default_factory=list)


def _letters_key(text: str) -> str:
    return re.sub(r"[^A-Z]", "", text.upper())


def _first_word(text: str) -> str:
    m = _LINE_START_WORD.match(text.strip(" ‘’'\"“”"))
    return fold(m.group(1)) if m else ""


def _body_height(lines: list[Line], width: int) -> float:
    full = [ln.height for ln in lines if ln.x1 - ln.x0 > 0.6 * width] or [ln.height for ln in lines]
    return statistics.median(full) if full else 1.0


def _pitch(lines: list[Line]) -> float | None:
    steps = [b.top - a.top for a, b in zip(lines, lines[1:]) if b.top > a.top]
    return statistics.median(steps) if steps else None


class _Head:
    """Top-of-page lines recurring across the work: running heads."""

    def __init__(self, tops: list[str]):
        keys = [k for k in (_letters_key(t) for t in tops) if len(k) >= 4]
        # A key counts every top line close to it, so OCR variants add up.
        self.keys = [k for k in set(keys)
                     if sum(_similar(k, other) for other in keys) >= REPEATED_HEAD_PAGES]

    def repeated(self, text: str) -> bool:
        key = _letters_key(text)
        return len(key) >= 4 and any(_similar(key, k) for k in self.keys)


def _similar(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= HEAD_SIMILARITY


def _top_kind(line: Line, page: Page, heads: _Head) -> str | None:
    if _PAGE_NUMBER.match(line.text):
        return "page_number"
    tokens = line.text.split()
    if page.number and page.number in (tokens[0], tokens[-1]) and len(tokens) > 1:
        return "running_head"
    if heads.repeated(line.text):
        return "running_head"
    if _HEAD_NUMBER.search(line.text) and line.text == line.text.upper():
        return "running_head"
    return None


def _numbered_head(line: Line, page: Page) -> bool:
    tokens = line.text.split()
    return (line.top < HEAD_BAND * page.height and len(tokens) > 1
            and page.number in (tokens[0], tokens[-1]))


def _low_head(line: Line, page: Page, heads: _Head) -> bool:
    """A running head below the top band: the page's number at one end, or recurring."""
    return _numbered_head(line, page) or (line.top < HEAD_BAND * page.height
                                          and heads.repeated(line.text))


def _top_furniture(lines: list[Line], page: Page, heads: _Head) -> list[Removal]:
    """Take the running head, a page number set apart from it, and any mark above it off
    the top of `lines`."""
    out: list[Removal] = []

    def take(kind: str) -> None:
        out.append(Removal(page.leaf, page.number, kind, lines.pop(0).text))

    # Marks stand above a head only where the head is sure: it carries the page's number.
    # A council's title page has none, and its title lines stay.
    above = 0 if lines and _low_head(lines[0], page, heads) else next(
        (k for k, ln in enumerate(lines[:MARKS_ABOVE_HEAD + 1]) if _numbered_head(ln, page)), 0)
    for _ in range(above):
        take("speck")
    if not lines:
        return out
    if lines[0].top < TOP_BAND * page.height:
        kind = _top_kind(lines[0], page, heads)
        if kind:
            take(kind)
    elif _low_head(lines[0], page, heads):
        take("running_head")
    else:
        return out
    if out and out[-1].kind == "running_head" and lines and _PAGE_NUMBER.match(lines[0].text) \
            and lines[0].top < HEAD_BAND * page.height:
        take("page_number")
    return out


def _bottom_kind(line: Line, page: Page, next_first: str) -> str | None:
    text = line.text.strip()
    if _PAGE_NUMBER.match(text):
        return "page_number"
    if (len(text.split()) == 1 and line.x0 > page.width / 2 and next_first
            and _first_word(text) == next_first):
        return "catchword"
    if (len(text) <= 8 and _SIGNATURE.match(text)) or _VOLUME_SIGNATURE.match(text):
        return "signature"
    return None


def _usual_gap(lines: list[Line]) -> float:
    """The usual space between lines where their boxes are tight to the letters, as in a
    PDF's text layer (its lines carry their words): a note's or a paragraph's extra space
    is measured beyond it. The djvu's line boxes leave little space, so it is 0 there."""
    if not lines or not lines[0].words:
        return 0
    return statistics.median([max(0, b.top - a.bottom) for a, b in zip(lines, lines[1:])] or [0])


def _split_notes(lines: list[Line], page: Page, after_note: bool) -> tuple[list[Line], list[Line]]:
    """(body, notes): the block at the foot of the page that opens with a note marker
    after a gap and is set tighter than the body, or that continues a note from the
    previous page."""
    if len(lines) < 2:
        return lines, []
    height = _body_height(lines, page.width)
    # Notes sit in the lower part of the printed text, which on a short last page can be
    # well above the middle of the image.
    floor = lines[0].top + NOTE_REGION * (lines[-1].bottom - lines[0].top)
    usual = _usual_gap(lines)
    for i in range(1, len(lines)):
        line, prev = lines[i], lines[i - 1]
        if line.top < floor:
            continue
        gap = line.top - prev.bottom
        block, body = lines[i:], lines[:i]
        block_pitch, body_pitch = _pitch(block), _pitch(body)
        tighter = (block_pitch is not None and body_pitch is not None
                   and block_pitch < NOTE_PITCH * body_pitch)
        if len(block) == 1:
            tighter = gap - usual > NOTE_GAP * height
        # A note carried over from the previous page has no marker; it must then be the
        # foot of the page and start at the left margin, not a centred heading.
        carried = (after_note and line.top > page.height * (1 - CARRIED_NOTE_BAND)
                   and line.x0 - min(ln.x0 for ln in body[-3:]) < INDENT * page.width)
        opens = (bool(_NOTE_START.match(line.text)) or carried) and not _HEADING.match(line.text)
        if opens and gap > NOTE_GAP * height and tighter:
            return body, block
    return lines, []


# A number printed in the margin beside a line (Denzinger's numbers in Deferrari: "336",
# "2147a"). An article's own number ("6.") stands inside the text block and stays.
_MARGIN_NUMBER = re.compile(r"^\d{3,4}[a-z]?$")
# How far outside the text block a margin number stands at least, as a fraction of the
# page width.
MARGIN_SLACK = 0.004


def _strip_margin_numbers(lines: list[Line], page: Page) -> tuple[list[Line], list[Removal]]:
    """`lines` without the numbers standing outside the text block, which needs each
    line's words (`pdf.py`). A line left with no words goes."""
    # The text block's edges, measured without the numbers: on a page of a numbered list
    # most full lines open with one (Wyclif's articles, p. 210).
    full = [words for words in (tuple(w for w in ln.words if not _MARGIN_NUMBER.match(w[0]))
                                for ln in lines) if len(words) >= 6]
    if not full:
        return lines, []
    left = statistics.median(words[0][1] for words in full) - MARGIN_SLACK * page.width
    right = statistics.median(words[-1][2] for words in full) + MARGIN_SLACK * page.width
    kept, removed = [], []
    for ln in lines:
        margin = [w for w in ln.words if _MARGIN_NUMBER.match(w[0]) and (w[2] < left or w[1] > right)]
        if not margin:
            kept.append(ln)
            continue
        removed.extend(Removal(page.leaf, page.number, "margin_number", w[0]) for w in margin)
        rest = tuple(w for w in ln.words if w not in margin)
        if rest:
            kept.append(replace(ln, text=" ".join(w[0] for w in rest), x0=rest[0][1],
                                x1=rest[-1][2], words=rest, numbered=True))
    return kept, removed


def _continues_word(prev: Line, line: Line) -> bool:
    return bool(_LINE_END_BREAK.search(prev.text) and _LINE_START_WORD.match(line.text))


def _paragraph_starts(lines: list[Line], width: int, page_start: list[bool],
                      broken_words_continue: bool = False) -> list[bool]:
    """For each line, whether it opens a paragraph. `page_start[i]` marks a line that is
    the first body line of its page. With `broken_words_continue`, the rest of a word
    broken at the line end never opens one: some scans misplace its box (Giles: "ration"
    read as indented after "delibe-")."""
    starts = []
    height = statistics.median([ln.height for ln in lines]) if lines else 1
    usual = _usual_gap(lines)
    for i, line in enumerate(lines):
        if i == 0:
            starts.append(True)
            continue
        prev = lines[i - 1]
        near = lines[max(0, i - 3):i] + lines[i + 1:i + 4]
        left = statistics.median([ln.x0 for ln in near]) if near else line.x0
        right = statistics.median([ln.x1 for ln in near]) if near else prev.x1
        if broken_words_continue and _continues_word(prev, line):
            starts.append(False)
            continue
        indented = line.x0 - left > INDENT * width
        prev_short = prev.x1 < right - SHORT_LINE * width
        capital = line.text[:1].isupper() or line.text[:1].isdigit()
        gap = (not page_start[i]) and line.top - prev.bottom - usual > PARAGRAPH_GAP * height
        starts.append(indented or gap or (prev_short and capital))
    return starts


def clean_pages(pages: list[Page], layout: Layout | None = None,
                broken_words_continue: bool = False,
                max_paragraph_words: int | None = None,
                margin_numbers: bool = False,
                paragraph_opens: tuple[str, ...] = (),
                rule_lines: tuple[str, ...] = (),
                note_opens: tuple[str, ...] = (),
                watermark: str | None = None) -> CleanResult:
    """The pages' body paragraphs, notes and removals. With `max_paragraph_words`, a
    paragraph is cut at the first line ending a sentence or a clause once it holds that
    many words, and the part after the cut `continues` it: a page-long paragraph is too
    much for one correction call or one check against the page images.

    `paragraph_opens` are patterns, each matching the start of exactly one line, that
    open a paragraph the clean-up would join to the one before: a decree whose heading
    the OCR lost and whose first line opens a page (Basel's decree 3, p. 475). One that
    matches no line, or more than one, raises.

    `watermark` is a pattern for a stamp the scanner put on the pages, not the printer
    ("Digitized by Google" on a Google scan, 1.3d): each match is taken out of the line it
    was read into, and a line left with no letters goes, each logged as a `watermark`.

    `rule_lines` and `note_opens` take patterns the same way. A rule line is a printed rule
    the OCR reads as letters ("ee SS ---ς-ς---", Chrystal), removed as furniture. A
    `note_opens` line opens its page's notes, which then run to the page's end, in place
    of the measure of gaps and line spacing: Chrystal sets his notes almost the size of
    his text, and a note carried over from the page before opens with no marker."""
    layout = layout or SingleColumn()
    result = CleanResult()
    ordered = [layout.reading_order(p) for p in pages]
    # The long s is a letter form of s, not a letter: a printing set before about 1800
    # (Diu Satis, 1.3d) is read with it written out, as the ligatures are.
    ordered = [[replace(ln, text=ln.text.replace("ſ", "s")) if "ſ" in ln.text else ln
                for ln in lines] for lines in ordered]
    if watermark:
        stamp = re.compile(watermark)
        for k, page in enumerate(pages):
            kept_lines = []
            for ln in ordered[k]:
                if stamp.search(ln.text):
                    result.removals.append(Removal(page.leaf, page.number, "watermark", ln.text))
                    text = re.sub(r"\s{2,}", " ", stamp.sub(" ", ln.text)).strip()
                    if not _HAS_ALNUM.search(text):
                        continue
                    ln = replace(ln, text=text)
                kept_lines.append(ln)
            ordered[k] = kept_lines
    if margin_numbers:
        for k, page in enumerate(pages):
            ordered[k], removed = _strip_margin_numbers(ordered[k], page)
            result.removals.extend(removed)

    tops = [lines[0].text for p, lines in zip(pages, ordered)
            if lines and lines[0].top < HEAD_BAND * p.height]
    heads = _Head(tops)

    # Top furniture first, so each page's first body word is known for catchwords.
    rules = _one_line_each(rule_lines, ordered, "rule_lines")
    opens = _one_line_each(note_opens, ordered, "note_opens")
    kept: list[list[Line]] = []
    for page, lines in zip(pages, ordered):
        lines = list(lines)
        for line in [ln for ln in lines if not _HAS_ALNUM.search(ln.text)]:
            result.removals.append(Removal(page.leaf, page.number, "speck", line.text))
            lines.remove(line)
        for line in [ln for ln in lines if id(ln) in rules]:
            result.removals.append(Removal(page.leaf, page.number, "rule", line.text))
            lines.remove(line)
        for removal in _top_furniture(lines, page, heads):
            result.removals.append(removal)
        kept.append(lines)

    bodies: list[list[Line]] = []
    after_note = False
    for i, (page, lines) in enumerate(zip(pages, kept)):
        next_first = _first_word(kept[i + 1][0].text) if i + 1 < len(kept) and kept[i + 1] else ""
        while lines and lines[-1].bottom > BOTTOM_BAND * page.height:
            kind = _bottom_kind(lines[-1], page, next_first)
            if not kind:
                break
            result.removals.append(Removal(page.leaf, page.number, kind, lines.pop().text))
        if note_opens:
            k = next((k for k, ln in enumerate(lines) if id(ln) in opens), len(lines))
            body, notes = lines[:k], lines[k:]
        else:
            body, notes = _split_notes(lines, page, after_note)
        if notes:
            result.notes.append(Note(page.leaf, page.number, "\n".join(ln.text for ln in notes)))
        after_note = bool(notes)
        bodies.append(body)

    # Words that occur unbroken anywhere in the body: evidence for joining a break.
    seen = Counter(fold(w) for body in bodies for ln in body for w in words(ln.text))

    flat: list[tuple[Page, Line]] = []
    starts: list[bool] = []
    for page, body in zip(pages, bodies):
        if not body:
            continue
        page_starts = _paragraph_starts(body, page.width, [j == 0 for j in range(len(body))],
                                        broken_words_continue)
        if flat:
            # A page's first line continues the previous page's paragraph unless indented.
            near = body[1:4]
            left = statistics.median([ln.x0 for ln in near]) if near else body[0].x0
            page_starts[0] = body[0].x0 - left > INDENT * page.width and not (
                broken_words_continue and _continues_word(flat[-1][1], body[0]))
        # Denzinger's margin number stands beside the first line of the text it numbers,
        # so that line opens a paragraph: in a list, item after item (Wyclif's articles).
        page_starts = [s or ln.numbered for s, ln in zip(page_starts, body)]
        flat.extend((page, ln) for ln in body)
        starts.extend(page_starts)

    opened = _one_line_each(paragraph_opens, [[ln for _, ln in flat]], "paragraph_opens")
    starts = [s or id(ln) in opened for s, (_, ln) in zip(starts, flat)]

    current: list[tuple[Page, Line]] = []
    continues = False
    for k, (page, line) in enumerate(flat):
        if starts[k] and current:
            result.paragraphs.append(_paragraph(current, seen, result.hyphens, continues))
            current, continues = [], False
        current.append((page, line))
        if (max_paragraph_words and k + 1 < len(flat) and not starts[k + 1]
                and _CLAUSE_END.search(line.text)
                and sum(len(ln.text.split()) for _, ln in current) >= max_paragraph_words):
            result.paragraphs.append(_paragraph(current, seen, result.hyphens, continues))
            current, continues = [], True
    if current:
        result.paragraphs.append(_paragraph(current, seen, result.hyphens, continues))
    return result


def _one_line_each(patterns: tuple[str, ...], pages: list[list[Line]], what: str) -> set[int]:
    """The ids of the lines `patterns` name, each pattern matching the start of exactly
    one line of `pages`; one that matches none, or more than one, raises."""
    out: set[int] = set()
    for pattern in patterns:
        hits = [ln for lines in pages for ln in lines if re.match(pattern, ln.text)]
        if len(hits) != 1:
            raise ValueError(f"{what} {pattern!r} matches {len(hits)} lines, not one")
        out.add(id(hits[0]))
    return out


def _paragraph(lines: list[tuple[Page, Line]], seen: Counter, log: list[HyphenBreak],
               continues: bool = False) -> Paragraph:
    text = ""
    for k, (page, line) in enumerate(lines):
        piece = line.text.strip()
        if not text:
            text = piece
            continue
        broken = _LINE_END_BREAK.search(text)
        start = _LINE_START_WORD.match(piece)
        if broken and start:
            head, tail = broken.group(1), start.group(1)
            joined = head + tail
            if tail[0].isupper():
                ok, reason = False, "kept: capital"
            elif is_known(joined):
                ok, reason = True, "word list"
            elif seen.get(fold(joined)):
                ok, reason = True, "elsewhere in the work"
            else:
                ok, reason = False, "kept: unknown"
            stem = text[:broken.start(1)]
            result = (joined if ok else f"{head}-{tail}")
            log.append(HyphenBreak(page.leaf, f"{head}-|{tail}", result, ok, reason))
            text = stem + result + piece[start.end(1):]
        else:
            text = f"{text} {piece}"
    leaves = sorted({page.leaf for page, _ in lines})
    raw = "\n".join(line.reading for _, line in lines)
    return Paragraph(clean_text(text), raw, leaves, continues)


def _joined(parts: list[tuple[str, bool]]) -> str:
    """Paragraphs joined by a blank line, and a part cut at a sentence end back onto the
    one before it."""
    out = ""
    for k, (text, continues) in enumerate(parts):
        out += ("" if not k else " " if continues else "\n\n") + text
    return out


def page_map_agreement(removals: list[Removal]) -> tuple[int, int]:
    """(agree, read): of the running heads and page numbers removed that hold a number,
    how many hold the number the page map gives their page. The page map is keyed by
    leaf, so a scan whose djvu pages and leaves are out of step shows up here."""
    agree = read = 0
    for r in removals:
        nums = re.findall(r"\b\d{1,4}\b", r.text) if r.kind in ("running_head", "page_number") else []
        if nums:
            read += 1
            agree += r.page in nums
    return agree, read


def clean_work(workdir, sources=None, force: bool = False,
               passage_words: int | None = None) -> CleanResult:
    """Read the work's pages, clean them, and write its passages and clean-up log.
    Cleaning again replaces the passages, so it refuses once any has been corrected,
    unless `force`."""
    from dataclasses import asdict

    from ocr.layout import get_layout
    from ocr.pages import leaves_for_pages, load_pages, read_page_numbers
    from ocr.units import get_units
    from ocr.work import PASSAGE_WORDS, SOURCES, OcrPassage, group_passages

    config = workdir.config
    sources = sources or SOURCES
    if not force and any(p.correction.status != "pending" for p in workdir.passages()):
        raise RuntimeError(f"{config.work}: passages already corrected; clean again with force")
    note_calls = []
    if config.pdf:
        from ocr.pdf import read_pdf
        first, last = (int(n) + config.pdf_page_offset for n in config.pages)
        pages = read_pdf(sources / config.pdf, range(first, last + 1), config.pdf_page_offset,
                         note_calls)
    elif config.leaf_pages:
        # A scan with no page map, or one that leaves out a page the work needs: the
        # work names each leaf's printed page itself (1.3d).
        numbers = {int(leaf): page for leaf, page in config.leaf_pages.items()}
        leaves = leaves_for_pages(numbers, *config.pages)
        pages = load_pages(sources / config.djvu_xml, None, leaves)
        for page in pages:
            page.number = numbers.get(page.leaf)
    else:
        numbers_path = sources / config.page_numbers
        leaves = leaves_for_pages(read_page_numbers(numbers_path, config.leaf_offset), *config.pages)
        pages = load_pages(sources / config.djvu_xml, numbers_path, leaves, config.leaf_offset)
    if config.only_pages:
        # A printing that sets a translation on the pages facing its original (the
        # Dublin Review's Latin and English, 1.3d) reads only the translation's pages.
        missing = set(config.only_pages) - {p.number for p in pages}
        if missing:
            raise ValueError(f"{config.work}: only_pages {sorted(missing)} are not in its pages")
        pages = [p for p in pages if p.number in config.only_pages]
    strips: list[Removal] = []
    if config.edge_strip:
        # The cut-off lines of the page before, which the frame caught at its left edge
        # (the Archbishop of Quebec's pastoral on microfiche, 1.3d).
        for page in pages:
            edge = config.edge_strip * page.width
            strips += [Removal(page.leaf, page.number, "edge_strip", ln.text)
                       for ln in page.lines if ln.x0 < edge]
            page.lines = [ln for ln in page.lines if ln.x0 >= edge]
    result = clean_pages(pages, get_layout(config.layout), config.broken_words_continue,
                         config.max_paragraph_words, config.margin_numbers,
                         config.paragraph_opens, config.rule_lines, config.note_opens,
                         config.watermark)
    result.removals.extend(strips)
    number = {p.leaf: p.number for p in pages}
    result.removals.extend(Removal(c.leaf, number[c.leaf], "note_call", f"{c.after}|{c.text}")
                           for c in note_calls)
    agree, read = page_map_agreement(result.removals)
    # A work that names its leaves' pages itself (`leaf_pages`) was set from the images;
    # small page numbers in parentheses the OCR misreads do not overrule it (Diu Satis).
    if read and agree * 2 < read and not config.leaf_pages:
        raise RuntimeError(
            f"{config.work}: the page numbers printed on the pages agree with "
            f"{config.page_numbers} on only {agree} of {read} pages; the scan's images and "
            "its page map are out of step")
    if config.units:
        units = get_units(config.units).split(result.paragraphs, config.unit_series,
                                                config.unit_closes, config.unit_bounds)
        if config.unit_count is not None and len(units) != config.unit_count:
            raise RuntimeError(f"{config.work}: {len(units)} units read, the work prints "
                               f"{config.unit_count}")
        groups = [(u.id, u.paragraphs) for u in units]
    else:
        groups = [(f"{i:04d}", group) for i, group in enumerate(
            group_passages(result.paragraphs, passage_words or PASSAGE_WORDS), 1)]
    passages = []
    for passage_id, group in groups:
        leaves_ = sorted({leaf for para in group for leaf in para.leaves})
        passages.append(OcrPassage(
            id=passage_id, leaves=leaves_, pages=[number[x] for x in leaves_],
            raw_ocr=_joined([(para.raw, para.continues) for para in group]),
            cleaned=_joined([(para.text, para.continues) for para in group]),
            continues=group[0].continues, cut=group[0].continues))
    workdir.save_passages(passages)
    workdir.save_cleanup({
        "pages": [{"leaf": p.leaf, "page": p.number} for p in pages],
        "page_map": {"agree": agree, "read": read},
        "removals": [asdict(r) for r in result.removals],
        "hyphens": [asdict(h) for h in result.hyphens],
        "notes": [asdict(n) for n in result.notes],
    })
    return result
