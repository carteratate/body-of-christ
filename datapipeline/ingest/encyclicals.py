"""Encyclicals ingestion (dual pipeline).

One Document per encyclical from vendored HTML. A typed-stream tokenizer over
<p> handles three numbering layouts (inline `N. body`, bold heading + following
body, and section headers). One passage per numbered paragraph; chapters group
by section header, falling back to paragraph-range buckets.
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
from ingest.common import split_at_sentences, _split_at_whitespace

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "encyclicals")
_NUM = re.compile(r"^(\d+)\s*\.\s*(.*)", re.DOTALL)  # tolerate "10 ." (space before dot)
_ROMAN = re.compile(r"^[IVX]+\.\s+\S")
_BUCKET = 20
# papalencyclicals.net page chrome (nav/footer boilerplate that pollutes the
# <p> stream and otherwise masquerades as bold section headers).
_CHROME = re.compile(
    r"automatically notified|more information about this site|fan of our facebook"
    r"|^search tips$|^sitemap$|return to (?:the )?home", re.IGNORECASE)


def _strip_leading_caps(text: str) -> str:
    """Drop a leading run of ALL-CAPS words (a Latin incipit / title masthead that
    shares a paragraph with the greeting, e.g. 'IOANNES PAULUS PP. II EVANGELIUM
    VITAE To the Bishops…' → 'To the Bishops…'). Stops at the first word with a
    lowercase letter, so normal greetings ('To Our…', 'Venerable…') are untouched."""
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
    """True for an ALL-CAPS masthead line (e.g. 'ENCYCLICAL LETTER … OF THE
    SUPREME PONTIFF …'); used to keep the document title block out of the
    preamble passage. Mixed-case greetings (~0–15% caps) are kept."""
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


def _tokens(soup) -> list[tuple[str, int | None, str]]:
    """Return an ordered list of ('preamble'|'section'|'para', num|None, text)."""
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    items = [(p, p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    items = [(p, t) for p, t in items if t and not _CHROME.search(t)]
    toks: list[tuple[str, int | None, str]] = []
    seen = False
    cur: list | None = None   # [num, [parts]]

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            toks.append(("para", cur[0], "\n\n".join(x for x in cur[1] if x)))
            cur = None

    for p, t in items:
        m = _NUM.match(t)
        is_roman = bool(_ROMAN.match(t))
        is_bold = _is_bold_only(p)
        if not seen:
            if m:
                seen = True
                body = m.group(2).strip()
                cur = [int(m.group(1)), [body] if body else []]
            elif is_roman:
                # A genuine Roman-numeral section can open the document before §1.
                toks.append(("section", None, t))
            else:
                # Title/subtitle/greeting (incl. bold-only) before §1 is noise.
                toks.append(("preamble", None, t))
            continue
        if m:
            flush()
            body = m.group(2).strip()
            cur = [int(m.group(1)), [body] if body else []]
            continue
        if is_roman or is_bold:
            flush()
            toks.append(("section", None, t))
            continue
        if cur is not None:        # stray prose => body of the open paragraph
            cur[1].append(t)
    flush()
    # Drop sections that have no paragraph before the next section/EOF — leftover
    # nav/footer headers that slipped past the chrome filter add no real chapter.
    cleaned: list[tuple[str, int | None, str]] = []
    for i, tok in enumerate(toks):
        if tok[0] == "section":
            following = toks[i + 1:]
            nxt_sec = next((j for j, x in enumerate(following) if x[0] == "section"), len(following))
            if not any(x[0] == "para" for x in following[:nxt_sec]):
                continue
        cleaned.append(tok)
    return cleaned


def _cap(text: str, maxc: int) -> list[str]:
    if len(text) <= maxc:
        return [text]
    out: list[str] = []
    for p in split_at_sentences(text, target=maxc, overlap=0):
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def build_document(entry: dict) -> Document:
    path = os.path.join(_SRC, entry["file"])
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    toks = _tokens(soup)
    slug, title, author = entry["slug"], entry["title"], entry["author"]
    did = document_id("encyclicals", slug)
    has_sec = any(k == "section" for k, _, _ in toks)
    meta = {"pope": author, "url": entry["url"]}
    passages: list[Passage] = []
    pos = 0
    seen_anchors: set[str] = set()

    def emit(content: str, ref: str, base_anchor: str, ckey: str, clabel: str,
             unit: str | None) -> None:
        nonlocal pos
        content = clean_text(strip_footnote_markers(strip_boilerplate(content)))
        if not content:
            return
        pieces = _cap(content, settings.MAX_PASSAGE_CHARS)
        for j, piece in enumerate(pieces):
            anc = base_anchor + (f"/p{j + 1}" if len(pieces) > 1 else "")
            k = 1
            while anc in seen_anchors:
                k += 1
                anc = f"{base_anchor}-{k}" if len(pieces) == 1 else f"{base_anchor}/p{j + 1}-{k}"
            seen_anchors.add(anc)
            passages.append(Passage(content=piece, reference=ref, anchor=anc,
                                    chapter_key=ckey, chapter_label=clabel,
                                    position=pos, unit_label=unit, metadata=meta))
            pos += 1

    # The preamble is the greeting/salutation before §1. Take preamble tokens only
    # up to the first ALL-CAPS line: a shouting line is the title masthead or an
    # embedded table-of-contents header (modern vatican.va docs), never greeting
    # prose — so it marks the end of any real preamble. Masthead-first documents
    # (Caritas, Laudato, Magnifica Humanitas) yield no preamble passage.
    pre_parts: list[str] = []
    for k, _, t in toks:
        if k != "preamble":
            continue
        if _is_shouting(t):
            break
        pre_parts.append(t)
    pre = _strip_leading_caps("\n\n".join(pre_parts).strip()).strip()
    if pre:
        emit(pre, f"{title} — Preamble", make_anchor(slug, "preamble"),
             make_anchor(slug, "preamble"), "Preamble", None)

    # For bucket-labeled docs (no section headers), label each bucket by the
    # ACTUAL paragraph range present, not the fixed bucket width — so a final
    # partial bucket reads e.g. "Paragraphs 61–64", not "Paragraphs 61–80".
    bucket_range: dict[int, tuple[int, int]] = {}
    if not has_sec:
        for k, n, _ in toks:
            if k != "para":
                continue
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range.get(b, (n, n))
            bucket_range[b] = (min(lo, n), max(hi, n))

    sec_ord = 0
    cur_key = cur_label = None
    for k, n, t in toks:
        if k == "preamble":
            continue
        if k == "section":
            sec_ord += 1
            cur_key = make_anchor(slug, f"sec-{sec_ord}")
            cur_label = title_case_shouting(clean_text(t))
            continue
        # k == "para"
        if has_sec:
            if cur_key is None:
                cur_key, cur_label = make_anchor(slug, "sec-0"), "Introduction"
            ckey, clabel = cur_key, cur_label
        else:
            b = (n - 1) // _BUCKET
            lo, hi = bucket_range[b]
            clabel = f"Paragraphs {lo}–{hi}" if lo != hi else f"Paragraph {lo}"
            ckey = make_anchor(slug, f"bucket-{b}")
        emit(t, f"{title}, §{n}", make_anchor(slug, n), ckey, clabel, f"§{n}")

    return Document(id=did, collection="encyclicals", title=title, author=author,
                    year=entry["year"], metadata={"url": entry["url"], "pope": author},
                    passages=passages)


def build_documents() -> list[Document]:
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return [build_document(e) for e in manifest]
