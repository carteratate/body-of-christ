"""Catechism of the Catholic Church ingestion — three-tier page_node chunking.

Sources: structure from nossbigg/catechism-ccc-json (v0.0.2, vatican.va's English), words
and footnotes from the US edition (`us-edition/ccc-us.json`, issue #279). Before any
chunking, `ingest/catechism_us.align` puts the US text of every numbered paragraph and
heading into ccc.json's nodes; footnotes go to `metadata.footnotes`, never into content.

Three-tier strategy
-------------------
  Tier 1 (Stub):   No CCC paragraph numbers (any length).
                   Stub text is merged forward into the next non-stub node.
                   Nodes without CCC refs are structural (headers, TOC titles).
  Tier 2 (Normal): Has CCC paragraph numbers AND raw_text <= 4000 chars.
                   One chunk per node.
  Tier 3 (Large):  Has CCC paragraph numbers AND raw_text > 4000 chars.
                   Split at internal section headers; header-only split sections
                   with no CCC refs are skipped (trailing title, content follows
                   in the next node).

IN BRIEF rule: any chunk whose leading section header is exactly "IN BRIEF",
or whose raw_text begins with "IN BRIEF", is flagged is_in_brief=True.

Each numbered paragraph's text opens with its number, "§2267 " (1.6, Decision log
"Catechism paragraph markers (1.6)"), and each passage cites the paragraphs it holds.
Chapters are the source's Prologue, Parts, Sections, Chapters and Articles (`chapters`).
The 1997 text of §2267 is kept as an unsearchable history passage after the passage that
holds the 2018 text (rule F, D11).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from identity import PIECE_MARK, anchor as make_anchor  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from config import settings  # noqa: E402
from ingest.common import split_display_passage  # noqa: E402
from ingest import catechism_us  # noqa: E402
from ingest.catechism_headings import TEXT_FIXES, TITLE_FIXES  # noqa: E402
from ingest.pieces import RANGE, piece_reference  # noqa: E402
from normalize.caps import smart_title_case  # noqa: E402
from registry import ANCHOR_SCHEME, resolve_document_id  # noqa: E402

_DEFAULT_SRC = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "sources", "catechism", "ccc.json"
)

_STUB_THRESHOLD = 500
_LARGE_THRESHOLD = 4000
_HEADER_MAX_CHARS = 120


# ---------------------------------------------------------------------------
# Paragraph / element helpers
# ---------------------------------------------------------------------------

def marker(number: int) -> str:
    """What opens a numbered paragraph's text: "§2267 ", the form `unit_label` uses."""
    return f"§{number} "


def _para_text(paragraph: dict) -> str:
    """The paragraph's text, opened by its number's marker when the paragraph starts
    with a `ref-ccc` element (every numbered paragraph in the source does)."""
    parts: list[str] = []
    number = None
    for el in paragraph.get("elements", []):
        if el.get("type") == "text":
            t = el.get("text", "")
            if t:
                parts.append(t)
        elif el.get("type") == "ref-ccc" and not parts and el.get("ref_number") is not None:
            number = el["ref_number"]
    text = " ".join(parts).strip()
    return marker(number) + text if text and number is not None else text


def extract_node_text(node: dict) -> tuple[str, list[int]]:
    """Return (raw_text, ccc_paragraph_numbers) for a page_node."""
    para_texts: list[str] = []
    ccc_paragraphs: list[int] = []

    for para in node.get("paragraphs", []):
        for el in para.get("elements", []):
            if el.get("type") == "ref-ccc":
                ref = el.get("ref_number")
                if ref is not None:
                    ccc_paragraphs.append(ref)
        text = _para_text(para)
        if text:
            para_texts.append(text)

    return "\n\n".join(para_texts), ccc_paragraphs


def is_section_header(paragraph: dict) -> bool:
    """Return True if paragraph qualifies as an internal section header."""
    if "indent" in paragraph:
        return False
    if any(el.get("type") == "ref-ccc" for el in paragraph.get("elements", [])):
        return False
    text = _para_text(paragraph)
    return 0 < len(text) < _HEADER_MAX_CHARS and not text.endswith((":", ";"))


# ---------------------------------------------------------------------------
# Tier 3: split large nodes at section headers
# ---------------------------------------------------------------------------

def split_large_node(node: dict) -> list[tuple[str, list[int], bool]]:
    """Split a large node at internal section headers.

    Returns list of (section_text, ccc_paragraphs, is_in_brief).
    """
    sections: list[tuple[str, list[int], bool]] = []
    current_header: str | None = None
    current_body: list[str] = []
    current_paras: list[int] = []

    def _flush() -> None:
        lines: list[str] = []
        if current_header is not None:
            lines.append(current_header)
        lines.extend(current_body)
        text = "\n\n".join(lines).strip()
        if text:
            is_brief = current_header == "IN BRIEF"
            # list() snapshots current_paras; the name is reassigned (not mutated) after flush
            sections.append((text, list(current_paras), is_brief))

    for para in node.get("paragraphs", []):
        if is_section_header(para):
            if current_header is not None or current_body:
                _flush()
            current_header = _para_text(para)
            current_body = []
            current_paras = []
        else:
            for el in para.get("elements", []):
                if el.get("type") == "ref-ccc":
                    ref = el.get("ref_number")
                    if ref is not None:
                        current_paras.append(ref)
            text = _para_text(para)
            if text:
                current_body.append(text)

    if current_header is not None or current_body:
        _flush()

    return sections


# ---------------------------------------------------------------------------
# Reference formatting
# ---------------------------------------------------------------------------

def make_reference(ccc_paragraphs: list[int], node_id: str) -> str:
    """The citation of the paragraphs a passage holds: "CCC §N", "CCC §N–M" for a run,
    "CCC §N, §M" otherwise. Pieces that would share one get "(part 1 of 2)" from
    `piece_reference` in `build`."""
    if not ccc_paragraphs:
        return f"CCC [{node_id}]"

    if len(ccc_paragraphs) == 1:
        return f"CCC §{ccc_paragraphs[0]}"

    consecutive = all(
        ccc_paragraphs[i + 1] == ccc_paragraphs[i] + 1
        for i in range(len(ccc_paragraphs) - 1)
    )
    if consecutive:
        return f"CCC §{ccc_paragraphs[0]}{RANGE}{ccc_paragraphs[-1]}"

    joined = ", ".join(f"§{n}" for n in ccc_paragraphs)
    return f"CCC {joined}"


# ---------------------------------------------------------------------------
# Three-tier chunker
# ---------------------------------------------------------------------------

# "IN BRIEF" opening a node's text, behind a paragraph's "§N " if it is numbered.
_IN_BRIEF = re.compile(r"(?:§\d+ )?IN BRIEF")


def chunk_nodes(nodes: list[dict], node_ids: list[str]) -> list[tuple[str, str, dict, int]]:
    """Apply three-tier chunking strategy to an ordered list of page nodes."""
    chunks: list[tuple[str, str, dict, int]] = []
    position = 0
    pending_prefix = ""

    for node, node_id in zip(nodes, node_ids):
        raw_text, ccc_paragraphs = extract_node_text(node)

        # Tier 1 (Stub): no numbered CCC paragraphs — merge forward regardless of length.
        # Nodes without CCC paragraph refs are structural elements (headers, TOC titles)
        # that should prefix the next substantive chunk rather than stand alone.
        if len(ccc_paragraphs) == 0:
            if raw_text:
                pending_prefix = (
                    pending_prefix + "\n\n" + raw_text if pending_prefix else raw_text
                )
            continue

        prefix = pending_prefix
        pending_prefix = ""

        # Tier 3 (Large): split at internal section headers. The size is the text's
        # without its "§N " markers, so the markers (1.6) split no node that was whole.
        size = len(raw_text) - sum(len(marker(n)) for n in ccc_paragraphs)
        if size > _LARGE_THRESHOLD and len(ccc_paragraphs) > 0:
            sections = split_large_node(node)
            carry = prefix

            for i, (sec_text, sec_paras, is_brief) in enumerate(sections):
                # Unnumbered fragments are headings with nothing under them in this
                # node ("IN BRIEF" is the exception: its summary body is unnumbered and
                # stays its own flagged section). They head what follows, so they carry
                # forward rather than being dropped (#279: every heading's words reach
                # a passage).
                if not sec_paras and not is_brief:
                    carry = (carry + "\n\n" + sec_text).strip() if carry else sec_text
                    continue

                sec_content = (carry + "\n\n" + sec_text).strip() if carry else sec_text
                carry = ""

                ref = make_reference(sec_paras, node_id)
                meta: dict = {
                    "path": node_id,
                    "ccc_paragraphs": sec_paras,
                    "is_in_brief": is_brief,
                }
                chunks.append((sec_content, ref, meta, position))
                position += 1
            if carry:
                pending_prefix = carry           # the node ended on a heading
            continue

        # Tier 2 (Normal): one chunk per node
        content = (prefix + "\n\n" + raw_text).strip() if prefix else raw_text

        # If the first paragraph text is "IN BRIEF" (header or numbered), it appears
        # first in raw_text, so one match covers both cases.
        is_brief = bool(_IN_BRIEF.match(raw_text.lstrip()))

        ref = make_reference(ccc_paragraphs, node_id)
        meta = {
            "path": node_id,
            "ccc_paragraphs": ccc_paragraphs,
            "is_in_brief": is_brief,
        }
        chunks.append((content, ref, meta, position))
        position += 1

    # Trailing stubs with no subsequent non-stub node — emit as-is
    if pending_prefix:
        ref = make_reference([], "stub-tail")
        meta = {"path": "stub-tail", "ccc_paragraphs": [], "is_in_brief": False}
        chunks.append((pending_prefix, ref, meta, position))

    return chunks


_MIN_CONTENT = 30

# Paragraphs whose current text replaces, on purpose, the one users saw before, so the
# release report's stability check (0.1c) expects the change (1.6's identity rule).
TEXT_REPLACED = {2267: "2018 revision of CCC 2267"}


def _units(page_nodes: dict) -> list[tuple[str | None, str]]:
    """Every text the chunker can place, in reading order: (item key or None for a
    source line kept as printed, the text the chunker reads)."""
    out = []
    for node_id in catechism_us.ordered_node_ids(page_nodes):
        for paragraph in page_nodes[node_id].get("paragraphs", []):
            text = _para_text(paragraph)
            if text:
                out.append((paragraph.get("_item"), text))
    return out


class _Placement:
    """Where each item's text lands in the chunks, found moving forward only."""

    def __init__(self, units: list[tuple[str | None, str]]):
        self.units = units
        self.next = 0
        self.placed: list[tuple[str | None, int]] = []   # (key, unit index) per chunk
        self.dropped: list[tuple[str | None, str]] = []

    def place(self, clean: str) -> list[tuple[str | None, str, int]]:
        """(key, unit text, start in `clean`) for each unit `clean` holds, in order."""
        found = []
        cursor = 0
        while self.next < len(self.units):
            key, text = self.units[self.next]
            unit = clean_text(text)
            rest = clean[cursor:]
            lead = len(rest) - len(rest.lstrip())
            if unit and rest[lead:].startswith(unit):
                found.append((key, text, cursor + lead))
                cursor += lead + len(unit)
                self.next += 1
                continue
            if cursor == 0 and not found:
                # The chunker dropped this unit (a heading-only section): skip it.
                self.dropped.append((key, text))
                self.next += 1
                continue
            break
        if clean[cursor:].strip():
            detail = ""
            if self.next < len(self.units):
                key, text = self.units[self.next]
                unit, rest = clean_text(text), clean[cursor:].lstrip()
                d = next((i for i in range(min(len(unit), len(rest))) if unit[i] != rest[i]),
                         min(len(unit), len(rest)))
                detail = (f"; next unit {key!r} differs at {d}: "
                          f"{unit[max(0, d - 50):d + 30]!r} vs {rest[max(0, d - 50):d + 30]!r}")
            raise ValueError(f"catechism: passage text not accounted for: "
                             f"{clean[cursor:cursor + 80]!r}{detail}")
        return found


def _last_word(text: str) -> str | None:
    found = re.findall(r"[^\W_]+", text)
    return found[-1] if found else None


def _footnotes_for(items: dict, held: list[tuple[str | None, str, int]], clean: str) -> list[dict]:
    """Each footnote of the items a chunk holds, at its offset in the chunk's text."""
    notes = []
    for key, text, start in held:
        if key is None or key not in items:      # a source line kept as printed
            continue
        raw = items[key]["text"]         # the offsets are into the US text as fetched
        if items[key]["kind"] == "paragraph":
            start += len(marker(items[key]["n"]))    # the text opens with "§N "
        for note in items[key]["footnotes"]:
            x = start + len(clean_text(raw[:note["at"]]))
            want = _last_word(raw[:note["at"]])
            if want is not None and _last_word(clean[:x]) != want:
                raise ValueError(f"catechism: footnote {note['n']} of {key} lands after "
                                 f"{_last_word(clean[:x])!r}, not {want!r}")
            notes.append({"n": note["n"], "text": note["text"], "x": x})
    return notes


def _piece_spans(clean: str, pieces: list[str]) -> list[tuple[int, int]]:
    """Each piece's span in its passage text, found moving forward
    (`split_display_passage` keeps every word once, in order)."""
    spans, cursor = [], 0
    for piece in pieces:
        start = clean.find(piece, cursor)
        if start < 0:
            raise ValueError("catechism: a display piece is not in its passage text")
        spans.append((start, start + len(piece)))
        cursor = start + len(piece)
    return spans


def _cut(clean: str, held: list[tuple[str | None, str, int]]) -> list[tuple[int, int]]:
    """Each display piece's span in a chunk's text. The cuts are those of the text
    without its "§N " markers, so adding the markers (1.6) moves no piece boundary and
    no piece's ID: a marker at a cut opens the piece after it."""
    marks = []                            # (offset in the text without markers, length)
    removed = 0
    for key, _, start in held:
        m = _PARAGRAPH_KEY.match(key or "")
        if m and clean.startswith(marker(int(m[1])), start):
            marks.append((start - removed, len(marker(int(m[1])))))
            removed += marks[-1][1]
    bare, at = [], 0
    for b, length in marks:
        start = b + sum(n for x, n in marks if x < b)
        bare.append(clean[at:start])
        at = start + length
    bare.append(clean[at:])
    text = "".join(bare)

    def marked(offset: int) -> int:
        # Only markers before `offset` move it: one exactly at a cut is the first thing
        # in the piece after it.
        return offset + sum(n for b, n in marks if b < offset)

    pieces = split_display_passage(text, settings.MAX_PASSAGE_CHARS)
    return [(marked(lo), marked(hi)) for lo, hi in _piece_spans(text, pieces)]


def _split_notes(spans: list[tuple[int, int]], notes: list[dict]) -> list[list[dict]]:
    """Give each footnote to the piece holding its offset: start <= x <= end, and a
    marker exactly at a piece's end belongs to that piece, not the next."""
    out: list[list[dict]] = [[] for _ in spans]
    for note in notes:
        for k, (start, end) in enumerate(spans):
            if start <= note["x"] <= end:
                out[k].append({"n": note["n"], "text": note["text"], "at": note["x"] - start})
                break
        else:
            raise ValueError(f"catechism: footnote {note['n']} falls between pieces")
    return out


_PARAGRAPH_KEY = re.compile(r"^p(\d+)$")


def _paragraph_starts(held: list[tuple[str | None, str, int]]) -> list[tuple[int, str]]:
    """(offset, CCC number) where each numbered paragraph a chunk holds starts in its
    text. A heading or a kept source line belongs to the paragraph after it (to the one
    before it at the end of a chunk), so a piece opening at a heading is named by the
    paragraph the heading introduces."""
    starts: list[tuple[int, str]] = []
    pending = None
    for key, _, start in held:
        m = _PARAGRAPH_KEY.match(key or "")
        if m:
            starts.append((start if pending is None else pending, m[1]))
            pending = None
        elif pending is None:
            pending = start
    return starts


def _piece_names(unit: str, spans: list[tuple[int, int]],
                 held: list[tuple[str | None, str, int]]
                 ) -> list[tuple[str, tuple[tuple[str, int], ...]]]:
    """(anchor, source_units) for each piece of a chunk (2.1, C-10): the first piece takes
    the unit's anchor, a later one `<unit>/from-<CCC number it opens with>`, plus `-<k>`
    when it opens inside that paragraph (the paragraph's start counts as 1)."""
    starts = _paragraph_starts(held)
    out, cuts = [], {}
    for j, (lo, hi) in enumerate(spans):
        opening = [x for x in starts if x[0] <= lo]
        at, number = opening[-1] if opening else (starts[0] if starts else (0, unit))
        units = [(n, x - lo) for x, n in starts if lo <= x < hi]
        if at != lo:
            units.insert(0, (number, 0))
        if j == 0:
            anchor = unit
        elif at == lo:
            anchor = f"{unit}{PIECE_MARK}{number}"
        else:
            cuts[number] = cuts.get(number, 1) + 1
            anchor = f"{unit}{PIECE_MARK}{number}-{cuts[number]}"
        out.append((anchor, tuple(units)))
    return out


# ---------------------------------------------------------------------------
# Chapters: the source's Prologue, Parts, Sections, Chapters and Articles
# ---------------------------------------------------------------------------

_LEVEL = re.compile(r"^(PART|SECTION|CHAPTER|ARTICLE)\s+(ONE|TWO|THREE|FOUR|\d+)\b:?\s*(.*)$",
                    re.I)
_NUMBER_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4}


def heading_text(node_id: str, text: str) -> str:
    """A `toc_nodes` heading with the source's misprints corrected, from the table the
    stopgap contents tree also reads (`catechism_headings`)."""
    text = TITLE_FIXES.get(node_id, text)
    for wrong, right in TEXT_FIXES:
        text = text.replace(wrong, right)
    return " ".join(text.split())


def chapters(source: dict) -> dict[str, tuple[str, str]]:
    """(chapter_key, chapter_label) for every node of `toc_link_tree`: its nearest
    Prologue, Part, Section, Chapter or Article, itself included. The key is the path of
    levels ("ccc/part-3/section-2/chapter-2/article-5"), the label their names and the
    nearest one's title ("Part Three, Section Two, Chapter Two, Article 5, The Fifth
    Commandment"). Sub-headings ("I. Respect for Human Life", "IN BRIEF", "Paragraph 1.")
    belong to the chapter above them."""
    toc = source["toc_nodes"]
    out: dict[str, tuple[str, str]] = {}

    def visit(link: dict, path: tuple[str, ...], names: tuple[str, ...],
              here: tuple[str, str] | None) -> None:
        node_id = link["id"]
        text = heading_text(node_id, toc[node_id]["text"])
        m = _LEVEL.match(text)
        if text.upper() == "PROLOGUE":
            path, names = ("prologue",), ()
            here = (make_anchor("ccc", *path), "Prologue")
        elif m:
            level, word = m[1].lower(), m[2].upper()
            number = _NUMBER_WORDS.get(word) or int(word)
            path = path + (f"{level}-{number}",)
            names = names + (f"{level.capitalize()} {word.capitalize()}",)
            title = smart_title_case(m[3].strip())
            here = (make_anchor("ccc", *path), ", ".join(names + ((title,) if title else ())))
        if here is None:
            raise ValueError(f"catechism: heading {node_id} ({text!r}) is under no part")
        out[node_id] = here
        for child in link["children"]:
            visit(child, path, names, here)

    for link in source["toc_link_tree"]:
        visit(link, (), (), None)
    return out


# The 1997 text of §2267, replaced on 2 August 2018, is kept as history (rule F, D11).
HISTORY_1997 = 2267
HISTORY_1997_REFERENCE = "CCC §2267 (1997 text, in force until 2 August 2018)"


def _history_1997(old_text: str, current: Passage, position: int) -> Passage:
    """The 1997 text of §2267 as the source prints it (vatican.va's English, citation in
    brackets), after the passage holding its 2018 text and in its chapter."""
    return Passage(
        content=clean_text(marker(HISTORY_1997) + old_text),
        reference=HISTORY_1997_REFERENCE,
        anchor=f"{current.anchor}/history-1997",
        chapter_key=current.chapter_key, chapter_label=current.chapter_label,
        position=position, unit_label=f"§{HISTORY_1997}",
        metadata={"path": current.metadata["path"], "ccc_paragraphs": [HISTORY_1997],
                  "is_in_brief": False, "footnotes": []},
        searchable=False, superseded_by_anchor=current.anchor)


@dataclass
class Build:
    document: Document
    alignment: "catechism_us.Alignment"
    dropped: list[tuple[str | None, str]]   # units the chunker left out, for the report
    held: dict[str, list[str | None]]        # anchor -> item keys its text holds, in order


def build_document(source_path: str | None = None, us_path: str | None = None) -> Document:
    """Build the CCC as one Document of clean numbered passages (reuses the
    three-tier chunker, drops tiny TOC-only fragments, normalizes ellipses), with the
    US edition's words and footnotes."""
    return build(source_path, us_path).document


def build(source_path: str | None = None, us_path: str | None = None) -> Build:
    src = source_path or _DEFAULT_SRC
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    alignment = catechism_us.align(data, catechism_us.load_us(us_path or catechism_us.US_SOURCE))
    page_nodes = alignment.page_nodes

    ids = catechism_us.ordered_node_ids(page_nodes)
    raw_chunks = chunk_nodes([page_nodes[k] for k in ids], ids)  # (content, ref, meta, pos)
    placement = _Placement(_units(page_nodes))

    did = resolve_document_id("catechism", "catechism", ("catechism",))
    chapter_of = chapters(data)
    passages: list[Passage] = []
    pos = 0
    seen: set[str] = set()
    held_by: dict[str, list[str | None]] = {}
    for content, _, meta, _ in raw_chunks:
        clean = clean_text(content)
        held = placement.place(clean)
        if len(clean) < _MIN_CONTENT:
            placement.dropped.extend((key, text) for key, text, _ in held)
            continue                      # drop TOC-only fragments ("Article 2")
        notes = _footnotes_for(alignment.items, held, clean)
        paras = meta.get("ccc_paragraphs") or []
        first = paras[0] if paras else None
        chapter_key, chapter_label = chapter_of[meta["path"]]
        # A chunk with no numbered paragraph is anchored on its node's path in the source.
        base = make_anchor("ccc", first) if first else make_anchor("ccc", meta["path"])
        unit, k = base, 1
        while unit in seen:
            k += 1
            unit = f"{base}-{k}"
        spans = _cut(clean, held)
        pieces = [clean[lo:hi] for lo, hi in spans]
        named = _piece_names(unit, spans, held)
        # Each piece cites the paragraphs it holds: those opening in it, and the one it
        # continues. Pieces of one paragraph would cite alike, so they say which part.
        cited = [[int(n) for n, _ in units] if len(pieces) > 1 else paras
                 for _, units in named]
        refs = [make_reference(c, meta["path"]) for c in cited]
        shared = Counter(refs)
        part: Counter = Counter()
        for (piece, (lo, hi), piece_notes, (anchor, units), piece_paras, ref) in zip(
                pieces, spans, _split_notes(spans, notes), named, cited, refs):
            if shared[ref] > 1:
                part[ref] += 1
                ref = piece_reference(ref, None, None, part[ref], shared[ref])
            seen.add(anchor)
            piece_meta = {**meta, "ccc_paragraphs": piece_paras, "footnotes": piece_notes}
            held_by[anchor] = [key for key, text, start in held
                               if start < hi and start + len(clean_text(text)) > lo]
            replaced = [TEXT_REPLACED[n] for n in TEXT_REPLACED if f"p{n}" in held_by[anchor]]
            if replaced:
                piece_meta["text_replaced"] = "; ".join(replaced)
            passages.append(Passage(
                content=piece, reference=ref, anchor=anchor,
                chapter_key=chapter_key, chapter_label=chapter_label,
                position=pos, unit_label=(f"§{piece_paras[0]}" if piece_paras else None),
                metadata=piece_meta, source_units=units))
            pos += 1
            if any(key == f"p{HISTORY_1997}" and lo <= start < hi for key, _, start in held):
                passages.append(_history_1997(alignment.old_paragraphs[HISTORY_1997],
                                              passages[-1], pos))
                pos += 1
    if placement.next != len(placement.units):
        raise ValueError("catechism: text after the last passage was not placed")
    document = Document(id=did, collection="catechism",
                        title="Catechism of the Catholic Church", author="Catholic Church",
                        year=1992,
                        metadata={"source": "nossbigg/catechism-ccc-json (structure); "
                                            "US edition via catholiccrossreference.online "
                                            "(text and footnotes, us-edition/ccc-us.json)",
                                  "source_key": "catechism", "anchor_scheme": ANCHOR_SCHEME},
                        passages=passages)
    return Build(document, alignment, placement.dropped, held_by)

