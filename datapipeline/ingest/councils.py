"""Ecumenical Councils ingestion (dual pipeline).

One Document per council (ecumenical 1-20) or per Vatican II document. Passages:
one per canon / numbered paragraph; plain prose accumulates to the size cap.
Chapters group by header (h2/h3/h4 or CHAPTER N); header-less prose forms a
single 'Text' chapter.
"""
from __future__ import annotations

import json
import os
import re

from bs4 import BeautifulSoup

from config import settings
from identity import document_id, anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.footnotes import strip_footnote_markers
from ingest.common import split_at_sentences, _split_at_whitespace

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_CANON = re.compile(r"^(?:Canon|Can\.?)\s+(\d+|[IVXLCDM]+)[\.\:]?\s*(.*)", re.IGNORECASE | re.DOTALL)
_NUM = re.compile(r"^(\d+)\s*\.\s+(.+)", re.DOTALL)
_CHAPTER = re.compile(r"^CHAPTER\s+([IVXLCDM]+)\b\.?\s*(.*)", re.IGNORECASE | re.DOTALL)
# Tanner's edition numbers many medieval-council canons as a leading "[1a]." etc.
_LEAD_CANON = re.compile(r"^\[(\d+[a-z]?)\]\s*\.?\s*(.*)", re.DOTALL)
# Editorial brackets: page markers ([Page 45]), footnote refs ([3]), notes.
_BRACKET = re.compile(r"\[[^\]]*\]")
_MIN = 40
_TARGET = 2200


def _declutter(text: str) -> str:
    """Drop editorial bracket spans (page/footnote markers, notes) and tidy."""
    return re.sub(r"\s{2,}", " ", _BRACKET.sub(" ", text)).strip()


def _chapter_label_from(m: re.Match) -> str:
    roman = m.group(1).upper()
    rest = _declutter(m.group(2) or "").strip(" .:-")
    return f"Chapter {roman}" + (f": {title_case_shouting(rest)}" if rest else "")


def _cap(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def _strip_chrome(soup) -> None:
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "form"]):
        tag.decompose()


class _Builder:
    """Accumulates passages with unique anchors for one council document."""

    def __init__(self):
        self.passages: list[Passage] = []
        self.pos = 0
        self.seen: set[str] = set()

    def add(self, *, body: str, ref: str, base_anchor: str, ckey: str,
            clabel: str, unit: str | None, meta: dict) -> None:
        body = clean_text(strip_footnote_markers(_declutter(body)))
        if len(body) < 1:
            return
        pieces = _cap(body, settings.MAX_PASSAGE_CHARS)
        for j, piece in enumerate(pieces):
            anc = base_anchor + (f"/p{j + 1}" if len(pieces) > 1 else "")
            k = 1
            while anc in self.seen:
                k += 1
                anc = f"{base_anchor}-{k}"
            self.seen.add(anc)
            self.passages.append(Passage(content=piece, reference=ref, anchor=anc,
                                         chapter_key=ckey, chapter_label=clabel,
                                         position=self.pos, unit_label=unit, metadata=meta))
            self.pos += 1


def build_ecumenical(entry: dict, soup: BeautifulSoup) -> Document:
    _strip_chrome(soup)
    council = entry["council"]
    cslug = slugify(council)
    did = document_id("councils", council, council)
    b = _Builder()
    meta = {"council": council, "year": entry["year"], "url": entry["url"]}
    sec_ord, sec_key, sec_label = 0, make_anchor(cslug, "sec-0"), "Text"
    prose: list[str] = []
    seq = 0

    def flush_prose() -> None:
        nonlocal seq, prose
        if not prose:
            return
        seq += 1
        b.add(body="\n\n".join(prose), ref=f"{council} — {sec_label}",
              base_anchor=make_anchor(cslug, f"sec-{sec_ord}", seq),
              ckey=sec_key, clabel=sec_label, unit=None, meta=meta)
        prose = []

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        if el.name in ("h2", "h3", "h4"):
            flush_prose()
            sec_ord += 1
            sec_key = make_anchor(cslug, f"sec-{sec_ord}")
            mch = _CHAPTER.match(t)
            sec_label = _chapter_label_from(mch) if mch else title_case_shouting(_declutter(t))
            continue
        if len(t) < _MIN:
            continue
        mc, mn, ml = _CANON.match(t), _NUM.match(t), _LEAD_CANON.match(t)
        if mc:
            flush_prose()
            num = mc.group(1)
            b.add(body=_declutter(t), ref=f"{council}, Canon {num}",
                  base_anchor=make_anchor(cslug, "canon", num),
                  ckey=sec_key, clabel=sec_label, unit=f"Canon {num}", meta=meta)
        elif ml:
            flush_prose()
            num = ml.group(1)
            b.add(body=_declutter(ml.group(2).strip()), ref=f"{council}, Canon {num}",
                  base_anchor=make_anchor(cslug, "canon", num),
                  ckey=sec_key, clabel=sec_label, unit=f"Canon {num}", meta=meta)
        elif mn:
            flush_prose()
            num = mn.group(1)
            b.add(body=_declutter(mn.group(2).strip()), ref=f"{council} — {sec_label}, §{num}",
                  base_anchor=make_anchor(cslug, f"sec-{sec_ord}", num),
                  ckey=sec_key, clabel=sec_label, unit=f"§{num}", meta=meta)
        else:
            decl = _declutter(t)
            if len(decl) >= _MIN:
                prose.append(decl)
                if sum(len(x) for x in prose) >= _TARGET:
                    flush_prose()
    flush_prose()
    return Document(id=did, collection="councils", title=council, author=None,
                    year=entry["year"], metadata={"url": entry["url"],
                    "council_number": entry.get("council_number")}, passages=b.passages)


def build_vatican2(entry: dict, soup: BeautifulSoup) -> Document:
    _strip_chrome(soup)
    title = entry["document"]
    dslug = slugify(title)
    did = document_id("councils", "Second Vatican Council", title)
    b = _Builder()
    meta = {"council": "Second Vatican Council",
            "document_type": entry.get("document_type"), "year": entry["year"],
            "url": entry["url"]}
    chap_ord, chap_key, chap_label = 0, make_anchor(dslug, "chap-0"), title

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "strong"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        mch = _CHAPTER.match(t)
        if mch:
            chap_ord += 1
            chap_key = make_anchor(dslug, f"chap-{chap_ord}")
            chap_label = _chapter_label_from(mch)
            continue
        if el.name != "p":
            continue
        mn = _NUM.match(t)
        if not mn:
            continue
        body = _declutter(mn.group(2).strip())
        if len(body) < _MIN:
            continue
        num = mn.group(1)
        b.add(body=body, ref=f"{title}, §{num}",
              base_anchor=make_anchor(dslug, f"chap-{chap_ord}", num),
              ckey=chap_key, clabel=chap_label, unit=f"§{num}", meta=meta)
    return Document(id=did, collection="councils", title=title, author=None,
                    year=entry["year"], metadata=meta, passages=b.passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    docs: list[Document] = []
    for entry in manifest:
        with open(os.path.join(_SRC, entry["file"]), "rb") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        if entry["group"] == "vatican-ii":
            docs.append(build_vatican2(entry, soup))
        else:
            docs.append(build_ecumenical(entry, soup))
    return docs
