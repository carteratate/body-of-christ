"""Church Fathers ingestion — one Document per (father, work).

Parses each ANF/NPNF ThML volume into per-work documents with the correct
Church Father as author (not the series editor) and the specific work title.
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
from ingest.common import iter_works, _extract_p_text, split_at_sentences

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
_SINGLE_AUTHOR = {"confessions.xml": "Augustine", "incarnation.xml": "Athanasius"}
_AUGUSTINE_FILES = {"city-of-god.xml", "on-the-holy-trinity.xml"}


def _strip_doctype(xml: str) -> str:
    return re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        return ET.fromstring(_strip_doctype(f.read()))


def _chapter_label(raw_title: str, n: str) -> str:
    """A short, clean chapter heading: the part before the em-dash description."""
    head = re.split(r"\.?—|—", (raw_title or "").strip())[0].strip().rstrip(".")
    if head:
        return smart_title_case(head)
    if n:
        return f"Chapter {n.upper()}"
    return "Section"


def _passages_from_chapters(work_slug, author, title, chapters):
    passages: list[Passage] = []
    pos = 0
    maxc = settings.MAX_PASSAGE_CHARS
    for ch in chapters:
        raw = _extract_p_text(ch)
        if len(raw) < 100:
            continue
        n = (ch.get("n") or "").strip()
        label = _chapter_label(ch.get("title") or "", n)
        ch_slug = slugify(label) or f"sec-{pos}"
        ch_key = make_anchor(work_slug, ch_slug)
        parts = split_at_sentences(raw, target=maxc, overlap=0) if len(raw) > maxc else [raw]
        for i, part in enumerate(parts):
            sub = f"-{i + 1}" if len(parts) > 1 else ""
            passages.append(Passage(
                content=clean_text(part),
                reference=f"{author} — {title}, {label}",
                anchor=ch_key + sub,
                chapter_key=ch_key,
                chapter_label=label,
                position=pos,
                unit_label=None,
                metadata=None,
            ))
            pos += 1
    return passages


def build_documents(path: str) -> list[Document]:
    filename = os.path.basename(path)
    if filename == "summa.xml":
        return []
    root = _read_root(path)
    docs: list[Document] = []

    single = _SINGLE_AUTHOR.get(filename)
    if single:
        works = list(iter_works(root))
        chapters = [ch for _, _, chs in works for ch in chs]
        title = (root.findtext(".//DC.Title") or (works[0][1] if works else "Unknown")).strip()
        title = smart_title_case(title)
        passages = _passages_from_chapters(slugify(title), single, title, chapters)
        if passages:
            docs.append(Document(
                id=document_id("church-fathers", single, title),
                collection="church-fathers", title=title, author=single,
                metadata={"source_file": filename}, passages=passages))
        return docs

    augustine = filename in _AUGUSTINE_FILES
    for father, work, chapters in iter_works(root):
        if augustine:
            author = "Augustine"
            title = smart_title_case(work).strip() or "Unknown"
        else:
            author = smart_title_case(father).strip() or "Unknown"
            title = smart_title_case(work).strip() or author
        work_slug = slugify(title) or slugify(author)
        passages = _passages_from_chapters(work_slug, author, title, chapters)
        if not passages:
            continue
        docs.append(Document(
            id=document_id("church-fathers", author, title),
            collection="church-fathers", title=title, author=author,
            metadata={"source_file": filename}, passages=passages))
    return docs


def build_all() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(glob(os.path.join(_SRC_DIR, "*.xml"))):
        if path.endswith(".Zone.Identifier"):
            continue
        docs.extend(build_documents(path))
    return docs
