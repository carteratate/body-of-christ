"""Catechism of the Catholic Church ingestion — three-tier page_node chunking.

Source: nossbigg/catechism-ccc-json (v0.0.2)

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

import asyncio
import json
import os
import sys

from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document  # noqa: E402
from identity import document_id, anchor as make_anchor  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from config import settings  # noqa: E402
from ingest.common import split_at_sentences, _split_at_whitespace  # noqa: E402

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
    return 0 < len(text) < _HEADER_MAX_CHARS


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

            for i, (sec_text, sec_paras, is_brief) in enumerate(sections):
                # Skip header-only trailing sections that have no CCC paragraph content.
                # These arise when a section title appears at the end of a large node
                # with no following body paragraphs — the actual content is in the next node.
                if not sec_paras:
                    continue

                if i == 0 and prefix:
                    sec_content = (prefix + "\n\n" + sec_text).strip()
                else:
                    sec_content = sec_text

                is_partial = n_sections > 1
                ref = make_reference(sec_paras, node_id, is_partial=is_partial)
                meta: dict = {
                    "path": node_id,
                    "ccc_paragraphs": sec_paras,
                    "is_in_brief": is_brief,
                }
                chunks.append((sec_content, ref, meta, position))
                position += 1
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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def ingest_catechism(pool, source_path: str | None = None) -> None:
    """Ingest the Catechism of the Catholic Church into the database."""
    src = source_path or _DEFAULT_SRC
    print(f"Reading CCC JSON from {src}...")
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    page_nodes_raw: dict = data.get("page_nodes", {})

    def _toc_key(k: str) -> int:
        try:
            return int(k.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    sorted_ids = sorted(page_nodes_raw.keys(), key=_toc_key)
    sorted_nodes = [page_nodes_raw[k] for k in sorted_ids]

    chunks = chunk_nodes(sorted_nodes, sorted_ids)
    print(f"  Produced {len(chunks)} chunks from {len(sorted_ids)} page nodes.")

    doc_id = await upsert_document(
        pool,
        collection="catechism",
        title="Catechism of the Catholic Church",
        translation="",
        author="Catholic Church",
        year=1992,
        metadata={"source": "nossbigg/catechism-ccc-json"},
    )

    with tqdm(total=len(chunks), unit="chunk", desc="Catechism") as pbar:
        for content, reference, metadata, pos in chunks:
            await upsert_chunk(
                pool,
                document_id=doc_id,
                content=content,
                position=pos,
                reference=reference,
                metadata=metadata,
            )
            pbar.update(1)

    print(f"  Done. {len(chunks)} chunks written for catechism.")


_MIN_CONTENT = 30


def _cap(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def build_document(source_path: str | None = None) -> Document:
    """Build the CCC as one Document of clean numbered passages (reuses the
    three-tier chunker, drops tiny TOC-only fragments, normalizes ellipses)."""
    src = source_path or _DEFAULT_SRC
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    page_nodes = data.get("page_nodes", {})

    def _key(k: str) -> int:
        try:
            return int(k.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    ids = sorted(page_nodes.keys(), key=_key)
    raw_chunks = chunk_nodes([page_nodes[k] for k in ids], ids)  # (content, ref, meta, pos)

    did = document_id("catechism")
    passages: list[Passage] = []
    pos = 0
    seen: set[str] = set()
    for content, reference, meta, _ in raw_chunks:
        clean = clean_text(content)
        if len(clean) < _MIN_CONTENT:
            continue                      # drop TOC-only fragments ("Article 2")
        paras = meta.get("ccc_paragraphs") or []
        first = paras[0] if paras else None
        chapter_no = (first // 100) if first else 0
        base = make_anchor("ccc", first) if first else make_anchor("ccc", meta.get("path", str(pos)))
        pieces = _cap(clean, settings.MAX_PASSAGE_CHARS)
        for j, piece in enumerate(pieces):
            anchor = base + (f"-p{j + 1}" if len(pieces) > 1 else "")
            k = 1
            while anchor in seen:
                k += 1
                anchor = f"{base}-p{j + 1}-{k}" if len(pieces) > 1 else f"{base}-{k}"
            seen.add(anchor)
            passages.append(Passage(
                content=piece, reference=reference, anchor=anchor,
                chapter_key=make_anchor("ccc", "part", str(chapter_no)),
                chapter_label=(f"CCC §§{chapter_no * 100}–{chapter_no * 100 + 99}" if first else "CCC"),
                position=pos, unit_label=(f"§{first}" if first else None), metadata=meta))
            pos += 1
    return Document(id=did, collection="catechism",
                    title="Catechism of the Catholic Church", author="Catholic Church",
                    year=1992, metadata={"source": "nossbigg/catechism-ccc-json"},
                    passages=passages)


async def main(pool) -> None:
    """Entry point called by run_all.py."""
    await ingest_catechism(pool)


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
