"""Apostolic Exhortations ingestion (dual pipeline).

One Document per exhortation from vendored HTML. Same typed-stream tokenizer
as encyclicals — handles three numbering layouts (inline `N. body`, bold
heading + following body, and section headers).
"""
from __future__ import annotations

import json
import os
import re

from bs4 import BeautifulSoup

from config import settings
from identity import anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.footnotes import strip_footnote_markers
from normalize.boilerplate import strip_boilerplate
from ingest.pieces import (Segment, element_locator, name_pieces, number_elements,
                           pack_text, piece_reference,
                           unique_unit_anchors)
from registry import ANCHOR_SCHEME, resolve_document_id

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "apostolic-exhortations")
_NUM = re.compile(r"^(\d+)\s*\.\s*(.*)", re.DOTALL)
_ROMAN = re.compile(r"^[IVX]+\.\s+\S")
_BUCKET = 20
_CHROME = re.compile(
    r"automatically notified|more information about this site|fan of our facebook"
    r"|^search tips$|^sitemap$|return to (?:the )?home", re.IGNORECASE)


def _strip_leading_caps(text: str) -> str:
    words = text.split()
    i = 0
    while i < len(words):
        letters = [c for c in words[i] if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            i += 1
        else:
            break
    return " ".join(words[i:])


def _is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.7


def _is_bold_only(p) -> bool:
    kids = [c for c in p.children if getattr(c, "name", None)]
    bare = "".join(str(c) for c in p.children if not getattr(c, "name", None)).strip()
    t = p.get_text(strip=True)
    return (len(kids) == 1 and kids[0].name in ("b", "strong")
            and not bare and len(t) >= 8 and not t.endswith(":"))


_NOTES_HEADING = re.compile(r"^(?:END)?NOTES?$|^FOOTNOTES?$", re.IGNORECASE)


def _tokens(soup) -> list[tuple[str, int | None, str, list[Segment]]]:
    """Return an ordered list of ('preamble'|'section'|'para', num|None, text,
    source segments), each segment one `<p>` named by its ordinal in the file."""
    number_elements(soup)
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    items = [(p, p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    items = [(p, t) for p, t in items if t and not _CHROME.search(t)]
    for i, (_, t) in enumerate(items):
        if _NOTES_HEADING.match(t.strip()):
            items = items[:i]
            break
    toks: list[tuple[str, int | None, str, list[Segment]]] = []
    seen = False
    cur: list | None = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            toks.append(("para", cur[0], "\n\n".join(x for x in cur[1] if x),
                         [seg for seg in cur[2] if seg.text]))
            cur = None

    for p, t in items:
        m = _NUM.match(t)
        is_roman = bool(_ROMAN.match(t))
        is_bold = _is_bold_only(p)
        if not seen:
            if m:
                seen = True
                body = m.group(2).strip()
                cur = [int(m.group(1)), [body] if body else [],
                       [Segment(element_locator(p), body)]]
            elif is_roman:
                toks.append(("section", None, t, [Segment(element_locator(p), t)]))
            else:
                toks.append(("preamble", None, t, [Segment(element_locator(p), t)]))
            continue
        if m:
            flush()
            body = m.group(2).strip()
            cur = [int(m.group(1)), [body] if body else [], [Segment(element_locator(p), body)]]
            continue
        if is_roman or is_bold:
            flush()
            toks.append(("section", None, t, [Segment(element_locator(p), t)]))
            continue
        if cur is not None:
            cur[1].append(t)
            cur[2].append(Segment(element_locator(p), t))
    flush()
    last_para_num = 0
    for i, (k, n, t, _) in enumerate(toks):
        if k == "para" and n is not None:
            if n < last_para_num and n <= 3:
                remaining = [tt for kk, _, tt, _ in toks[i:] if kk == "para"]
                if remaining and sum(len(tt) for tt in remaining) / len(remaining) < 150:
                    toks = toks[:i]
                    break
            last_para_num = n
    # Unnumbered fallback: if no numbered paragraphs were found, re-classify
    # preamble tokens so the body text isn't silently dropped.
    if not any(k == "para" for k, _, _, _ in toks):
        retyped: list[tuple[str, int | None, str, list[Segment]]] = []
        n = 1
        for k, _, t, segs in toks:
            if k != "preamble":
                retyped.append((k, None, t, segs))
                continue
            if _is_shouting(t):
                retyped.append(("section", None, t, segs))
            else:
                retyped.append(("para", n, t, segs))
                n += 1
        toks = retyped
    cleaned: list[tuple[str, int | None, str, list[Segment]]] = []
    for i, tok in enumerate(toks):
        if tok[0] == "section":
            following = toks[i + 1:]
            nxt_sec = next((j for j, x in enumerate(following) if x[0] == "section"), len(following))
            if not any(x[0] == "para" for x in following[:nxt_sec]):
                continue
        cleaned.append(tok)
    return cleaned


def _disambiguate_title(title: str, slug: str, year: int) -> str:
    base_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return title if slug == base_slug else f"{title} ({year})"


def build_document(entry: dict) -> Document:
    path = os.path.join(_SRC, entry["file"])
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    toks = _tokens(soup)
    slug, author = entry["slug"], entry["author"]
    title = _disambiguate_title(entry["title"], slug, entry["year"])
    source_key = f"apostolic-exhortations/{slug}"
    did = resolve_document_id("apostolic-exhortations", source_key,
                              ("apostolic-exhortations", slug))
    has_sec = any(k == "section" for k, _, _, _ in toks)
    meta = {"pope": author, "url": entry["url"]}
    units: list[tuple] = []

    def emit(content: str, ref: str, base_anchor: str, ckey: str, clabel: str,
             unit: str | None, segments: list[Segment]) -> None:
        content = clean_text(strip_footnote_markers(strip_boilerplate(content)))
        if not content:
            return
        pieces = pack_text(content, segments, settings.MAX_PASSAGE_CHARS)
        units.append((content, pieces, ref, base_anchor, ckey, clabel, unit, segments))

    pre_parts: list[str] = []
    pre_segments: list[Segment] = []
    for k, _, t, segs in toks:
        if k != "preamble":
            continue
        if _is_shouting(t):
            break
        pre_parts.append(t)
        pre_segments += segs
    pre = _strip_leading_caps("\n\n".join(pre_parts).strip()).strip()
    if pre:
        emit(pre, f"{title} — Preamble", make_anchor(slug, "preamble"),
             make_anchor(slug, "preamble"), "Preamble", None, pre_segments)

    bucket_range: dict[int, tuple[int, int]] = {}
    if not has_sec:
        for k, n, _, _ in toks:
            if k != "para":
                continue
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range.get(b, (n, n))
            bucket_range[b] = (min(lo, n), max(hi, n))

    sec_ord = 0
    cur_key = cur_label = None
    for k, n, t, segs in toks:
        if k == "preamble":
            continue
        if k == "section":
            sec_ord += 1
            cur_key = make_anchor(slug, f"sec-{sec_ord}")
            cur_label = title_case_shouting(clean_text(t))
            continue
        if has_sec:
            if cur_key is None:
                cur_key, cur_label = make_anchor(slug, "sec-0"), "Introduction"
            ckey, clabel = cur_key, cur_label
        else:
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range[b]
            clabel = f"Paragraphs {lo}–{hi}" if lo != hi else f"Paragraph {lo}"
            ckey = make_anchor(slug, f"bucket-{b}")
        emit(t, f"{title}, §{n}", make_anchor(slug, n), ckey, clabel, f"§{n}", segs)

    passages: list[Passage] = []
    anchors = unique_unit_anchors([u[3] for u in units], [len(u[1]) > 1 for u in units])
    for (content, pieces, ref, _, ckey, clabel, label, segments), anc in zip(units, anchors):
        for k, (piece, (anchor, held)) in enumerate(
                zip(pieces, name_pieces(anc, content, pieces, segments)), 1):
            passages.append(Passage(content=piece,
                                    reference=piece_reference(ref, None, None, k, len(pieces)),
                                    anchor=anchor,
                                    chapter_key=ckey, chapter_label=clabel,
                                    position=len(passages), unit_label=label, metadata=meta,
                                    source_units=held))
    return Document(id=did, collection="apostolic-exhortations", title=title, author=author,
                    year=entry["year"], metadata={"url": entry["url"], "pope": author,
                              "source_key": source_key, "anchor_scheme": ANCHOR_SCHEME},
                    passages=passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e) for e in manifest]
