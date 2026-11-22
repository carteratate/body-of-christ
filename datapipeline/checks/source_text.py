"""Read vendored source files into units of text, without the adapters.

Each extractor returns `list[SourceUnit]` for one file. A unit is one block of the
source (a paragraph, a verse, a numbered Catechism paragraph, a note) with the region it
belongs to:

- "body": the work's own text, which should reach a passage;
- "note": footnotes and endnotes;
- "toc": tables of contents and navigation links;
- "heading": headings and titles;
- "apparatus": page furniture that is none of the above (title pages, indexes, language
  bars, site footers, the editor's introduction to a Bible book);
- "withheld": the work's own text that rule E keeps out of the corpus because it has no
  English (1.5b): Latin, and the canons the removal registry retires for it; in ThML, a
  paragraph mostly in another language, which a translator left untranslated (3.3);
- "excluded": the work's own text that rules A to C take out of the corpus (3.1): a work
  the removal registry retires whole, and a chapter every passage of which it retires.

Nothing here imports from `ingest/`, so a parser defect cannot hide itself by being
shared. Where a sentence of body text is interrupted by a note, the note's position is
marked with `SEGMENT_BREAK`, so the text either side is measured separately whether or
not an adapter leaves the note inline.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from glob import glob
from typing import NamedTuple

import defusedxml.ElementTree as ET
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from checks.language import latin_runs, mostly_foreign
from ingest.editorial import PLAIN_CALLERS
from ingest.editorial_keep import kept_quotes, quoted_text

SOURCES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources")

# Separates two stretches of text that must not be read as one sentence.
SEGMENT_BREAK = "\u2029"

REGIONS = ("body", "note", "toc", "heading", "apparatus", "withheld", "excluded")


PAPAL_COLLECTIONS = ("encyclicals", "apostolic-exhortations", "papal-documents")
# The file the Catechism of the Catholic Church is measured on (#279).
CCC_FILE = "us-edition/ccc-us.json"


class SourceUnit(NamedTuple):
    source_file: str      # path relative to sources/<collection>/
    unit_id: str | None   # div id, "<BOOK>/<chapter>/<verse>", paragraph or canon number
    text: str
    region: str           # one of REGIONS


# --------------------------------------------------------------------------- ThML

_THML_TOC_TITLES = frozenset({"contents", "table of contents"})
_THML_APPARATUS = re.compile(
    r"^(?:title pages?|indexes|indices|index|subject index(?:es)?|index of .*|errata)\.?$")
_THML_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_THML_DIVS = frozenset(f"div{n}" for n in range(1, 7))


def _thml_div_region(title: str, inherited: str) -> str:
    if inherited != "body":
        return inherited
    t = " ".join((title or "").split()).lower()
    if t in _THML_TOC_TITLES:
        return "toc"
    if _THML_APPARATUS.match(t):
        return "apparatus"
    return "body"


def _thml_text(el, skip_notes: bool) -> str:
    """Text of an element. With skip_notes, each <note> becomes a SEGMENT_BREAK.
    Entities the source escaped twice ("&amp;gt;") are read as the character."""
    return html.unescape(_thml_raw(el, skip_notes))


def _thml_raw(el, skip_notes: bool) -> str:
    parts = [el.text or ""]
    for child in el:
        if skip_notes and child.tag == "note":
            parts.append(SEGMENT_BREAK)
        elif child.tag == "br":
            parts.append(" ")
        elif child.tag == "l":
            # A line of verse: lines sit side by side in the source, often without
            # whitespace between them.
            parts.append(f" {_thml_raw(child, skip_notes)} ")
        else:
            parts.append(_thml_raw(child, skip_notes))
        parts.append(child.tail or "")
    return "".join(parts)


def _read_thml(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


EDITORIAL_DIVS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "editorial_divs.json")


def editorial_divs(source_file: str, path: str = EDITORIAL_DIVS_PATH) -> set[str]:
    """Div ids of a ThML file that hold an editor's or translator's text (introductory
    notices, elucidations, editors' prefaces), reviewed by Carter on 5 Oct 2026. Rule G
    keeps them out of the corpus, so they are "apparatus", not body."""
    with open(path, encoding="utf-8") as f:
        return {r["div"] for r in json.load(f)
                if r["file"] == source_file and not r.get("own_text")}


def editorial_own_text(source_file: str, path: str = EDITORIAL_DIVS_PATH) -> set[str]:
    """Div ids of a ThML file whose own paragraphs are an editor's, though the divs inside
    them are the author's (`"own_text": true`): the NPNF Augustine volumes' book divs,
    which print only title lines and the editor's summary, and the treatises' title pages
    (1.8b). Those paragraphs are "apparatus"."""
    with open(path, encoding="utf-8") as f:
        return {r["div"] for r in json.load(f)
                if r["file"] == source_file and r.get("own_text")}


REMOVALS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "registry", "removals.json")
_removed_paragraphs: dict[str, frozenset[str]] = {}


def removed_paragraphs(path: str = REMOVALS_PATH) -> frozenset[str]:
    """The sha1s of whole paragraphs the removal registry's `span` entries take out of a
    chapter that stays, as `ingest.editorial.span_sha1` keys them: rule G's editor lines
    (1.8a: a translator's credit, an "Argument", a letter's title line), the longer
    Ignatian recension (rule B) and the commentators in Peter's canons (1.8c). The
    registry explains them, so they are apparatus, not body the build lost."""
    if path not in _removed_paragraphs:
        with open(path, encoding="utf-8") as f:
            _removed_paragraphs[path] = frozenset(
                e["span"]["sha1"] for e in json.load(f)
                if e.get("scope") == "span" and (e.get("span") or {}).get("sha1"))
    return _removed_paragraphs[path]


_withheld_canons: dict[str, frozenset[str]] = {}


def withheld_canons(path: str = REMOVALS_PATH) -> frozenset[str]:
    """The canon numbers whose passage the removal registry retires because their current
    text has no English (rule E, 1.5b)."""
    if path not in _withheld_canons:
        with open(path, encoding="utf-8") as f:
            _withheld_canons[path] = frozenset(
                e["anchor"].split("/")[1] for e in json.load(f)
                if e.get("collection") == "canon-law" and e.get("scope") == "passage"
                and e.get("reason") == "translation-in-preparation"
                and re.fullmatch(r"can/\d+", e.get("anchor") or "")
                and not e.get("closed_by"))
    return _withheld_canons[path]


_withheld_chapters: dict[str, frozenset[tuple[str, str]]] = {}


def withheld_chapters(path: str = REMOVALS_PATH) -> frozenset[tuple[str, str]]:
    """(ThML file, div id) of each chapter every passage of which the removal registry
    retires because no English exists (rule E, 3.3): Stromata III ch. 3, Divine
    Institutes VI.23, On the Workmanship of God 12. A chapter that keeps a passage is
    not listed; its Latin paragraphs are `mostly_foreign`. Read from the registry files
    beside `path`: a passage row's anchor is `<div>` or `<div>/<piece>`, and its work's
    `source_key` names the file."""
    if path not in _withheld_chapters:
        folder = os.path.dirname(path)
        with open(path, encoding="utf-8") as f:
            retired = {e["passage_id"] for e in json.load(f)
                       if e.get("collection") == "church-fathers"
                       and e.get("scope") == "passage" and not e.get("closed_by")
                       and e.get("reason") == "translation-in-preparation"}
        with open(os.path.join(folder, "works.json"), encoding="utf-8") as f:
            files = {w["document_id"]: w["source_key"].split("/", 1)[1].split("#")[0]
                     for w in json.load(f) if w["collection"] == "church-fathers"}
        rows_path = os.path.join(folder, "passages", "church-fathers.jsonl")
        chapters: dict[tuple[str, str], bool] = {}     # → every row retired for rule E
        if os.path.exists(rows_path):
            with open(rows_path, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    if r["status"] == "redirected" or r["document_id"] not in files:
                        continue
                    key = (files[r["document_id"]], r["anchor"].split("/")[0])
                    chapters[key] = chapters.get(key, True) and r["passage_id"] in retired
        _withheld_chapters[path] = frozenset(k for k, v in chapters.items() if v)
    return _withheld_chapters[path]


_EXCLUDING_REASONS = ("rule-a", "rule-b", "rule-c")
_excluded_divs: dict[str, frozenset[tuple[str, str]]] = {}


def excluded_divs(path: str = REMOVALS_PATH) -> frozenset[tuple[str, str]]:
    """(ThML file, div id) of each unit rules A to C take out of the corpus (3.1): the
    work div of a document an open `document` entry retires, and each chapter every
    passage of which open `passage` entries retire (Treatises I and III among Cyprian's,
    Hippolytus's undatable works, Book VIII before its canons). Everything inside one is
    "excluded". Read from the registry files beside `path`, as `withheld_chapters` is."""
    if path not in _excluded_divs:
        folder = os.path.dirname(path)
        with open(path, encoding="utf-8") as f:
            entries = [e for e in json.load(f) if e.get("collection") == "church-fathers"
                       and e.get("reason") in _EXCLUDING_REASONS and not e.get("closed_by")]
        with open(os.path.join(folder, "works.json"), encoding="utf-8") as f:
            keys = {w["document_id"]: w["source_key"].split("/", 1)[1]
                    for w in json.load(f) if w["collection"] == "church-fathers"}
        out = {tuple(keys[e["document_id"]].split("#", 1)) for e in entries
               if e["scope"] == "document" and "#" in keys[e["document_id"]]}
        retired = {e["passage_id"] for e in entries if e["scope"] == "passage"}
        chapters: dict[tuple[str, str], bool] = {}     # → every row retired by 3.1
        rows_path = os.path.join(folder, "passages", "church-fathers.jsonl")
        if os.path.exists(rows_path):
            with open(rows_path, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    if r["status"] == "redirected" or r["document_id"] not in keys:
                        continue
                    key = (keys[r["document_id"]].split("#")[0],
                           r["anchor"].split("#")[0].split("/")[0])
                    chapters[key] = chapters.get(key, True) and r["passage_id"] in retired
        _excluded_divs[path] = frozenset(out | {k for k, v in chapters.items() if v})
    return _excluded_divs[path]


# Volumes only some works of which are built, by file: the work divs measured. Text outside
# them is not part of any built work (NPNF2-04's other works wait for 5.6a), so it is not
# read. The adapter names the same divs (`ingest.church_fathers.VOLUME_WORKS`).
VOLUME_SCOPE = {"npnf204.xml": ("vii.ii",)}


def _in_scope(div_id: str | None, scope: tuple[str, ...] | None) -> bool:
    return scope is None or (div_id is not None
                             and any(div_id == d or div_id.startswith(d + ".") for d in scope))


def _leads_to_scope(div_id: str | None, scope: tuple[str, ...]) -> bool:
    return div_id is not None and any(d.startswith(div_id + ".") for d in scope)


def _paragraph_sha1(text: str) -> str:
    return hashlib.sha1(" ".join(text.replace(SEGMENT_BREAK, " ").split())
                        .encode("utf-8")).hexdigest()


def thml_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """ThML (CCEL XML). Body is <p> and <verse> text inside div1 to div6 (a <verse>
    holds a poem or a quoted hymn as <l> lines); <note> is "note"; <scripCom> and <pb>
    carry no text and are ignored. unit_id is the nearest ancestor div's id. Divs
    listed in editorial_divs.json, and everything inside them, are "apparatus", and so
    is a paragraph a removal registry span entry records (`removed_paragraphs`), and the
    own paragraphs of a div `editorial_own_text` lists. A body paragraph mostly in another
    language (`checks.language.mostly_foreign`), or in a chapter the removal registry
    retires whole for rule E (`withheld_chapters`), is "withheld" (3.3); a body paragraph in
    a unit rules A to C take out (`excluded_divs`) is "excluded" (3.1). A quotation of the author that
    `ingest.editorial_keep` keeps from an editorial div is body under its passage's
    chapter key (`<div>/retractations`), and a footnote caller printed as a plain digit
    (`ingest.editorial.PLAIN_CALLERS`) is read without it, as the adapter reads it. Of a
    volume `VOLUME_SCOPE` lists, only the listed work divs are read."""
    source_file = source_file or os.path.basename(path)
    root = _read_thml(path)
    scope = VOLUME_SCOPE.get(source_file)
    editorial = editorial_divs(source_file)
    own_text = editorial_own_text(source_file)
    removed = removed_paragraphs()
    withheld = withheld_chapters()
    excluded = {d for f, d in excluded_divs() if f == source_file}
    quotes = {}
    for q in kept_quotes(source_file):
        quotes.setdefault(q.first, []).append(q)
        quotes.setdefault(q.last, []).append(q)
    units: list[SourceUnit] = []

    def walk(el, div_id: str | None, region: str, in_div: bool) -> None:
        for child in el:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag in _THML_DIVS:
                if not (_in_scope(child.get("id"), scope)
                        or _leads_to_scope(child.get("id"), scope)):
                    continue
                child_region = _thml_div_region(child.get("title") or "", region)
                if child.get("id") in editorial:
                    child_region = "apparatus"
                elif child.get("id") in excluded and child_region == "body":
                    child_region = "excluded"
                walk(child, child.get("id") or div_id, child_region, True)
            elif in_div and not _in_scope(div_id, scope):
                continue
            elif tag == "note":
                if in_div:
                    units.append(SourceUnit(source_file, div_id,
                                            _thml_text(child, skip_notes=False), "note"))
            elif tag in ("p", "verse"):
                if in_div:
                    text = _thml_text(child, skip_notes=True)
                    for printed, without in PLAIN_CALLERS.get((source_file, child.get("id")),
                                                              ()):
                        text = text.replace(printed, without)
                    own = "apparatus" if region == "body" and (
                        _paragraph_sha1(text) in removed or div_id in own_text) else region
                    if own == "body" and (mostly_foreign(text)
                                          or (source_file, div_id) in withheld):
                        own = "withheld"
                    for q in quotes.get(child.get("id"), [])[:1]:
                        a, b = quoted_text(text, q, child.get("id"))
                        units.append(SourceUnit(source_file, q.anchor, text[a:b], "body"))
                        text = text[:a] + SEGMENT_BREAK + text[b:]
                    units.append(SourceUnit(source_file, div_id, text, own))
                    # A note inside the paragraph is its own unit.
                    for note in child.iter("note"):
                        units.append(SourceUnit(source_file, div_id,
                                                _thml_text(note, skip_notes=False), "note"))
            elif tag in _THML_HEADINGS:
                if in_div:
                    units.append(SourceUnit(source_file, div_id,
                                            _thml_text(child, skip_notes=True), "heading"))
            else:
                walk(child, div_id, region, in_div)

    walk(root, None, "body", False)
    return [u for u in units if u.text.strip()]


# A passage may hold no run this long of a ThML file's CCEL `<description>` (3.1).
DESCRIPTION_RUN = 40
_QUOTED = re.compile(r'["\u201c][^"\u201c\u201d]*["\u201d]')


def thml_description(path: str) -> str:
    """The CCEL staff blurb in a ThML file's header (`ThML.head`'s `<description>`), with
    its whitespace collapsed; empty when it has none. It is CCEL's text, not the work's
    (Decision log "CCEL staff descriptions"), and no adapter reads the header."""
    root = _read_thml(path)
    head = next((el for el in root if isinstance(el.tag, str) and el.tag == "ThML.head"),
                None)
    found = head.find(".//description") if head is not None else None
    return " ".join(_thml_text(found, skip_notes=False).split()) if found is not None else ""


def description_leaks(descriptions: dict[str, str], passages) -> list[tuple[str, str]]:
    """(file, passage anchor) for each passage that holds `DESCRIPTION_RUN` or more
    consecutive characters of a file's description, whitespace collapsed. Only CCEL's own
    words count: a stretch the description quotes (Anselm's "a being than which none
    greater can be conceived") is the author's and may be in a passage, and no run crosses
    one. `descriptions` maps a file to its `thml_description`; `passages` yields objects
    with `anchor` and `content`."""
    n = DESCRIPTION_RUN
    windows = {}
    for name, text in descriptions.items():
        for part in _QUOTED.split(text):
            for i in range(len(part) - n + 1):
                windows.setdefault(part[i:i + n], name)
    out = []
    for p in passages:
        content = " ".join(p.content.split())
        hit = next((windows[content[i:i + n]] for i in range(len(content) - n + 1)
                    if content[i:i + n] in windows), None)
        if hit is not None:
            out.append((hit, p.anchor))
    return out


def thml_divs(path: str) -> list[tuple[str, int, str, str]]:
    """Every div1 to div6 of a ThML file as (id, level, title, region), in order."""
    root = _read_thml(path)
    out: list[tuple[str, int, str, str]] = []

    def walk(el, region: str) -> None:
        for child in el:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag in _THML_DIVS:
                r = _thml_div_region(child.get("title") or "", region)
                out.append((child.get("id") or "", int(tag[3:]),
                            " ".join((child.get("title") or "").split()), r))
                walk(child, r)
            else:
                walk(child, region)

    walk(root, "body")
    return out


# --------------------------------------------------------------------------- Summa

# The Summa's text carries the editor's bracketed notes ("[*Or, Fruition]") and a
# shorthand for references ("FS, Q[24], A[3]"). The corpus drops the notes as editorial
# text and prints the references in words, so the extractor reads the text the same way:
# a note is a "note" unit, and a reference is spelled out as a reader sees it. Without
# this, every sentence holding either one reads as lost (4 points of the Summa's body).
SUMMA_NOTE = re.compile(r"\s*\[\*(?:[^\[\]]|\[[^\]]*\])*\]")
_SUMMA_PARTS = {"FP": "First Part", "FS": "First Part of the Second Part",
                "SS": "Second Part of the Second Part", "SP": "Second Part",
                "TP": "Third Part", "XP": "Supplement"}
_SUMMA_SHORTHAND = (
    (re.compile(r"QQ\[(\d+)\]\s*-\s*\[?(\d+)\]?"), r"Qq. \1–\2"),
    (re.compile(r"AA\[(\d+)\]\s*,\s*(\d+)"), r"Aa. \1, \2"),
    (re.compile(r"AA\[(\d+)\]"), r"Aa. \1"),
    (re.compile(r"\bQ\[(\d+)\]"), r"Q. \1"),
    (re.compile(r"\bA\[(\d+)\]"), r"A. \1"),
    (re.compile(r"\bOBJ\[(\d+)\]"), r"Objection \1"),
)
_SUMMA_PART = re.compile(r"\b(FP|FS|SS|SP|TP|XP)\b")


def summa_reading_text(text: str) -> str:
    """Summa text as the reader sees it: editor's notes removed, references in words."""
    text = SUMMA_NOTE.sub("", text)
    for pattern, replacement in _SUMMA_SHORTHAND:
        text = pattern.sub(replacement, text)
    return _SUMMA_PART.sub(lambda m: _SUMMA_PARTS[m.group(1)], text)


def summa_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """The Summa's ThML read as thml_units, with each body or heading unit's editor's
    notes moved into "note" units and its reference shorthand spelled out."""
    units: list[SourceUnit] = []
    for u in thml_units(path, source_file):
        if u.region in ("body", "heading"):
            for m in SUMMA_NOTE.finditer(u.text):
                units.append(SourceUnit(u.source_file, u.unit_id, m.group(0).strip(), "note"))
            u = u._replace(text=summa_reading_text(u.text))
        units.append(u)
    return [u for u in units if u.text.strip()]


# --------------------------------------------------------------------------- HTML

# Elements that start a new block of text. Inline elements (a, b, i, span, font, …)
# join the block they sit in.
_HTML_BLOCKS = frozenset({
    "p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "dd", "dt",
    "blockquote", "center", "tr", "table", "ul", "ol", "dl", "body", "pre",
})
_HTML_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_HTML_DROP = ("script", "style", "noscript", "nav", "header", "footer", "form", "head")

# A notes heading, or a horizontal rule followed by numbered notes, starts the notes.
# papalencyclicals.net heads its notes "REFERENCES:".
_NOTES_HEADING = re.compile(r"^(?:end|foot)?notes?\b|^references:?$", re.IGNORECASE)
# A papal paragraph number that lost its point ("14 If we read"), read only when it is the
# next number.
_UNDOTTED_NUMBER = re.compile(r"^\s*(\d{1,3})\s+([A-Z“\"].*)", re.DOTALL)
# How many blocks after a horizontal rule note 1 may sit.
_NOTE_REACH = 3
_NOTE_START = re.compile(r"^\s*(?:\[\s*1\s*\]|\(\s*1\s*\)|1\s*\.|1\s)")
_BRACKET_NOTE_START = re.compile(r"^\s*(?:\[\s*1\s*\]|\(\s*1\s*\))")
_SITE_CHROME = re.compile(
    r"^copyright\s*©|^©\s*copyright|automatically notified|more information about this site"
    r"|fan of our facebook|^search tips$|^sitemap$|return to (?:the )?home|^last updated\b",
    re.IGNORECASE)
# "12. Text", and "131.Later" where the source left out the space (but not "1.5").
_PARA_NUMBER = re.compile(r"^\s*(\d{1,4})\s*\.(?=\s|$|[^\d\s])")
# Canon law pages' notes on amendments, and a canon's reference to the amending act (1.5a).
_CANON_NOTE = re.compile(
    r"^(?:\(\s*:\s*indicates that|\(\s*:\s*Indica che|\[\s*(?:Earlier|Original) version"
    r"|\(\s*(?:earlier version|precedente versione)\s*\)|Cf\.?:?\s|For Can\.|For the new text"
    r"|Can\.?\s*\d+\s*(?:§\s*\d+\.?)?\s*:\s*(?:Cf|Apostolic|Rescript)|\[\s*(?:Italian|Latin)\s*\]"
    r"|Rescriptum ex Audientia)", re.IGNORECASE)
_CANON_ACT_REF = re.compile(r"\s*(?:\[[^\[\]]*\b(?:19|20)\d\d\s*\)?\s*\]"
                            r"|\(\s*(?:Cf\.|Apostolic Letter|Rescript)[^()]*\b(?:19|20)\d\d\b[^()]*\))")
_CANON_SPELLING = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "normalize", "canon_spelling.json")


def _canon_respell(text: str) -> str:
    """The reviewed corrections of the source's lost ff and ffi ligatures, which the
    parser applies to the canons that print them (C-16)."""
    with open(_CANON_SPELLING, encoding="utf-8") as f:
        rows = json.load(f)["corrections"]
    for r in rows:
        text = re.sub(rf"\b{re.escape(r['broken'])}\b", r["corrected"], text)
    return text


_CANON_NUMBER = re.compile(r"^\W*n?\s*Can\.\s*(\d+)")
_LEADING_NUMBER = re.compile(r"^\s*(?:\d{1,4}\s*\.|\W*n?\s*Can\.\s*\d+\.?)\s*")


def _is_shouting(text: str) -> bool:
    """A short all-capitals block: a heading set as a paragraph."""
    letters = [c for c in text if c.isalpha()]
    return (len(text) < 200 and len(letters) >= 4
            and sum(c.isupper() for c in letters) / len(letters) >= 0.8)


def _html_main(soup: BeautifulSoup) -> Tag:
    """The element holding the document: papalencyclicals.net's entry-content, the
    current vatican.va layout's `documento`, the old vatican.va layout's largest table
    cell, else the body."""
    for selector in ("div.entry-content", "div.documento"):
        found = soup.select(selector)
        if found:
            return max(found, key=lambda e: len(e.get_text(" ", strip=True)))
    cells = soup.find_all("td")
    if cells:
        # The cell holding the most text; with nested layout tables that is the outer
        # cell, which still holds only the document and its language bar.
        return max(cells, key=lambda e: len(e.get_text(" ", strip=True)))
    return soup.body or soup


class _Block(NamedTuple):
    tag: str
    text: str
    all_link: bool   # every letter and digit sits inside an <a href>
    list_number: int | None = None   # the number an <ol> item renders with


def _list_number(el: Tag) -> int | None:
    """An `<ol>` item's rendered number, honouring the list's `start`."""
    parent = el.parent
    if el.name != "li" or parent is None or parent.name != "ol":
        return None
    earlier = sum(1 for sib in el.find_previous_siblings("li"))
    return int(parent.get("start") or 1) + earlier


def _html_blocks(main: Tag) -> list[_Block]:
    blocks: list[_Block] = []

    def visit(el: Tag, block_tag: str) -> None:
        buf: list[str] = []
        linked = [0, 0]   # characters inside links, all characters

        def flush() -> None:
            text = "".join(buf)
            if text.strip():
                blocks.append(_Block(block_tag, text, linked[0] == linked[1],
                                     _list_number(el)))
            buf.clear()
            linked[0] = linked[1] = 0

        def inline(node, in_link: bool) -> None:
            for child in node.children:
                if isinstance(child, Comment):
                    continue
                if isinstance(child, NavigableString):
                    s = str(child)
                    buf.append(s)
                    n = sum(c.isalnum() for c in s)   # separators such as " - " are not text
                    linked[1] += n
                    if in_link:
                        linked[0] += n
                    continue
                if not isinstance(child, Tag):
                    continue
                if child.name in _HTML_BLOCKS:
                    flush()
                    visit(child, child.name)
                    continue
                if child.name == "br":
                    buf.append(" ")
                    continue
                if child.name == "hr":
                    flush()
                    blocks.append(_Block("hr", "", False))
                    continue
                inline(child, in_link or (child.name == "a" and child.get("href") is not None))

        inline(el, False)
        flush()

    visit(main, main.name)
    return blocks


# The footnote callers of the papal collections, whose adapters drop them (C-17): a numeric
# <sup>, an in-page link holding only a number, and "(35)" or a digit glued after a word.
# Written here again, not imported, for the reason in this module's docstring.
_CALLER_OPEN, _CALLER_CLOSE = "\ue000", "\ue001"
_FENCED = re.compile(f"{_CALLER_OPEN}(.*?){_CALLER_CLOSE}")
# The last paragraph of a document whose page runs on past it with the site's own extracts.
_LAST_PARAGRAPH = {"syllabus-of-errors.html": "80"}
# Site text inside a page (C-05): from the match to the end of the body is apparatus.
_SITE_TEXT = {"cum-sancta-mater-ecclesia.html": re.compile(r"Perform bulk operations\b.*$", re.S),
              "exsurge-domine.html": re.compile(r"\{.*$", re.S)}
_NUMBER_ONLY = re.compile(r"^\W*\d{1,3}\*?\W*$")
_TEXT_CALLER = re.compile(r"(?<=[A-Za-z\"”’.,;:!?)])\s?\(\d{1,3}\)"
                          r"|(?<=[a-z\"”’)][.,;:])\d{1,3}(?=\s|$|[A-Z“\"])"
                          r"(?!\s+(?:Cor|Jn|John|Pt|Pet|Peter|Tim|Tm|Thes|Th|Sam|Sm|Kgs|Kg|Kings"
                          r"|Chr|Mac|Macc|Mc|Esd)\b)")
# The Vatican II pages' callers, which the councils parser drops (1.1): "(9)" and the
# starred "(21*)" after a word or a closing mark, "[ 40 ]", and the "[ ]" a linked number
# leaves.
_VAT2_CALLER = re.compile(r"(?<=[A-Za-z\"”’.,;:!?)\]])\s?\(\d{1,3}\*?\)"
                          r"|(?<=\S)\s*\[\s*\d{0,3}\s*\]")
# Sources that print callers as plain numbers after a sentence.
_BARE_CALLER_FILES = ("annus-qui-hunc.html", "mulieris-dignitatem.html")
_CITATION_BEFORE = re.compile(r"\b(?:cf|bk|sess|ch|cap|tit|vol|no|nos|art|can|lib|p|pp|n|dist)\.$",
                              re.IGNORECASE)
_BARE_CALLER = re.compile(r"(?<=[.!?\"”’)…])\s\d{1,3}(?=\s+[A-Z“\"‘]|\s*$)"
                          r"(?!\s+(?:Cor|Jn|John|Pt|Pet|Peter|Tim|Tm|Thes|Th|Sam|Sm|Kgs|Kg|Kings|Chr"
                          r"|Mac|Macc|Mc|Esd)\b)")


def _drop_bare_callers(text: str) -> str:
    """The bare numbers of `_BARE_CALLER_FILES`, a citation's number apart ("sess. 24 On")."""
    def keep_citation(m: re.Match) -> str:
        cited = _CITATION_BEFORE.search(text, max(0, m.start() - 8), m.start())
        return m.group(0) if cited else ""
    return _BARE_CALLER.sub(keep_citation, text)


def _mark_callers(main: Tag) -> None:
    """Fence each marked caller, so the notes are found on the unchanged text and only
    body units lose it."""
    for tag in main.find_all(["sup", "a"]):
        if tag.decomposed or tag.find_parent("sup") is not None:
            continue
        text = tag.get_text(strip=True)
        if (tag.name == "sup" or (tag.get("href") or "").startswith("#")) \
                and _NUMBER_ONLY.match(text or "x"):
            tag.string = f"{_CALLER_OPEN}{text}{_CALLER_CLOSE}"


def html_units(path: str, source_file: str | None = None,
               papal: bool = False, canon_law: bool = False,
               vatican2: bool = False) -> list[SourceUnit]:
    """vatican.va and papalencyclicals.net HTML. Body is the visible text of the main
    content element, one unit per block (<p>, <li>, <div>, table cell, …). Text after
    the first notes marker is "note": a notes heading ("Notes", "NOTES", "ENDNOTES",
    "REFERENCES:"), a horizontal rule followed by note 1 when note 1 is bracketed or the
    body has already used paragraph number 1, or a block that opens with "[1]". Headings
    are "heading"; blocks that are entirely links (language bars, tables of contents) are
    "toc"; site footers are "apparatus". unit_id is the leading paragraph or canon number;
    in a body that prints no number it is the number an `<ol>` item renders with.

    With `papal`, for the three papal collections: note 1 may sit up to three blocks after
    the rule, and any paragraph number counts (many print no "1."); body text loses its
    footnote callers, as the parser's does; a number that lost its point is read when it is
    the next one.

    With `canon_law`, the amendment marker (a brown "n" beside an amended canon) is not
    text and is dropped, the page's notes on amendments (the marker legend, "Cf." lines,
    version headings) are notes, and a canon's bracketed reference to the amending act
    is not its text, as the parser reads them (1.5a). Body text rule E keeps out is
    "withheld" (1.5b): a block holding a Latin run, and every block of a canon the removal
    registry retires for having no English, from its "Can. N" block to the next canon or
    heading, its superseded texts included.

    With `vatican2`, for the Vatican II pages of the councils collection, body text loses
    its footnote callers, as the parser's does (1.1)."""
    source_file = source_file or os.path.basename(path)
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    for tag in soup.find_all(_HTML_DROP):
        tag.decompose()
    if canon_law:
        for tag in soup.find_all("font"):
            if (tag.get("color") or "").lower() == "#663300" and tag.get_text(strip=True) == "n":
                tag.replace_with(" ")
    main = _html_main(soup)
    if papal or vatican2:
        _mark_callers(main)
    blocks = _html_blocks(main)

    units: list[SourceUnit] = []
    rendered: list[int | None] = []
    withheld = withheld_canons() if canon_law else frozenset()
    canon: str | None = None
    in_notes = False
    seen_number = False
    last_number = 0
    for i, block in enumerate(blocks):
        if block.tag == "hr":
            if in_notes:
                continue
            following = [b for b in blocks[i + 1:] if b.tag != "hr" and b.text.strip()]
            for nxt in following[:_NOTE_REACH if papal else 1]:
                lead = " ".join(_FENCED.sub(r"\1", nxt.text).split())
                if _BRACKET_NOTE_START.match(lead) or (seen_number and _NOTE_START.match(lead)):
                    in_notes = True
            continue
        raw = block.text
        block = block._replace(text=_FENCED.sub(r"\1", raw))
        text = " ".join(block.text.split())
        if not in_notes and units and _BRACKET_NOTE_START.match(text) and text.startswith("["):
            in_notes = True     # "[1] …" with its rule outside the main element
        if not in_notes and len(text) < 40 and _NOTES_HEADING.match(text):
            in_notes = True
            units.append(SourceUnit(source_file, None, block.text, "heading"))
            continue
        number = _PARA_NUMBER.match(text) or _CANON_NUMBER.match(text)
        unit_id = number.group(1) if number else None
        body_text = block.text
        if number:
            # The number is the unit's identity, not its text: adapters drop it.
            body_text = _LEADING_NUMBER.sub("", block.text, count=1)
            if unit_id.isdigit():
                last_number = int(unit_id)
        elif papal and not in_notes:
            undotted = _UNDOTTED_NUMBER.match(block.text)
            if undotted and int(undotted.group(1)) == last_number + 1:
                unit_id, body_text = undotted.group(1), undotted.group(2)
                last_number += 1
        if in_notes:
            region = "note"
        elif _SITE_CHROME.search(text):
            region = "apparatus"
        elif block.all_link:
            region = "toc"
        elif block.tag in _HTML_HEADINGS or (not number and _is_shouting(text)):
            region = "heading"
        else:
            region = "body"
            if _PARA_NUMBER.match(text) and (papal or unit_id == "1"):
                seen_number = True
        if in_notes and _SITE_CHROME.search(text):
            region = "apparatus"
        if canon_law and region == "heading":
            canon = None
        if canon_law and region == "body":
            if _CANON_NOTE.match(text):
                region = "note"
            else:
                if number and _CANON_NUMBER.match(text):
                    canon = unit_id
                body_text = _canon_respell(_CANON_ACT_REF.sub("", body_text))
                if canon in withheld or latin_runs(body_text):
                    region = "withheld"
        if vatican2 and region == "body":
            kept = _LEADING_NUMBER.sub("", raw, count=1) if number else raw
            body_text = _VAT2_CALLER.sub("", _FENCED.sub("", kept))
        if papal and region == "body":
            kept = _LEADING_NUMBER.sub("", raw, count=1) if number else raw
            if unit_id and not number and (m := _UNDOTTED_NUMBER.match(raw)):
                kept = m.group(2)
            body_text = _TEXT_CALLER.sub("", _FENCED.sub("", kept))
            if source_file in _BARE_CALLER_FILES:
                body_text = _drop_bare_callers(body_text)
        units.append(SourceUnit(source_file, unit_id,
                                body_text if region == "body" else block.text, region))
        rendered.append(block.list_number if region == "body" else None)
    if papal and not any(u.unit_id for u in units if u.region == "body"):
        units = [u if n is None else u._replace(unit_id=str(n))
                 for u, n in zip(units, rendered)]
    return _site_text_to_apparatus(units, source_file)


def _site_text_to_apparatus(units: list[SourceUnit], source_file: str) -> list[SourceUnit]:
    """The units of a page's site text, per `_LAST_PARAGRAPH` and `_SITE_TEXT`."""
    last, site = _LAST_PARAGRAPH.get(source_file), _SITE_TEXT.get(source_file)
    end = None
    for i, u in enumerate(units):
        if u.region != "body":
            continue
        if last is not None and u.unit_id == last:
            end = i
        elif site is not None and site.search(u.text):
            units = units[:i] + [u._replace(text=site.sub("", u.text))] + units[i + 1:]
            end = i
        if end is not None:
            break
    if end is None:
        return units
    return units[:end + 1] + [u._replace(region="apparatus") if u.region == "body" else u
                              for u in units[end + 1:]]


# --------------------------------------------------------------------------- USFM

_USFM_NOTE = re.compile(r"\\(f|fe|x)\s.*?\\\1\*", re.DOTALL)
_USFM_WORD = re.compile(r"\\\+?w\s+([^|\\]*?)\s*(?:\|[^\\]*)?\\\+?w\*")
_USFM_MARKER = re.compile(r"\\\+?[a-zA-Z0-9]+\*?")
# Paragraph markers whose text is a heading or the editor's introduction, not verses.
_USFM_HEADINGS = frozenset({"h", "mt", "mt1", "mt2", "mt3", "ms", "ms1", "ms2", "mr", "s",
                            "s1", "s2", "s3", "sr", "r", "sp", "is", "is1", "is2",
                            "cl", "cd"})
# A Psalm title (superscription): Scripture, unnumbered in WEB-C, so body text with the
# unit id "<BOOK>/<chapter>/d" (0.1d; C-11).
_USFM_TITLES = frozenset({"d"})
_USFM_APPARATUS = frozenset({"id", "ide", "toc1", "toc2", "toc3", "ip", "ipr", "im", "imt",
                             "imt1", "imt2", "io1", "io2", "iot", "rem", "sts"})
_USFM_BREAKS = frozenset({"p", "m", "mi", "nb", "pc", "pi", "pi1", "pi2", "q", "q1", "q2",
                          "q3", "qr", "qc", "b", "li", "li1", "li2"})
_USFM_TOKEN = re.compile(
    r"(?m)\\(c|v)\s+(\d+)[a-z]?\s?|^\\("
    + "|".join(sorted(_USFM_HEADINGS | _USFM_TITLES | _USFM_APPARATUS | _USFM_BREAKS,
                      key=len, reverse=True))
    + r")(?![a-z0-9])")


def _usfm_plain(raw: str) -> str:
    text = _USFM_WORD.sub(r"\1", raw)
    text = _USFM_MARKER.sub(" ", text)
    return text


def usfm_book_code(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"^\\id\s+([A-Z0-9]{3})", line)
            if m:
                return m.group(1)
    raise ValueError(f"{path}: no \\id line")


def usfm_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """USFM (Bible). One unit per \\v, unit_id "<BOOK>/<chapter>/<verse>". A Psalm title
    (\\d) is body text with unit_id "<BOOK>/<chapter>/d". Footnotes and
    cross-references (\\f, \\fe, \\x) are "note"; section headings
    (\\s, \\ms, …) are "heading"; the book's identification lines and introduction are
    "apparatus". A verse continues across paragraph and poetry markers until the next
    verse, chapter or heading."""
    source_file = source_file or os.path.basename(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    code = usfm_book_code(path)
    units: list[SourceUnit] = []
    # Notes first, so a verse's text can be read with them removed.
    for m in _USFM_NOTE.finditer(raw):
        units.append(SourceUnit(source_file, None, _usfm_plain(m.group(0)[3:-3]), "note"))
    body = _USFM_NOTE.sub(f" {SEGMENT_BREAK} ", raw)

    chapter = 0
    current: tuple[str | None, str] = (None, "apparatus")
    buf: list[str] = []
    pos = 0

    def flush() -> None:
        text = _usfm_plain("".join(buf))
        if text.strip(f" \t\n{SEGMENT_BREAK}"):
            units.append(SourceUnit(source_file, current[0], text, current[1]))
        buf.clear()

    for m in _USFM_TOKEN.finditer(body):
        buf.append(body[pos:m.start()])
        pos = m.end()
        kind, number, para = m.group(1), m.group(2), m.group(3)
        if kind == "c":
            flush()
            chapter = int(number)
            current = (None, "heading")
        elif kind == "v":
            flush()
            current = (f"{code}/{chapter}/{int(number)}", "body")
        elif para in _USFM_TITLES:
            flush()
            current = (f"{code}/{chapter}/d", "body")
        elif para in _USFM_HEADINGS:
            flush()
            current = (None, "heading")
        elif para in _USFM_APPARATUS:
            flush()
            current = (None, "apparatus")
        elif current[1] == "body":
            # \p, \q1, \m, \b, …: a paragraph or poetry break inside the current verse.
            buf.append(" ")
        else:
            # A paragraph after a heading and before the next verse marker: text with
            # no verse number, measured for coverage but outside any verse.
            flush()
            current = (None, "body" if chapter else "apparatus")
    buf.append(body[pos:])
    flush()
    return units


# --------------------------------------------------------------------------- CCC

def _ccc_heading(para: dict, text: str) -> bool:
    """An unnumbered, unindented short line not ending in ":" or ";" is a heading in
    ccc.json; indented lines are quotations inside the paragraph before them."""
    t = text.strip()
    return ("indent" not in (para.get("attrs") or {}) and len(t) < 120
            and not t.endswith((":", ";", ",")))


def ccc_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """ccc.json (Catechism). One unit per numbered paragraph, unit_id the CCC number.
    Unnumbered paragraphs that follow a numbered one (indented quotations, the
    continuation of a paragraph) belong to it; unnumbered paragraphs before the first
    number of a page are "heading". Footnotes are "note"."""
    source_file = source_file or os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("page_nodes", {})

    def order(key: str) -> int:
        try:
            return int(key.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    units: list[SourceUnit] = []
    for key in sorted(nodes, key=order):
        node = nodes[key]
        number: int | None = None
        parts: list[str] = []

        def flush() -> None:
            if number is not None and parts:
                units.append(SourceUnit(source_file, str(number), "\n".join(parts), "body"))

        for para in node.get("paragraphs", []):
            elements = para.get("elements", [])
            refs = [e.get("ref_number") for e in elements
                    if e.get("type") == "ref-ccc" and e.get("ref_number") is not None]
            text = " ".join(e.get("text", "") for e in elements
                            if e.get("type") == "text" and e.get("text"))
            if refs:
                flush()
                number, parts = refs[0], [text] if text.strip() else []
            elif not text.strip():
                continue
            elif number is None or _ccc_heading(para, text):
                flush()          # keep source order: the paragraph so far, then the heading
                parts = []
                units.append(SourceUnit(source_file, None, text, "heading"))
            else:
                parts.append(text)
        flush()
        for note_number, note in (node.get("footnotes") or {}).items():
            text = " ".join(r.get("text") or "" for r in note.get("refs", []))
            if text.strip():
                units.append(SourceUnit(source_file, f"n{note_number}", text, "note"))
    return units


def ccc_us_units(path: str, source_file: str | None = None) -> list[SourceUnit]:
    """us-edition/ccc-us.json (the Catechism's words since #279). One "body" unit per
    numbered paragraph, unit_id the CCC number; headings and Part, Section, Chapter and
    Article titles are "heading"; each footnote is a "note" unit, which passages hold in
    metadata rather than in their text. The vendored file is read with its reviewed
    corrections (ingest/catechism_corrections.json) applied, as the build reads it."""
    from ingest import catechism_us

    source_file = source_file or os.path.relpath(path, os.path.join(SOURCES, "catechism"))
    data = catechism_us.load_us(path)
    units: list[SourceUnit] = []
    for item in data["items"]:
        if item["kind"] == "paragraph":
            units.append(SourceUnit(source_file, str(item["n"]), item["text"], "body"))
        else:
            units.append(SourceUnit(source_file, None, item["text"], "heading"))
        for note in item.get("footnotes", []):
            units.append(SourceUnit(source_file, f"n{note['n']}", note["text"], "note"))
    return units


# --------------------------------------------------------------------------- files

# Collections whose files are listed in sources/<collection>/manifest.json, by format.
_MANIFEST_HTML = ("apostolic-exhortations", "councils", "encyclicals", "papal-documents")


def collection_files(collection: str, sources: str = SOURCES) -> list[str]:
    """The source files a collection is built from, relative to sources/<collection>/,
    as the vendored manifests list them. Files a manifest leaves out (downloaded but never
    published) are not measured."""
    base = os.path.join(sources, collection)
    if collection in _MANIFEST_HTML or collection in ("medieval", "church-fathers"):
        with open(os.path.join(base, "manifest.json"), encoding="utf-8") as f:
            entries = json.load(f)
        if collection == "councils":
            # A council rebuilt from another source is not built from its Tanner page,
            # which stays vendored; its canon count is its check (1.2e). So is Vatican I's,
            # built from Schaff, whose chapter and canon counts are its check (1.2d), and
            # councils 1 to 7's, built from Percival (1.2c).
            from ingest.councils_percival import COUNCILS
            from ingest.councils_schroeder import WORKS
            entries = [e for e in entries
                       if e["council"] not in WORKS and e["council"] not in COUNCILS
                       and e["council"] != "First Vatican Council"]
        if collection in PAPAL_COLLECTIONS:
            # A document held for permission (1.3d, ADR 0001) is not built from its page,
            # nor is one built from a public-domain printing, whose coverage of the
            # printing `tests/test_papal_printings.py` checks. One published only in part
            # from its page (Exsurge Domine's propositions, R9) is not measured either:
            # its build leaves out the passages held for permission.
            from ingest.papal_printings import printing
            from registry import current, open_removals, removed_document_ids, \
                resolve_document_id
            held = removed_document_ids() | {
                e["document_id"] for e in open_removals(current())
                if e["scope"] == "passage" and e["reason"] == "awaiting-permission"}
            entries = [e for e in entries if resolve_document_id(
                collection, f"{collection}/{e['slug']}", (collection, e["slug"])) not in held
                and printing(collection, e["slug"]) is None]
        return [e["file"] for e in entries]
    if collection == "canon-law":
        with open(os.path.join(base, "pages.json"), encoding="utf-8") as f:
            return [p["file"] for p in json.load(f) if p.get("parsed", True)]
    if collection == "bible":
        return sorted(os.path.relpath(p, base)
                      for p in glob(os.path.join(base, "eng-web-c_usfm", "*.usfm")))
    if collection == "catechism":
        # The words come from the US edition (#279); ccc.json supplies only structure.
        return ["us-edition/ccc-us.json"]
    if collection == "summa":
        return ["summa.xml"]
    raise ValueError(f"unknown collection {collection!r}")


def file_units(collection: str, source_file: str, sources: str = SOURCES) -> list[SourceUnit]:
    path = os.path.join(sources, collection, source_file)
    if collection == "summa":
        return summa_units(path, source_file)
    if source_file.endswith(".xml"):
        return thml_units(path, source_file)
    if source_file.endswith(".html"):
        return html_units(path, source_file, papal=collection in PAPAL_COLLECTIONS,
                          canon_law=collection == "canon-law",
                          vatican2=collection == "councils" and source_file.startswith("vat2-"))
    if source_file.endswith(".usfm"):
        return usfm_units(path, source_file)
    if source_file.endswith("ccc-us.json"):
        return ccc_us_units(path, source_file)
    if source_file.endswith(".json"):
        return ccc_units(path, source_file)
    raise ValueError(f"no extractor for {source_file}")
