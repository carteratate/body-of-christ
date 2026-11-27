"""Medieval theology ingestion (dual pipeline).

Reads vendored CCEL ThML from sources/medieval/ and builds one Document per
(author, work) via the shared ThML helper. Anselm's basic_works.xml is
multi-work / single-author (each div1 is a work).

Rule G runs here as in the Fathers (1.9): an `ingest.editorial.Editor` skips the
editors' divs (Boethius's note on the translation, editorial note and chronological
table, the Imitation's foreword) and edits each chapter.
"""
from __future__ import annotations

import json
import os
import re

import defusedxml.ElementTree as ET

from model import Document
from normalize.caps import smart_title_case
from ingest.common import _block_text, _build_parent_map, _cf_skippable, iter_chapters
from ingest.editorial import ChapterEdit, Editor, Removed
from ingest.keys import THEOLOGIANS as COLLECTION
from ingest.thml_doc import ChapterPlan, distinct_titles, make_doc

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "medieval")

# Anselm's three works are one source file with one manifest year (1099); each carries
# its own (the plan, 1.9). The Proslogium's year is a range, shown as `date_display`.
_WORK_YEARS = {"Monologium": 1076, "Proslogium": 1077, "Anselm's Cur Deus Homo": 1098}
_WORK_DATES = {"Proslogium": "1077 to 1078"}
# The source's work titles that are not the work's title.
_WORK_TITLES = {"Anselm's Cur Deus Homo": "Cur Deus Homo"}

# The translations the source files leave unnamed or misname (1.9): Boethius's is
# Cooper's, not H. R. James's (the plan's correction note); On Loving God's is van
# Allen's (R5, Decision log "On Loving God translation").
_TRANSLATIONS = {
    "consolation-of-philosophy.xml": {
        "translator": "W. V. Cooper",
        "edition": "J. M. Dent and Company, London, 1902",
    },
    "on-loving-god.xml": {
        "translator": "William Harman van Allen",
        "edition": "Caldey Abbey, Tenby, 1909",
        "credit_line": "Translated by William Harman van Allen (1909). Sourced via CCEL.org",
    },
}

# Chapter titles the vendored file mistranscribes, by (file, div id): the 1909 printing
# of On Loving God reads "loves Self for Self's sake", capitals and all (R5).
_LABELS = {
    ("on-loving-god.xml", "x"):
        "Chapter VIII. Of the first degree of love: wherein man loves Self for Self's sake",
}


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


def _anselm_front_matter(title: str) -> bool:
    """Front matter inside Anselm's works: a work's "Preface" is Anselm's own and stays."""
    t = (title or "").strip().lower()
    return t != "preface" and _cf_skippable(t)


class _MedievalEditor(Editor):
    """Rule G for a medieval work. A preface of Anselm's opens with the editor's summary
    of the work ("In this brief work the author aims at…", class `SectionInfo`), which
    leaves the text; his chapters' `SectionInfo` lines are his own capitula and stay."""

    def chapter(self, elem, label: str) -> ChapterEdit:
        edit = super().chapter(elem, label)
        if (elem.get("title") or "").strip().lower() == "preface":
            for block in elem:
                if block.tag == "p" and block.get("class") == "SectionInfo":
                    edit.dropped[id(block)] = "summary"
                    edit.removed.append(Removed(edit.locators[id(block)], "summary",
                                                _block_text(block)))
        return edit


def _plan(filename: str, elem, imitation: bool) -> ChapterPlan:
    label = _LABELS.get((filename, elem.get("id")))
    title = (elem.get("title") or "").strip()
    if label is None and imitation and title \
            and (elem.get("type") or "").strip().lower() == "chapter":
        # The Imitation's chapters are titled; a long short title would otherwise give
        # "Chapter 1" (Book I's first, "Imitating Christ and Despising All Vanities…").
        label = smart_title_case(title)
    return ChapterPlan(label=label)


def _chapters(filename: str, work, parent_map, editor: Editor, front_matter=_cf_skippable):
    imitation = filename == "imitation-of-christ.xml"
    return [(book, elem, _plan(filename, elem, imitation)) for book, elem in
            iter_chapters(work, parent_map, editor.skip, front_matter=front_matter)]


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    docs: list[Document] = []
    for entry in manifest:
        filename = entry["file"]
        path = os.path.join(_SRC, filename)
        root = _read_root(path)
        parent_map = _build_parent_map(root)
        author, year = entry["author"], entry["year"]
        extra = {"source_url": entry["url"], **_TRANSLATIONS.get(filename, {})}
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
                source_title = smart_title_case((d1.get("title") or "").strip())
                work = _WORK_TITLES.get(source_title, source_title) or entry["title"]
                source_key = f"medieval/{filename}#{d1.get('id')}"
                editor = _MedievalEditor(filename, source_key, parent_map)
                d = make_doc(collection=COLLECTION, filename=filename, author=author,
                             title=work,
                             chapters=_chapters(filename, d1, parent_map, editor,
                                                _anselm_front_matter),
                             source_key=source_key,
                             year=_WORK_YEARS.get(source_title, year), extra_meta=extra,
                             editor=editor)
                if d:
                    d.date_display = _WORK_DATES.get(source_title)
                    docs.append(d)
        else:
            source_key = f"medieval/{filename}"
            editor = _MedievalEditor(filename, source_key, parent_map)
            d = make_doc(collection=COLLECTION, filename=filename, author=author,
                         title=entry["title"],
                         chapters=_chapters(filename, root, parent_map, editor),
                         source_key=source_key, year=year, extra_meta=extra, editor=editor)
            if d:
                d.translation = _translation(filename)
                docs.append(d)
    return distinct_titles(docs)


def _translation(filename: str) -> str:
    t = _TRANSLATIONS.get(filename)
    return f"{t['translator']} ({t['edition']})" if t else ""
