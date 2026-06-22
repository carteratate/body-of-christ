"""Medieval theology ingestion (dual pipeline).

Reads vendored CCEL ThML from sources/medieval/ and builds one Document per
(author, work) via the shared ThML helper. Anselm's basic_works.xml is
multi-work / single-author (each div1 is a work).
"""
from __future__ import annotations

import json
import os
import re

import defusedxml.ElementTree as ET

from model import Document
from normalize.caps import smart_title_case
from ingest.common import iter_chapters, _build_parent_map, _cf_skippable
from ingest.thml_doc import make_doc

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "medieval")


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    docs: list[Document] = []
    for entry in manifest:
        path = os.path.join(_SRC, entry["file"])
        root = _read_root(path)
        parent_map = _build_parent_map(root)
        author, year = entry["author"], entry["year"]
        extra = {"source_url": entry["url"]}
        if entry.get("fix_author"):
            # Multi-work single-author file (Anselm): each work is a div1 marked
            # type="Book"; front-matter (Title Page, Introduction, Appendix,
            # Indexes) is unmarked and excluded. Fall back to the front-matter
            # filter if a file marks no works.
            works = [d for d in root.iter("div1")
                     if (d.get("type") or "").strip().lower() == "book"]
            if not works:
                works = [d for d in root.iter("div1")
                         if not _cf_skippable(d.get("title") or "")]
            for d1 in works:
                work = smart_title_case((d1.get("title") or "").strip()) or entry["title"]
                d = make_doc(collection="medieval", filename=entry["file"], author=author,
                             title=work, chapters=list(iter_chapters(d1, parent_map)),
                             year=year, extra_meta=extra)
                if d:
                    docs.append(d)
        else:
            d = make_doc(collection="medieval", filename=entry["file"], author=author,
                         title=entry["title"], chapters=list(iter_chapters(root, parent_map)),
                         year=year, extra_meta=extra)
            if d:
                docs.append(d)
    return docs
