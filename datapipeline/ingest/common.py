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


def _chunk_standard(root, min_length: int = 100) -> list[tuple[str, str, int]]:
    """Chunk at div2 (chapter) level; falls back to div1 if no div2 content found."""
    chunks: list[tuple[str, str, int]] = []
    position = 0
    for elem in root.iter():
        if elem.tag != "div1":
            continue
        div1_title = (elem.get("title") or "").strip()
        # Try div2 children first
        div2_chunks: list[tuple[str, str, int]] = []
        for child in elem:
            if not child.tag.startswith("div2"):
                continue
            div2_title = (child.get("title") or "").strip()
            content = _extract_p_text(child)
            if len(content) < min_length:
                continue
            reference = f"{div1_title}, {div2_title}" if div1_title else div2_title
            div2_chunks.append((content, reference, position))
            position += 1
        if div2_chunks:
            chunks.extend(div2_chunks)
        else:
            # Fallback: treat div1 itself as a chunk
            content = _extract_p_text(elem)
            if len(content) >= min_length:
                chunks.append((content, div1_title or "Section", position))
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
