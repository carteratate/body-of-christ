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
"""
from __future__ import annotations

import json
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

def _para_text(paragraph: dict) -> str:
    parts: list[str] = []
    for el in paragraph.get("elements", []):
        if el.get("type") == "text":
            t = el.get("text", "")
            if t:
                parts.append(t)
    return " ".join(parts).strip()


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

def make_reference(ccc_paragraphs: list[int], node_id: str, is_partial: bool = False) -> str:
    """Build a human-readable CCC reference string."""
    if not ccc_paragraphs:
        return f"CCC [{node_id}]"

    suffix = " (part)" if is_partial else ""

    if len(ccc_paragraphs) == 1:
        return f"CCC §{ccc_paragraphs[0]}{suffix}"

    consecutive = all(
        ccc_paragraphs[i + 1] == ccc_paragraphs[i] + 1
        for i in range(len(ccc_paragraphs) - 1)
    )
    if consecutive:
        return f"CCC §{ccc_paragraphs[0]}–{ccc_paragraphs[-1]}{suffix}"

    joined = ", ".join(f"§{n}" for n in ccc_paragraphs)
    return f"CCC {joined}{suffix}"


# ---------------------------------------------------------------------------
# Three-tier chunker
# ---------------------------------------------------------------------------

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

        # Tier 3 (Large): split at internal section headers
        if len(raw_text) > _LARGE_THRESHOLD and len(ccc_paragraphs) > 0:
            sections = split_large_node(node)
            n_sections = len(sections)
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

                is_partial = n_sections > 1
                ref = make_reference(sec_paras, node_id, is_partial=is_partial)
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
        # first in raw_text — so a single startswith covers both cases.
        is_brief = raw_text.lstrip().startswith("IN BRIEF")

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
    passages: list[Passage] = []
    pos = 0
    seen: set[str] = set()
    held_by: dict[str, list[str | None]] = {}
    for content, reference, meta, _ in raw_chunks:
        clean = clean_text(content)
        held = placement.place(clean)
        if len(clean) < _MIN_CONTENT:
            placement.dropped.extend((key, text) for key, text, _ in held)
            continue                      # drop TOC-only fragments ("Article 2")
        notes = _footnotes_for(alignment.items, held, clean)
        paras = meta.get("ccc_paragraphs") or []
        first = paras[0] if paras else None
        chapter_no = (first // 100) if first else 0
        # A chunk with no numbered paragraph is anchored on its node's path in the source.
        base = make_anchor("ccc", first) if first else make_anchor("ccc", meta["path"])
        unit, k = base, 1
        while unit in seen:
            k += 1
            unit = f"{base}-{k}"
        pieces = split_display_passage(clean, settings.MAX_PASSAGE_CHARS)
        spans = _piece_spans(clean, pieces)
        for (piece, (lo, hi), piece_notes, (anchor, units)) in zip(
                pieces, spans, _split_notes(spans, notes), _piece_names(unit, spans, held)):
            seen.add(anchor)
            piece_meta = {**meta, "footnotes": piece_notes}
            held_by[anchor] = [key for key, text, start in held
                               if start < hi and start + len(clean_text(text)) > lo]
            replaced = [TEXT_REPLACED[n] for n in TEXT_REPLACED if f"p{n}" in held_by[anchor]]
            if replaced:
                piece_meta["text_replaced"] = "; ".join(replaced)
            passages.append(Passage(
                content=piece, reference=reference, anchor=anchor,
                chapter_key=make_anchor("ccc", "part", str(chapter_no)),
                chapter_label=(f"CCC §§{chapter_no * 100}–{chapter_no * 100 + 99}" if first else "CCC"),
                position=pos, unit_label=(f"§{first}" if first else None), metadata=piece_meta,
                source_units=units))
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

