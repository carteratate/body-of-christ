from __future__ import annotations
import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import tostring as et_tostring  # serialization only — no parsing
import defusedxml.ElementTree as ET  # safe parsing: blocks XXE and billion-laughs attacks


@dataclass
class ThmlDocument:
    title: str
    author: str | None
    year: int | None
    chunks: list[tuple[str, str, int]] = field(default_factory=list)  # (content, reference, position)


def _strip_tags(text: str) -> str:
    """Remove XML/HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return " ".join(text.split())


def _extract_p_text(elem) -> str:
    """Concatenate text from all <p> children of elem."""
    parts = []
    for p in elem.iter("p"):
        raw = et_tostring(p, encoding="unicode", method="xml")
        t = _strip_tags(raw)
        if t:
            parts.append(t)
    return "\n\n".join(parts)


def _parse_author(creator: str) -> tuple[str, int | None]:
    """
    Parse 'Augustine, Saint, Bishop of Hippo (345-430)' or
    'Athanasius, St. (c.296-c.373)' into (cleaned_name, death_year).
    """
    m = re.search(r"\(c?\.?\d{3,4}\??-c?\.?(\d{3,4})\)\s*$", creator)
    year: int | None = None
    if m:
        try:
            year = int(m.group(1))
        except ValueError:
            pass
        creator = creator[: m.start()].strip().rstrip(",").strip()
    return creator, year


def _is_summa(root) -> bool:
    head = root.find(".//electronicEdInfo")
    if head is None:
        return False
    author_id = head.findtext("authorID") or ""
    book_id = head.findtext("bookID") or ""
    return author_id.strip() == "aquinas" and book_id.strip() == "summa"


_SENT_END = re.compile(r'(?<=[.!?])\s+')
_MAX_FALLBACK_SCAN = 500


def split_at_sentences(
    text: str,
    target: int = 1200,
    overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks of ~target chars at sentence boundaries.

    All limits are soft — splits always happen at sentence ends. If no sentence
    boundary is found within _MAX_FALLBACK_SCAN chars of the target, splits at
    the nearest whitespace instead.
    """
    if len(text) <= target:
        return [text]

    sentences = _SENT_END.split(text)
    if len(sentences) <= 1:
        return _split_at_whitespace(text, target, overlap)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        current.append(sent)
        current_len += len(sent) + 1
        if current_len >= target:
            chunks.append(" ".join(current))
            overlap_sents: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) + 1 <= overlap:
                    overlap_sents.insert(0, s)
                    overlap_len += len(s) + 1
                else:
                    break
            current = overlap_sents
            current_len = overlap_len

    if current:
        last = " ".join(current)
        if not chunks or last != chunks[-1]:
            chunks.append(last)

    return chunks


def _split_at_whitespace(text: str, target: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + target, len(text))
        if end < len(text):
            ws = text.rfind(" ", start, end + _MAX_FALLBACK_SCAN)
            if ws > start:
                end = ws
        chunks.append(text[start:end].strip())
        start = end - overlap
        if start >= end:
            break
    return [c for c in chunks if c]


_MIN_MERGE_CHARS = 200
_MAX_SECTION_CHARS = 2500
_TARGET_CHUNK_CHARS = 1200
_OVERLAP_CHARS = 200


def _chunk_standard(root, min_length: int = 100) -> list[tuple[str, str, int]]:
    """Hybrid chunking: natural section boundary preserved if ≤ 2500 chars,
    sliding window applied for longer sections. Short sections merged upward."""
    # 1. Collect raw sections
    raw_sections: list[tuple[str, str]] = []
    for elem in root.iter():
        if elem.tag != "div1":
            continue
        div1_title = (elem.get("title") or "").strip()
        div2_found = False
        for child in elem:
            if not child.tag.startswith("div2"):
                continue
            div2_title = (child.get("title") or "").strip()
            content = _extract_p_text(child)
            if len(content) < min_length:
                continue
            reference = f"{div1_title}, {div2_title}" if div1_title else div2_title
            raw_sections.append((content, reference))
            div2_found = True
        if not div2_found:
            content = _extract_p_text(elem)
            if len(content) >= min_length:
                raw_sections.append((content, div1_title or "Section"))

    # 2. Merge short sections into the next
    merged: list[tuple[str, str]] = []
    i = 0
    while i < len(raw_sections):
        content, ref = raw_sections[i]
        if len(content) < _MIN_MERGE_CHARS and i + 1 < len(raw_sections):
            next_content, next_ref = raw_sections[i + 1]
            raw_sections[i + 1] = (content + "\n\n" + next_content, next_ref)
            i += 1
            continue
        merged.append((content, ref))
        i += 1

    # 3. Emit chunks
    chunks: list[tuple[str, str, int]] = []
    position = 0
    for content, ref in merged:
        if len(content) <= _MAX_SECTION_CHARS:
            chunks.append((content, ref, position))
            position += 1
        else:
            parts = split_at_sentences(content, _TARGET_CHUNK_CHARS, _OVERLAP_CHARS)
            total = len(parts)
            for idx, part in enumerate(parts):
                part_ref = f"{ref} ({idx + 1}/{total})" if total > 1 else ref
                chunks.append((part, part_ref, position))
                position += 1

    return chunks


def _chunk_summa(root, min_length: int = 50) -> list[tuple[str, str, int]]:
    """Chunk at div4 (Article) level for the Summa."""
    chunks: list[tuple[str, str, int]] = []
    position = 0
    for div3 in root.iter("div3"):
        div3_title = (div3.get("title") or "").strip()
        for child in div3:
            if not child.tag.startswith("div4"):
                continue
            div4_title = (child.get("title") or "").strip()
            content = _extract_p_text(child)
            if len(content) < min_length:
                continue
            reference = f"{div3_title}, {div4_title}" if div3_title else div4_title
            chunks.append((content, reference, position))
            position += 1
    return chunks


def parse_thml_string(xml_string: str) -> ThmlDocument:
    """Parse a ThML XML string into a ThmlDocument."""
    # Strip DOCTYPE declaration to prevent network fetches
    xml_string = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml_string, flags=re.DOTALL)
    root = ET.fromstring(xml_string)

    # Extract metadata
    title = (root.findtext(".//DC.Title") or root.findtext(".//title") or "Unknown").strip()

    creator = ""
    for el in root.findall(".//DC.Creator"):
        if el.get("scheme") == "file-as":
            creator = (el.text or "").strip()
            break

    author: str | None = None
    year: int | None = None
    if creator:
        author, year = _parse_author(creator)

    # Choose chunking strategy
    if _is_summa(root):
        chunks = _chunk_summa(root)
    else:
        chunks = _chunk_standard(root)

    return ThmlDocument(title=title, author=author, year=year, chunks=chunks)


def parse_thml(path: str) -> ThmlDocument:
    """Parse a ThML XML file into a ThmlDocument."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_thml_string(f.read())
