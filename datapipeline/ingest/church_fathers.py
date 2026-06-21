"""Church Fathers ingestion — one Document per (father, work).

Parses each ANF/NPNF ThML volume into per-work documents with the correct
Church Father as author (not the series editor) and the specific work title.
Works nest to variable depth (work→chapter or work→book→chapter); book-structured
works (City of God, Against Heresies, …) stay ONE document, with the book carried
into the chapter label and metadata (flat sections for now; richer book→chapter
navigation can be layered on later without re-ingesting).
"""
from __future__ import annotations

import os
import re
from glob import glob

import defusedxml.ElementTree as ET

from config import settings
from identity import document_id, anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import smart_title_case
from ingest.common import (
    iter_chapters, _direct_p_text, _book_label, split_at_sentences, _split_at_whitespace,
    _build_parent_map, _cf_skippable,
)

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
_SINGLE_AUTHOR = {"confessions.xml": "Augustine", "incarnation.xml": "Athanasius"}
_AUGUSTINE_FILES = {"city-of-god.xml", "on-the-holy-trinity.xml"}


def _strip_doctype(xml: str) -> str:
    return re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        return ET.fromstring(_strip_doctype(f.read()))


def _chapter_label(elem) -> str:
    """A short, clean chapter heading. ThML carries a concise label in shorttitle
    ('Chapter 1') and a long descriptive sentence in title; prefer the former."""
    st = (elem.get("shorttitle") or "").strip()
    title = (elem.get("title") or "").strip()
    n = (elem.get("n") or "").strip()
    typ = (elem.get("type") or "").strip().lower()
    if st and not st.endswith("...") and len(st) <= 45:
        return smart_title_case(st)
    if typ == "chapter" and n:
        return f"Chapter {n}"
    head = re.split(r"\.?—|—", title)[0].strip().rstrip(".")
    if head:
        return smart_title_case(head[:60])
    return f"Chapter {n}" if n else "Section"


def _cap_pieces(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def _make_doc(filename, author, title, chapters):
    if not chapters:
        return None
    work_slug = slugify(title) or slugify(author) or "work"
    maxc = settings.MAX_PASSAGE_CHARS
    passages: list[Passage] = []
    pos = 0
    seen_keys: dict[str, int] = {}
    for book, elem in chapters:
        raw = _direct_p_text(elem)
        if len(raw) < 100:
            continue
        self_book = _book_label(elem)
        if book is None and self_book:
            # The div is itself a book carrying intro paragraphs before its chapters.
            book = self_book
            core = "Introduction"
        else:
            core = _chapter_label(elem)
        if book:
            book_clean = smart_title_case(book)
            label = f"{book_clean} · {core}"
            base_key = make_anchor(work_slug, slugify(book_clean), slugify(core) or "sec")
        else:
            book_clean = None
            label = core
            base_key = make_anchor(work_slug, slugify(core) or "sec")
        # Ensure a stable, unique chapter_key even if two chapters share a label.
        # '--N' for the dedup suffix is kept distinct from the '/pN' split suffix
        # below so the two never collide.
        if base_key in seen_keys:
            seen_keys[base_key] += 1
            ch_key = f"{base_key}--{seen_keys[base_key]}"
        else:
            seen_keys[base_key] = 1
            ch_key = base_key
        meta = {"source_file": filename}
        if book_clean:
            meta["book"] = book_clean
        parts = _cap_pieces(raw, maxc)
        for i, part in enumerate(parts):
            sub = f"/p{i + 1}" if len(parts) > 1 else ""
            passages.append(Passage(
                content=clean_text(part),
                reference=f"{author} — {title}, {label}",
                anchor=ch_key + sub, chapter_key=ch_key, chapter_label=label,
                position=pos, unit_label=None, metadata=meta))
            pos += 1
    if not passages:
        return None
    return Document(id=document_id("church-fathers", author, title),
                    collection="church-fathers", title=title, author=author,
                    metadata={"source_file": filename}, passages=passages)


def build_documents(path: str) -> list[Document]:
    filename = os.path.basename(path)
    if filename == "summa.xml":
        return []
    root = _read_root(path)
    parent_map = _build_parent_map(root)
    docs: list[Document] = []

    single = _SINGLE_AUTHOR.get(filename)
    if single:
        title = smart_title_case((root.findtext(".//DC.Title") or "Unknown").strip())
        chapters = list(iter_chapters(root, parent_map))
        d = _make_doc(filename, single, title, chapters)
        if d:
            docs.append(d)
        return docs

    div1s = [d for d in root.iter("div1") if not _cf_skippable(d.get("title") or "")]
    if filename in _AUGUSTINE_FILES:
        # div1 = work; author is always Augustine.
        for d1 in div1s:
            title = smart_title_case((d1.get("title") or "").strip())
            d = _make_doc(filename, "Augustine", title, list(iter_chapters(d1, parent_map)))
            if d:
                docs.append(d)
    else:
        # Multi-author volume: div1 = father, div2 = work (else father itself is the work).
        for d1 in div1s:
            father = smart_title_case((d1.get("title") or "").strip())
            works = [w for w in d1.iter("div2") if not _cf_skippable(w.get("title") or "")]
            if works:
                for w in works:
                    title = smart_title_case((w.get("title") or "").strip()) or father
                    d = _make_doc(filename, father, title, list(iter_chapters(w, parent_map)))
                    if d:
                        docs.append(d)
            else:
                d = _make_doc(filename, father, father, list(iter_chapters(d1, parent_map)))
                if d:
                    docs.append(d)
    return docs


def build_all() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(glob(os.path.join(_SRC_DIR, "*.xml"))):
        if path.endswith(".Zone.Identifier"):
            continue
        docs.extend(build_documents(path))
    return docs
