"""Roman Curia ingestion: doctrinal documents of the Dicastery for the Doctrine of the Faith.

vatican.va pages for this office come in two shapes. Newer documents number their
paragraphs ("12. ..."); older ones and short responses do not. Both carry a language bar,
a title block in capitals, a signature block, and an endnote list at the foot.

The adapter keeps real paragraph numbers where the document has them and never invents
them where it does not. Unnumbered text is grouped by section heading into passages of
readable size. Endnotes are cut: bracketed note lists, runs of marked note lines, and a
plain-numbered tail that counts down to note 1.
"""
from __future__ import annotations

import json
import os
import re

from bs4 import BeautifulSoup

from config import settings
from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.footnotes import strip_footnote_markers
from normalize.boilerplate import strip_boilerplate
from ingest.common import split_display_passage

COLLECTION = "roman-curia"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", COLLECTION)

_NUM = re.compile(r"^(\d{1,3})\s*\.\s+(\S.*)", re.DOTALL)
_NOTE = re.compile(r"^(?:\[(\d{1,3})\]|\((\d{1,3})\)|(\d{1,3})\s*[.)])\s*\S")
_BRACKET_NOTE = re.compile(r"^[\[(]\s*\d{1,3}\s*[\])]\s*\S")
_AAS_REF = re.compile(r"^\*\s*AAS\s+\d")  # "* AAS 82 (1990) 362-379." source line
_LANG_BAR = re.compile(r"^\[\s*(?:[A-Z]{2}(?:_[A-Z]{2})?\s*-\s*)*[A-Z]{2}(?:_[A-Z]{2})?\s*\]$")
_ROMAN = re.compile(r"^[IVXLC]{1,6}\.?$")
_ROMAN_TITLE = re.compile(r"^[IVXLC]{1,6}\.\s+\S")
_NOTES_HEADING = re.compile(r"^(?:END)?NOTES?$|^FOOTNOTES?$", re.IGNORECASE)
_SIGNATURE = re.compile(r"\b(?:Prefect|Secretary|Under-?Secretary|Prefetto|Segretario)\b")
_SENTENCE_END = (".", ":", ";", "?", "!", "”", '"', "»", ")")
# Unnumbered text is grouped into passages of about this size before the display split.
_GROUP_TARGET = 1200


def _texts(soup) -> list[tuple[object, str]]:
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    out = []
    for p in soup.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        if t and not _LANG_BAR.match(t) and not _AAS_REF.match(t):
            out.append((p, t))
    return out


def _note_number(text: str) -> int | None:
    m = _NOTE.match(text)
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def cut_notes(lines: list[str]) -> list[str]:
    """Drop the endnote list: an explicit Notes heading, or a tail counting down to note 1.

    Walking back from the end, numbered lines must descend by one; unnumbered lines are
    continuations of the note above them. The cut happens only when the walk reaches note
    1, so a document whose body paragraphs are numbered keeps them.
    """
    for i, t in enumerate(lines):
        # "Note" is also a genre heading at the top of a page, so a Notes heading counts
        # only when note 1 follows it.
        if _NOTES_HEADING.match(t) and i + 1 < len(lines) and _note_number(lines[i + 1]) == 1:
            return lines[:i]
    # A note block in the middle of a page (a second document's notes, or a
    # presentation's) is a run of three or more marked lines.
    runs, i = [], 0
    while i < len(lines):
        j = i
        while j < len(lines) and _BRACKET_NOTE.match(lines[j]):
            j += 1
        if j - i >= 3:
            runs.append((i, j))
        i = max(j, i + 1)
    for a, b in reversed(runs):
        lines = lines[:a] + lines[b:]
    # Bracketed markers ("[12] ...") never open a body paragraph, so they settle it: cut at
    # the first [1] whose tail is mostly notes, and drop any stray bracketed note lines
    # (a presentation's own notes, placed mid-page).
    for i, t in enumerate(lines):
        # Note 1 is sometimes fused into the paragraph before it, so any bracketed note
        # can open the list.
        if _BRACKET_NOTE.match(t):
            tail = lines[i:]
            if sum(1 for x in tail if _BRACKET_NOTE.match(x)) / len(tail) >= 0.6:
                return [x for x in lines[:i] if not _BRACKET_NOTE.match(x)]
    expected = None
    for i in range(len(lines) - 1, -1, -1):
        n = _note_number(lines[i])
        if n is None:
            continue  # a note running over more than one paragraph
        if expected is not None and n != expected:
            return lines
        if n > 1:
            expected = n - 1
            continue
        # Reached note 1. A body that numbers its own paragraphs 1..N also counts down to
        # 1, so cut only when this tail looks like notes: bracketed markers, or short
        # entries after a body longer than the tail.
        tail, body = lines[i:], lines[:i]
        bracketed = lines[i].lstrip().startswith("[")
        short = sum(len(t) for t in tail) / len(tail) < 500
        longer_body = sum(len(t) for t in body) > sum(len(t) for t in tail)
        return body if bracketed or (short and longer_body) else lines
    return lines


def _is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def _is_bold_only(p) -> bool:
    kids = [c for c in getattr(p, "children", []) if getattr(c, "name", None)]
    bare = "".join(str(c) for c in getattr(p, "children", [])
                   if not getattr(c, "name", None)).strip()
    return len(kids) == 1 and kids[0].name in ("b", "strong", "i", "em") and not bare


def _is_heading(p, text: str) -> bool:
    if _NUM.match(text):
        return False
    if _ROMAN.match(text) or (_ROMAN_TITLE.match(text) and len(text) <= 120):
        return True
    if len(text) > 120 or text.endswith(_SENTENCE_END + (",",)):
        return False
    return True


def _numbered_heading(rest: str) -> bool:
    """ "1. A Growing Awareness of Human Dignity": a numbered section title, not a paragraph."""
    return len(rest) <= 100 and not rest.endswith(_SENTENCE_END + (",",))


_DATELINE = re.compile(r"^(?:Given (?:at|in) |Rome, |From the Offices?|Vatican City|Vatican, )")
_OPENER = re.compile(r"^(?:Presentation|Introduction|Preface|Foreword|Premise|Prologue)$", re.IGNORECASE)
_TOC = re.compile(r"^(?:table of )?contents$|^index$", re.IGNORECASE)


def _drop_contents(items: list[tuple[object, str]]) -> list[tuple[object, str]]:
    """Remove a table of contents: its entries repeat as headings further down."""
    for i, (_, t) in enumerate(items):
        if _TOC.match(t) and i + 1 < len(items):
            first = items[i + 1][1]
            for j in range(i + 2, len(items)):
                if items[j][1] == first:
                    return items[:i] + items[j:]
            return items
    return items


def tokens(soup) -> list[tuple[str, int | None, str]]:
    """Return ("title"|"section"|"para", number, text) tokens for one page.

    Before the first sentence of body text, lines are the title block (office name,
    genre, title, subtitle) and are dropped: the manifest carries the title.
    """
    items = _texts(soup)
    keep = cut_notes([t for _, t in items])
    kept, j = [], 0
    for p, t in items:  # keep is an order-preserving subsequence of the texts
        if j < len(keep) and t == keep[j]:
            kept.append((p, t))
            j += 1
    items = _drop_contents(kept)
    items = [(p, t) for p, t in items
             if not (len(t) < 140 and _SIGNATURE.search(t) and not t.endswith("."))]
    toks: list[tuple[str, int | None, str]] = []
    body_started = False
    for p, t in items:
        m = _NUM.match(t)
        if m and body_started and _numbered_heading(m.group(2).strip()):
            toks.append(("section", None, t))
        elif m:
            body_started = True
            toks.append(("para", int(m.group(1)), m.group(2).strip()))
        elif _ROMAN.match(t) or (_ROMAN_TITLE.match(t) and len(t) <= 120):
            toks.append(("section", None, t))
        elif not body_started and (_is_shouting(t) or not t.endswith(_SENTENCE_END)):
            toks.append(("title", None, t))
        elif _is_heading(p, t):
            toks.append(("section", None, t))
        elif _DATELINE.match(t) and len(t) < 250 and toks and toks[-1][0] == "para":
            k, n, prev = toks[-1]
            toks[-1] = (k, n, prev + "\n\n" + t)  # the closing dateline stays with the text
        else:
            body_started = True
            toks.append(("para", None, t))
    # An opening heading directly after the title block (Presentation, Introduction) is
    # a section.
    for i, (k, n, t) in enumerate(toks):
        if k == "para":
            if i and toks[i - 1][0] == "title" and _OPENER.match(toks[i - 1][2]):
                toks[i - 1] = ("section", None, toks[i - 1][2])
            break
    return toks


def _section_label(text: str) -> str:
    t = clean_text(text)
    return title_case_shouting(t) if _is_shouting(t) else t


def build_document(entry: dict) -> Document:
    with open(os.path.join(_SRC, entry["file"]), "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    toks = tokens(soup)
    slug, title = entry["slug"], entry["title"]
    did = document_id(COLLECTION, slug)
    meta = {"issuer": entry["author"], "genre": entry.get("genre"), "url": entry["url"]}
    numbered = any(k == "para" and n is not None for k, n, _ in toks)

    passages: list[Passage] = []
    seen: set[str] = set()

    def emit(content: str, ref: str, base: str, ckey: str, clabel: str, unit: str | None) -> None:
        content = clean_text(strip_footnote_markers(strip_boilerplate(content)))
        if not content:
            return
        pieces = split_display_passage(content, settings.MAX_PASSAGE_CHARS)
        for j, piece in enumerate(pieces):
            anc = base + (f"/p{j + 1}" if len(pieces) > 1 else "")
            k = 1
            while anc in seen:
                k += 1
                anc = f"{base}-{k}" + (f"/p{j + 1}" if len(pieces) > 1 else "")
            seen.add(anc)
            passages.append(Passage(content=piece, reference=ref, anchor=anc,
                                    chapter_key=ckey, chapter_label=clabel,
                                    position=len(passages), unit_label=unit, metadata=meta))

    sec_ord = 0
    ckey, clabel = make_anchor(slug, "sec-0"), "Introduction" if numbered else title
    group: list[str] = []
    group_ord = 0
    cur_num: int | None = None
    cur_parts: list[str] = []

    def flush_group() -> None:
        nonlocal group, group_ord
        if group:
            group_ord += 1
            base = make_anchor(slug, f"sec-{sec_ord}", f"part-{group_ord}")
            ref = title if clabel == title else f"{title}, {clabel}"
            emit("\n\n".join(group), ref, base, ckey, clabel, None)
            group = []

    def flush_num() -> None:
        nonlocal cur_num, cur_parts
        if cur_num is not None:
            emit("\n\n".join(cur_parts), f"{title}, §{cur_num}", make_anchor(slug, cur_num),
                 ckey, clabel, f"§{cur_num}")
        cur_num, cur_parts = None, []

    for kind, n, text in toks:
        if kind == "title":
            continue
        if kind == "section":
            flush_num()
            flush_group()
            sec_ord += 1
            ckey, clabel = make_anchor(slug, f"sec-{sec_ord}"), _section_label(text)
            group_ord = 0
            continue
        if n is not None:
            flush_group()
            flush_num()
            cur_num, cur_parts = n, [text]
        elif cur_num is not None:
            cur_parts.append(text)  # an unnumbered paragraph continues the numbered one
        else:
            group.append(text)
            if sum(len(g) for g in group) >= _GROUP_TARGET:
                flush_group()
    flush_num()
    flush_group()

    return Document(id=did, collection=COLLECTION, title=title, author=entry["author"],
                    year=entry["year"], metadata=meta, passages=passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e) for e in manifest]
