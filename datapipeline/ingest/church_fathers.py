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

from model import Document
from normalize.caps import smart_title_case
from ingest.common import iter_chapters, _build_parent_map, _cf_skippable
from ingest.thml_doc import make_doc

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
_SINGLE_AUTHOR = {"confessions.xml": "Augustine", "incarnation.xml": "Athanasius"}
_AUGUSTINE_FILES = {"city-of-god.xml", "on-the-holy-trinity.xml"}


def _strip_doctype(xml: str) -> str:
    return re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        return ET.fromstring(_strip_doctype(f.read()))


def _make_doc(filename, author, title, chapters):
    return make_doc(collection="church-fathers", filename=filename,
                    author=author, title=title, chapters=chapters)


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
