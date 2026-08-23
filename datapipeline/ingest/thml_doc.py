"""Shared ThML per-work Document builder.

Extracted from church_fathers so medieval (also CCEL ThML) reuses one tested
path. Builds a Document of clean Passages from a flat list of
(book_label|None, chapter_element) pairs, flattening book->chapter into labels.
"""
from __future__ import annotations

import re

from config import settings
from identity import document_id, anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import smart_title_case
from ingest.common import _book_label, _direct_p_text, split_display_passage


def _chapter_label(elem) -> str:
    """A short, clean chapter heading from ThML shorttitle/title/n attributes."""
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


def make_doc(*, collection: str, filename: str, author: str, title: str,
             chapters: list, year: int | None = None,
             extra_meta: dict | None = None) -> Document | None:
    """Build one Document from (book|None, chapter_elem) pairs. Returns None if empty."""
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
        if base_key in seen_keys:
            seen_keys[base_key] += 1
            ch_key = f"{base_key}--{seen_keys[base_key]}"
        else:
            seen_keys[base_key] = 1
            ch_key = base_key
        meta = {"source_file": filename}
        if book_clean:
            meta["book"] = book_clean
        if extra_meta:
            meta.update(extra_meta)
        parts = split_display_passage(raw, maxc)
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
    doc_meta = {"source_file": filename}
    if extra_meta:
        doc_meta.update(extra_meta)
    return Document(id=document_id(collection, author, title), collection=collection,
                    title=title, author=author, year=year, metadata=doc_meta,
                    passages=passages)
