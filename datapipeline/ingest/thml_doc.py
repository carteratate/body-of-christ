"""Shared ThML per-work Document builder.

Extracted from church_fathers so medieval (also CCEL ThML) reuses one tested
path. Builds a Document of clean Passages from a flat list of
(book_label|None, chapter_element) pairs, flattening book->chapter into labels.

Anchors come from the source's structure (2.1): a chapter's anchor and chapter key are
its div's `id`, exactly as the file writes it, and a later split piece is named by the
first paragraph it holds (`ingest.pieces`). Labels never reach an anchor.
"""
from __future__ import annotations

import re

from xml.etree.ElementTree import tostring as et_tostring  # serialization only

from config import settings
from model import Document, Passage
from normalize.text import clean_text, fold_ligatures
from normalize.caps import smart_title_case
from ingest.common import _book_label, _direct_p_text, _strip_tags, split_display_passage
from ingest.pieces import Segment, name_pieces
from registry import ANCHOR_SCHEME, resolve_document_id


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


def paragraph_segments(elem) -> list[Segment]:
    """The div's direct paragraphs, as `_direct_p_text` reads them, each named by its
    `id` without the div's own id in front (`ii.iii-p5` in div `ii.iii` is `p5`), or,
    with no id, `n<k>`: its ordinal among the div's `<p>` and `<verse>` children."""
    div = elem.get("id") or ""
    out, k = [], 0
    for child in elem:
        if child.tag not in ("p", "verse"):
            continue
        k += 1
        if child.tag != "p":
            continue
        text = _strip_tags(et_tostring(child, encoding="unicode", method="xml"))
        if not text:
            continue
        pid = child.get("id")
        if pid and div and pid.startswith(div + "-"):
            pid = pid[len(div) + 1:]
        out.append(Segment(pid or f"n{k}", text))
    return out


def _label(text: str) -> str:
    return fold_ligatures(text.strip().rstrip(" ."))


def _reference(author: str, title: str, label: str) -> str:
    return f"{author} — {title}, {label}"


def make_doc(*, collection: str, filename: str, author: str, title: str,
             chapters: list, source_key: str, year: int | None = None,
             extra_meta: dict | None = None) -> Document | None:
    """Build one Document from (book|None, chapter_elem) pairs. Returns None if empty.
    `source_key` names the work in the source (file, plus the work div's id when the
    file holds several works); the registry freezes the document ID under it."""
    if not chapters:
        return None
    # ANF and NPNF headings end in a period ("Methodius.", "Fragments."), and some spell
    # ligatures ("Irenæus"). Neither belongs in a label. The registry keeps the document
    # ID, and `identity.slugify` drops the punctuation anyway (1.10a).
    author, title = _label(author), _label(title)
    maxc = settings.MAX_PASSAGE_CHARS
    passages: list[Passage] = []
    pos = 0
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
        core = fold_ligatures(core)
        if book:
            book_clean = fold_ligatures(smart_title_case(book))
            label = f"{book_clean} · {core}"
        else:
            book_clean = None
            label = core
        ch_key = elem.get("id")
        if not ch_key:
            raise ValueError(f"{filename}: chapter {label!r} has no div id to anchor on")
        meta = {"source_file": filename}
        if book_clean:
            meta["book"] = book_clean
        if extra_meta:
            meta.update(extra_meta)
        parts = split_display_passage(raw, maxc)
        named = name_pieces(ch_key, raw, parts, paragraph_segments(elem))
        for part, (anchor, units) in zip(parts, named):
            passages.append(Passage(
                content=clean_text(part),
                reference=_reference(author, title, label),
                anchor=anchor, chapter_key=ch_key, chapter_label=label,
                position=pos, unit_label=None, metadata=meta, source_units=units))
            pos += 1
    if not passages:
        return None
    doc_meta = {"source_file": filename, "source_key": source_key,
                "anchor_scheme": ANCHOR_SCHEME}
    if extra_meta:
        doc_meta.update(extra_meta)
    did = resolve_document_id(collection, source_key, (collection, author, title))
    return Document(id=did, collection=collection,
                    title=title, author=author, year=year, metadata=doc_meta,
                    passages=passages)


def distinct_titles(documents: list[Document]) -> list[Document]:
    """No two documents of a collection share a title (C-15): where they do once their
    trailing periods are gone (Papias's "Fragments" and Methodius's "Fragments."), each
    takes its author: "Fragments of Papias", "Epistle of Polycarp to the Philippians".
    Their passages' references follow. Document IDs come from the registry and stay."""
    by_title: dict[str, list[Document]] = {}
    for d in documents:
        by_title.setdefault(d.title.casefold(), []).append(d)
    for shared in by_title.values():
        if len(shared) < 2:
            continue
        for d in shared:
            d.title = _with_author(d.title, d.author)
            for p in d.passages:
                p.reference = _reference(d.author, d.title, p.chapter_label)
    return documents


def _with_author(title: str, author: str) -> str:
    head, sep, rest = title.partition(" ")
    if head in ("Epistle", "Letter") and rest.startswith("to "):
        return f"{head} of {author} {rest}"
    return f"{title} of {author}"
