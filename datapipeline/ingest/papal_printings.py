"""Older papal documents from public-domain printings (corpus-cleanup 1.3d, ADR 0001).

A document R8 traced to an English printing before 1931 (or a later one never renewed)
takes its text from that printing instead of papalencyclicals.net's page, which stays
vendored and unread. `papal_printings.json` names, per document, the printing (a
transcription, or a scan whose text comes through 1.2f's clean-up and gate, frozen in
`ocr/texts/<work>.json`), its URL (which becomes `metadata.url`) and what the reviewed
alignment with the site's paragraphs decided:

- `units`: every printed block of the text, in order, by its opening words, and the unit
  it belongs to: `"preamble"`, `"preface"` (prose before the first paragraph, 1.3a),
  `"section"` (a heading that opens a chapter), `"epigraph"` (text under a heading that
  is no paragraph, as the site's Syllabus section IV, 1.3a), the site's paragraph number
  it is (a number printed before it is not text) (the unit keeps that
  anchor and ID, D1), or `"+"` for a block that continues the unit before it (a paragraph
  the printing divides where the site does not), or `"omit"` for an editor's heading set
  in the same line as the text, up to its `until` (rule G, with its `why`). A site
  paragraph the printing runs into the one before has no unit here; its anchor redirects
  to the unit holding its text.
- `editorial`: blocks the printing's editor wrote (a magazine's introduction, a heading
  the editor set), never emitted (rule G), each with its reason.
- `fixes`: places where a transcription misreads the page, each checked on the page
  image, with its reason (a scan's are the OCR tool's, `ocr/works/<work>.fixes.json`).
  The printing's own spellings and misprints stay.

A dating line or signature after the last unit joins it, as on the site (1.3a). Every
passage declares `text_replaced`, since the printing is another translation or edition.

A document still built from the site's page can take a passage from a printing too
(`papal_additions.json`, `additions`): a text the site's page holds only in a translation
held for permission, which the printing gives (Exsurge Domine's censure, from Deferrari's
p. 243, 5.9). It is its own unit and chapter, after the paragraph it follows, and carries
the printing's URL and scan label; the site's passages are unchanged.
"""
from __future__ import annotations

import functools
import json
import os
import re
from dataclasses import dataclass, field, replace

from bs4 import BeautifulSoup

from config import settings
from ingest import papal_common
from ingest.papal_common import Token
from ingest.pieces import Segment
from model import Document
from ocr.fixes import read_text

_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papal_printings.json")
_ADDITIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papal_additions.json")
_SPACE = re.compile(r"\s+")
_INVISIBLE = re.compile("[​­﻿]")
_BROKEN_WORD = re.compile(r"[a-z]-$")    # a word broken at a line end


@dataclass(frozen=True)
class Unit:
    opens: str
    unit: str | int          # "preamble", "preface", "section", "epigraph", the site's
                             # paragraph number, "+", or "omit"
    # Where the block's next unit opens inside it, if the printing sets the two on one
    # line (a greeting run into the first paragraph): the rest is the next block.
    until: str | None = None
    why: str | None = None   # an omitted heading's reason


@dataclass(frozen=True)
class Printing:
    key: str                 # "<collection>/<slug>"
    source: str              # "wikisource", or "ocr" (a scan, through 1.2f's clean-up)
    file: str                # under sources/<collection>/: the transcription, or the scan's folder
    work: str | None         # an OCR printing's work (`ocr/works/<work>.json`)
    url: str
    translation: str
    units: tuple[Unit, ...]
    editorial: tuple[dict, ...] = ()
    fixes: tuple[dict, ...] = field(default=())
    # False where the site's page prints no paragraph numbers either (Sublimis Deus): its
    # units keep their places as anchors and cite no number (1.3a).
    numbered: bool = True
    # An extract or abridgement (1.3d step 6): the site's paragraphs the printing lacks, by
    # number, or "preamble" where it lacks the site's address (Qui Nuper).
    # They are held for permission (a `passage`-scope `awaiting-permission` removal each),
    # the site's page stays the document's `held_text_url`, and `notes` say what is
    # missing, for the reader's overview.
    omits: tuple[int | str, ...] = ()
    notes: str | None = None
    # A reader note on every passage (Deferrari's extracts, R9: "Extract, in ...").
    passage_note: str | None = None
    # The printing ends each unit with the letter it was condemned in (the Syllabus):
    # each citation becomes its own "[Source: ...]" paragraph (`mark_sources`).
    marks_sources: bool = False

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
        out[key] = Printing(key=key, source=d["source"], file=d["file"], work=d.get("work"),
                            url=d["url"],
                            translation=d["translation"],
                            units=tuple(Unit(u["opens"], u["unit"], u.get("until"), u.get("why"))
                                        for u in d["units"]),
                            editorial=tuple(d.get("editorial", ())),
                            fixes=tuple(d.get("fixes", ())),
                            numbered=d.get("numbered", True),
                            omits=tuple(d.get("omits", ())), notes=d.get("notes"),
                            passage_note=d.get("passage_note"),
                            marks_sources=d.get("marks_sources", False))
    return out


def printing(collection: str, slug: str) -> Printing | None:
    return printings().get(f"{collection}/{slug}")


@dataclass(frozen=True)
class Addition:
    key: str                 # "<collection>/<slug>" of a document built from the site's page
    work: str                # the scan's OCR work (`ocr/texts/<work>.json`), all of it
    url: str                 # the printing's URL, the passage's `url`
    part: str                # its unit anchor's part ("censure" → `exsurge-domine/censure`)
    label: str               # its unit label, chapter label and citation ("Censure")
    after: int               # the site's paragraph it follows
    why: str


@functools.cache
def additions() -> dict[str, tuple[Addition, ...]]:
    with open(_ADDITIONS, encoding="utf-8") as f:
        data = json.load(f)
    return {key: tuple(Addition(key=key, **a) for a in items)
            for key, items in data.items() if not key.startswith("_")}


def with_additions(doc: Document, collection: str, slug: str) -> Document:
    """`doc` with the passages a printing adds to it (`papal_additions.json`), each its own
    unit and chapter after the paragraph it follows, which must end its chapter, and
    positions renumbered."""
    adds = additions().get(f"{collection}/{slug}", ())
    if not adds:
        return doc
    passages = list(doc.passages)
    for a in adds:
        after = papal_common._anchor(slug, str(a.after))
        at = [k for k, x in enumerate(passages) if papal_common.unit_anchor(x.anchor) == after]
        if not at:
            raise ValueError(f"{a.key}: no paragraph {a.after} for {a.part!r} to follow")
        # Its own chapter, so only after a chapter's last passage: the reader groups a
        # chapter's passages, and one left after it would show before the addition.
        if at[-1] + 1 < len(passages) and \
                passages[at[-1] + 1].chapter_key == passages[at[-1]].chapter_key:
            raise ValueError(f"{a.key}: paragraph {a.after} does not end its chapter")
        frozen = read_text(a.work)
        blocks = ocr_blocks(frozen)
        text = papal_common._clean("\n\n".join(t for _, t in blocks), slug, callers=False)
        segments = [Segment(loc, t) for loc, t in blocks]
        anchor = papal_common._anchor(slug, a.part)
        unit = papal_common._Unit(text, papal_common.pack_text(text, segments,
                                                               settings.MAX_PASSAGE_CHARS),
                                  f"{doc.title}, {a.label}", anchor, anchor, a.label,
                                  a.label, segments)
        meta = {"pope": doc.author, "url": a.url, "source_url": a.url, **frozen["metadata"]}
        passages[at[-1] + 1:at[-1] + 1] = papal_common._passages([unit], doc.title, meta)
    return replace(doc, passages=[replace(x, position=k) for k, x in enumerate(passages)])


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
    queue = list(blocks)
    closing = False
    kind = "para" if p.numbered else "text"
    while queue:
        loc, text = queue.pop(0)
        if any(text.startswith(e["opens"]) for e in p.editorial):
            continue
        if units and text.startswith(units[0].opens):
            u = units.pop(0)
            if u.until:
                cut = text.find(u.until)
                if cut <= 0:
                    raise ValueError(f"{p.key}: {u.opens!r} holds no {u.until!r}")
                queue.insert(0, (f"{loc}-2", text[cut:]))
                text = text[:cut].rstrip()
            seg = Segment(loc, text)
            if u.unit == "omit":            # an editor's heading run into the text (rule G)
                continue
            if u.unit in ("preamble", "preface", "section", "epigraph"):
                toks.append(Token(u.unit, None, text, [seg]))
            elif u.unit == "+":
                if not toks or toks[-1].kind != kind:
                    raise ValueError(f"{p.key}: {u.opens!r} continues no paragraph")
                last = toks[-1]
                toks[-1] = last._replace(text=f"{last.text}\n\n{text}",
                                         segments=last.segments + [seg])
            else:
                # The number a printing sets before its paragraph is the unit's number,
                # not its text (the Syllabus's "1. There exists …").
                text = re.sub(rf"^{int(u.unit)}\.\s+", "", text)
                toks.append(Token(kind, int(u.unit), text, [Segment(loc, text)]))
            continue
        # After the last unit: its dating line or signature, and the lines that finish
        # the date ("In the nineteenth year of Our Pontificate.") or sign it in capitals
        # ("PIUS P. P. IX.").
        if not units and toks and toks[-1].kind == kind and (
                papal_common._DATING.match(text) or papal_common._SIGNED.match(text)
                or (closing and papal_common._DATED.search(text)
                    and len(text) < papal_common._DATE_CARD_MAX)
                or (closing and len(text) <= papal_common._SIGNATURE_MAX
                    and papal_common.is_shouting(text))):
            closing = True
            last = toks[-1]
            toks[-1] = last._replace(text=f"{last.text}\n\n{text}",
                                     segments=last.segments + [Segment(loc, text)])
            continue
        raise ValueError(f"{p.key}: block {loc} is in no unit: {text[:80]!r}"
                         + (f" (next unit opens {units[0].opens!r})" if units else ""))
    if units:
        raise ValueError(f"{p.key}: no block opens {units[0].opens!r}")
    return toks


def ocr_blocks(text: dict) -> list[tuple[str, str]]:
    """A scanned printing's frozen text (`ocr/texts/<work>.json`, 1.2f) as (locator, text)
    blocks: each passage's paragraphs in turn, named `p<n>`. A paragraph the clean-up
    cut for correction (`continues`) joins the one before it again; where that one ends
    on a word broken at a line end ("philoso-" before "phy;"), the word is whole again."""
    blocks: list[tuple[str, str]] = []
    for passage in text["passages"]:
        for k, para in enumerate(passage["text"].split("\n\n")):
            para = _norm(para)
            if k == 0 and passage.get("continues") and blocks:
                before = blocks[-1][1]
                joined = (before[:-1] + para if _BROKEN_WORD.search(before) and para[:1].islower()
                          else f"{before} {para}")
                blocks[-1] = (blocks[-1][0], joined)
            elif para:
                blocks.append((f"p{len(blocks)}", para))
    return blocks


def blocks_of(p: Printing, src_dir: str) -> list[tuple[str, str]]:
    if p.source == "wikisource":
        return apply_fixes(wikisource_blocks(os.path.join(src_dir, p.file)), p.fixes)
    if p.source == "ocr":
        return apply_fixes(ocr_blocks(read_text(p.work)), p.fixes)
    raise ValueError(f"{p.key}: unknown printing source {p.source!r}")


def build_document(entry: dict, collection: str, src_dir: str) -> Document:
    return build_printed(printing(collection, entry["slug"]), entry, collection, src_dir)


def build_printed(p: Printing, entry: dict, collection: str, src_dir: str) -> Document:
    toks = printed_tokens(p, blocks_of(p, src_dir))
    # A scanned printing's passages carry its label (`text_source`, `scan_id`; 1.2f).
    label = read_text(p.work)["metadata"] if p.source == "ocr" else None
    # `source_file` names the printing's folder, as its rights row does (`source_path`).
    # 0.1a's coverage does not measure it (the site's page is not this document's source;
    # `tests/test_papal_printings.py` measures the printing).
    built = {t.number if t.number is not None else t.kind for t in toks}
    if built & set(p.omits):
        raise ValueError(f"{p.key}: units both printed and omitted: {sorted(built & set(p.omits))}")
    if bool(p.omits) != bool(p.notes):
        raise ValueError(f"{p.key}: an extract names its omitted paragraphs and its notes together")
    metadata = {"source_file": p.folder}
    if p.omits:
        metadata["held_text_url"] = entry["url"]
    doc = papal_common.document_from_tokens(
        entry, collection, toks, url=p.url, text_replaced=p.text_replaced,
        translation=p.translation, metadata=metadata, passage_metadata=label,
        callers=False)
    doc.notes = p.notes
    if p.passage_note:
        doc.passages = [replace(x, note=p.passage_note) for x in doc.passages]
    if p.marks_sources:
        marked = mark_sources([x.content for x in doc.passages])
        doc.passages = [replace(x, content=c) for x, c in zip(doc.passages, marked)]
    return doc


# A citation of the letter a proposition was condemned in, as the Syllabus prints them:
# a line of its own, or the end of the proposition's paragraph.
_CITED = r"(?:Allocution|Apostolic(?:al)? Letters?|Letters?|Encyclical|Epistle)\b[^\n]*?\b1[78]\d\d\b(?:, etc)?\."
_CITATION_LINE = re.compile(rf"^(?:Ibid\b[^\n]*|{_CITED})$")
_CITATION_END = re.compile(rf"(?<=[.?!])\s+(Ibid[.,]?|{_CITED})$")
_IBID = re.compile(r"^Ibid[.,]*\s*(.*?)\.?$")
_MONTH = r"(?:Jan|Feb|March|Mar|April|Apr|May|June|July|Aug|Sept|Sep|Oct|Nov|Dec)\b"


def mark_sources(texts: list[str]) -> list[str]:
    """Each passage's closing citation as its own paragraph, "[Source: ...]", so a reader
    sees it is a citation (Carter, 13 Nov 2026). The printed words stay; an "Ibid." also
    names the source it stands for, the last citation before it that names one."""
    last = None
    out = []
    for text in texts:
        paras = text.split("\n\n")
        printed = None
        if _CITATION_LINE.match(paras[-1]) and len(paras) > 1:
            printed = paras.pop()
        else:
            m = _CITATION_END.search(paras[-1])
            if m:
                printed, paras[-1] = m.group(1), paras[-1][:m.start()]
        if printed is None:
            out.append(text)
            continue
        m = _IBID.match(printed)
        if m is None:
            last = re.sub(r"(?:, etc)?\.$", "", printed)
            cited = printed.rstrip(".")
        else:
            if last is None:
                raise ValueError(f"no source before {printed!r}")
            rest = m.group(1)
            if not rest:
                cited = f"Ibid., {last}"
            elif rest.startswith("and "):
                # "Ibid., and Encyclical ...": both, and a later bare "Ibid." means both.
                last = f"{last}, {rest}"
                cited = f"Ibid., {last}"
            elif re.match(_MONTH, rest):
                # "Ibid, Dec. 11th, 1862": the same letters, this one; a later bare
                # "Ibid." means it.
                series = re.split(rf",\s*{_MONTH}", last)[0]
                last = f"{series}, {rest}"
                cited = f"Ibid., {last}"
            else:
                raise ValueError(f"cannot read {printed!r}")
        out.append("\n\n".join(paras + [f"[Source: {cited}]"]))
    return out
