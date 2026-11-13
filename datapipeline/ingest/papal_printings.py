"""Older papal documents from public-domain printings (corpus-cleanup 1.3d, ADR 0001).

A document R8 traced to an English printing before 1931 (or a later one never renewed)
takes its text from that printing instead of papalencyclicals.net's page, which stays
vendored and unread. `papal_printings.json` names, per document, the printing's file, its
URL (the transcription or the scan, which becomes `metadata.url`) and what the reviewed
alignment with the site's paragraphs decided:

- `units`: every printed block of the text, in order, by its opening words, and the unit
  it belongs to: `"preamble"`, the site's paragraph number it is (the unit keeps that
  anchor and ID, D1), or `"+"` for a block that continues the unit before it (a paragraph
  the printing divides where the site does not). A site paragraph the printing runs into
  the one before has no unit here; its anchor redirects to the unit holding its text.
- `editorial`: blocks the printing's editor wrote (a magazine's introduction, a heading
  the editor set), never emitted (rule G), each with its reason.
- `fixes`: places where the transcription misreads the page, each checked on the page
  image, with its reason. The printing's own spellings and misprints stay.

A dating line or signature after the last unit joins it, as on the site (1.3a). Every
passage declares `text_replaced`, since the printing is another translation or edition.
"""
from __future__ import annotations

import functools
import json
import os
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from ingest import papal_common
from ingest.papal_common import Token
from ingest.pieces import Segment
from model import Document

_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papal_printings.json")
_SPACE = re.compile(r"\s+")
_INVISIBLE = re.compile("[​­﻿]")


@dataclass(frozen=True)
class Unit:
    opens: str
    unit: str | int          # "preamble", the site's paragraph number, or "+"


@dataclass(frozen=True)
class Printing:
    key: str                 # "<collection>/<slug>"
    source: str              # "wikisource"
    file: str                # under sources/<collection>/
    url: str
    translation: str
    units: tuple[Unit, ...]
    editorial: tuple[dict, ...] = ()
    fixes: tuple[dict, ...] = field(default=())

    @property
    def folder(self) -> str:
        """The printing's folder under sources/<collection>/, with its closing slash."""
        return self.file.rsplit("/", 1)[0] + "/"

    @property
    def text_replaced(self) -> str:
        return f"{self.translation} replaces papalencyclicals.net"


@functools.cache
def printings() -> dict[str, Printing]:
    with open(_CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for key, d in data.items():
        if key.startswith("_"):
            continue
        out[key] = Printing(key=key, source=d["source"], file=d["file"], url=d["url"],
                            translation=d["translation"],
                            units=tuple(Unit(u["opens"], u["unit"]) for u in d["units"]),
                            editorial=tuple(d.get("editorial", ())),
                            fixes=tuple(d.get("fixes", ())))
    return out


def printing(collection: str, slug: str) -> Printing | None:
    return printings().get(f"{collection}/{slug}")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", _INVISIBLE.sub("", text)).strip()


def wikisource_blocks(path: str) -> list[tuple[str, str]]:
    """The transcribed text of a Wikisource page as (locator, text) blocks, in order:
    each paragraph or set-off line of its first page group, without page markers, note
    callers or the notes themselves (apparatus)."""
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    body = soup.select_one("div.prp-pages-output") or soup.select_one("div.mw-parser-output")
    for el in body.select("sup.reference, span.pagenum, style, link, .reflist, .references"):
        el.decompose()
    blocks = []
    for k, el in enumerate(e for e in body.children if getattr(e, "name", None) in ("p", "div")):
        text = _norm(el.get_text())
        if text:
            blocks.append((f"w{k}", text))
    return blocks


def apply_fixes(blocks: list[tuple[str, str]], fixes) -> list[tuple[str, str]]:
    """Each fix replaces its `find` once, in the one block holding it; a fix that matches
    nowhere, or more than once, is an error, so a fix never lands on other text."""
    out = list(blocks)
    for fix in fixes:
        hits = [(i, t) for i, (_, t) in enumerate(out) if fix["find"] in t]
        if len(hits) != 1 or hits[0][1].count(fix["find"]) != 1:
            raise ValueError(f"fix {fix['find']!r} must match exactly once, "
                             f"matched {sum(t.count(fix['find']) for _, t in hits)}")
        i, text = hits[0]
        out[i] = (out[i][0], text.replace(fix["find"], fix["replace"]))
    return out


def printed_tokens(p: Printing, blocks: list[tuple[str, str]]) -> list[Token]:
    """The printing's blocks as the parser's tokens, each placed by the reviewed `units`.
    Every block is a unit, an editorial block, or a closing line after the last unit;
    anything else is an error, so no printed text is silently lost."""
    units = list(p.units)
    toks: list[Token] = []
    for loc, text in blocks:
        seg = Segment(loc, text)
        if any(text.startswith(e["opens"]) for e in p.editorial):
            continue
        if units and text.startswith(units[0].opens):
            u = units.pop(0)
            if u.unit == "preamble":
                toks.append(Token("preamble", None, text, [seg]))
            elif u.unit == "+":
                if not toks or toks[-1].kind != "para":
                    raise ValueError(f"{p.key}: {u.opens!r} continues no paragraph")
                last = toks[-1]
                toks[-1] = last._replace(text=f"{last.text}\n\n{text}",
                                         segments=last.segments + [seg])
            else:
                toks.append(Token("para", int(u.unit), text, [seg]))
            continue
        if not units and toks and toks[-1].kind == "para" and (
                papal_common._DATING.match(text) or papal_common._SIGNED.match(text)):
            last = toks[-1]
            toks[-1] = last._replace(text=f"{last.text}\n\n{text}", segments=last.segments + [seg])
            continue
        raise ValueError(f"{p.key}: block {loc} is in no unit: {text[:80]!r}"
                         + (f" (next unit opens {units[0].opens!r})" if units else ""))
    if units:
        raise ValueError(f"{p.key}: no block opens {units[0].opens!r}")
    return toks


def blocks_of(p: Printing, src_dir: str) -> list[tuple[str, str]]:
    path = os.path.join(src_dir, p.file)
    if p.source == "wikisource":
        return apply_fixes(wikisource_blocks(path), p.fixes)
    raise ValueError(f"{p.key}: unknown printing source {p.source!r}")


def build_document(entry: dict, collection: str, src_dir: str) -> Document:
    p = printing(collection, entry["slug"])
    toks = printed_tokens(p, blocks_of(p, src_dir))
    # `source_file` names the printing's folder, as its rights row does (`source_path`).
    # 0.1a's coverage does not measure it (the site's page is not this document's source;
    # `tests/test_papal_printings.py` measures the printing).
    return papal_common.document_from_tokens(
        entry, collection, toks, url=p.url, text_replaced=p.text_replaced,
        translation=p.translation, metadata={"source_file": p.folder})
