"""Structure checks for the 6 Oct 2026 corpus reviews (corpus-cleanup item 0.1d).

Each check reads the built Documents, and where it says so the vendored source, and
returns its failures as check ids → the units behind each, the form `checks.report` and
`checks/known_defects.json` use. Every id is `structure.<check>:<collection>[/<scope>]`,
so `checks.report.check_scope` reads its collection from the id:

- `chapter_contiguous:<collection>`: each chapter key's passages form one run, for the
  collections CONTIGUOUS_COLLECTIONS names (C-13, Sol A-002). Units: the chapter keys.
- `canon_law.chapter_number_agreement:canon-law`: each canon's chapter number agrees with
  the source's table of contents, whose links are joined to the body's named anchors
  (C-13, Sol follow-up B-003). Units: the canon numbers.
- `chapter_sequence:councils/<document_id>`: the numbered chapter labels of a Vatican II
  document run I, II, III… without a gap or a repeat (C-20, Opus-2 B-009). Units:
  "gap:<before>-<after>" and "repeat:<numeral>".
- `bucket_chapters_with_headings:<collection>`: no papal document whose source prints
  section headings between its numbered paragraphs uses a "Paragraphs N–M" chapter (C-08,
  Opus A-003). Units: the document ids.
- `syllabus_body_boundary:encyclicals`: the Syllabus has exactly 80 proposition bodies, and
  no sentence of the source after proposition 80 reaches a passage (C-06, Sol A-004).
  Units: "propositions:<n>" and "after-80".
- `summa.one-disputation-per-article:summa`: within one chapter key, one disputation: no
  second determination run, no objection run restarting at "Objection 1" after the
  determination, and a determination unless R7 confirmed the article as reply-only
  (C-07, Sol A-003). Units: the article div ids.
- `embedded_work_labelled:<collection>/<document_id>`: in a ThML document, a run of
  CHAPTER_RUN_MIN or more chapters numbered with no book prefix, after chapters that carry
  one, belongs to a work or a book (C-15, Opus-2 B-013). Units: the run's first chapter key.

`chapter_size` is report only (C-26, Opus A-017): `large_chapters` lists chapters over
CHAPTER_SIZE_LIMIT characters for the summary, and never fails.
"""
from __future__ import annotations

import itertools
import json
import os
import re
from collections import Counter, defaultdict

from bs4 import BeautifulSoup

from checks.coverage import match_key, measurable, normalize, split_sentences
from checks.source_text import SOURCES, SourceUnit
from ingest.pieces import unit_reference
from model import Document

CHECKS_DIR = os.path.dirname(os.path.abspath(__file__))
DATAPIPELINE = os.path.dirname(CHECKS_DIR)
SUMMA_CORRECTIONS = os.path.join(DATAPIPELINE, "ingest", "summa_corrections.json")

CONTIGUOUS_COLLECTIONS = ("bible", "canon-law", "catechism", "summa")
PAPAL_COLLECTIONS = ("apostolic-exhortations", "encyclicals", "papal-documents")
CHAPTER_SIZE_LIMIT = 50_000
CHAPTER_RUN_MIN = 3
SYLLABUS_PROPOSITIONS = 80

Failures = dict[str, list[str]]

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman(numeral: str) -> int:
    total = 0
    for a, b in itertools.zip_longest(numeral, numeral[1:]):
        v = _ROMAN[a]
        total += -v if b and _ROMAN[b] > v else v
    return total


def _key_runs(document: Document):
    """(chapter_key, passages) for each run of consecutive passages sharing a key."""
    for key, group in itertools.groupby(document.passages, key=lambda p: p.chapter_key):
        yield key, list(group)


# --------------------------------------------------------------------------- contiguity

def chapter_contiguous(collection: str, documents: list[Document]) -> Failures:
    keys = []
    for d in documents:
        runs = Counter(key for key, _ in _key_runs(d))
        keys += sorted(k for k, n in runs.items() if n > 1)
    return {f"structure.chapter_contiguous:{collection}": keys} if keys else {}


# --------------------------------------------------------------------------- canon law

_TOC_LINK = re.compile(r"(cic_lib\d-cann[\d-]+_en\.html)#(.+)$")
_TOC_HEADING = re.compile(r"^(BOOK|PART|SECTION|TITLE|CHAPTER|ARTICLE|ART\.)\s*([IVXLC]+|\d+)?\b",
                          re.IGNORECASE)
_TOC_LEVELS = ("BOOK", "PART", "SECTION", "TITLE", "CHAPTER", "ARTICLE")
_CANON_START = re.compile(r"^\W*n?\s*Can\.\s*(\d+)")
_BUILT_CHAPTER = re.compile(r"\bChapter ([IVXLC]+)\b", re.IGNORECASE)


def _read_html(path: str) -> BeautifulSoup:
    with open(path, encoding="utf-8", errors="replace") as f:
        return BeautifulSoup(f.read(), "html.parser")


def canon_chapters(sources: str = SOURCES) -> dict[int, str]:
    """Each canon's chapter numeral from the source's own structure: the index page's
    links name a body anchor and a heading ("CHAPTER II. …"); each body file is walked in
    order, its named anchors are joined to its index links forward-only (names repeat
    within a file, and one link drops a trailing full stop), a heading resets every lower
    level, and each canon takes the chapter in force where it starts. A canon outside any
    chapter is absent."""
    base = os.path.join(sources, "canon-law")
    toc: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for a in _read_html(os.path.join(base, "cic_index_en.html")).find_all("a"):
        m = _TOC_LINK.search(a.get("href") or "")
        heading = _TOC_HEADING.match(a.get_text(" ", strip=True))
        if m and heading:
            level = heading.group(1).upper().rstrip(".")
            toc[m.group(1)].append((m.group(2).rstrip("."),
                                    "ARTICLE" if level == "ART" else level,
                                    (heading.group(2) or "").upper()))
    with open(os.path.join(base, "pages.json"), encoding="utf-8") as f:
        files = [p["file"] for p in json.load(f) if p.get("parsed", True)]

    chapters: dict[int, str] = {}
    state: dict[str, str] = {}
    for name in files:
        entries, i = toc.get(name, []), 0
        for el in _read_html(os.path.join(base, name)).find_all(["a", "p"]):
            if el.name == "a" and el.get("name"):
                if i < len(entries) and entries[i][0] == el["name"].rstrip("."):
                    _, level, number = entries[i]
                    i += 1
                    rank = _TOC_LEVELS.index(level)
                    state = {k: v for k, v in state.items() if _TOC_LEVELS.index(k) < rank}
                    state[level] = number
            elif el.name == "p":
                m = _CANON_START.match(el.get_text(" ", strip=True).replace("\xa0", " "))
                if m and int(m.group(1)) not in chapters and state.get("CHAPTER"):
                    chapters[int(m.group(1))] = state["CHAPTER"]
    return chapters


def canon_chapter_number_agreement(documents: list[Document],
                                   source_chapters: dict[int, str]) -> Failures:
    """Canons whose built chapter label names a numbered chapter other than the
    source's. A canon with no source chapter, or a label with no number, is not judged."""
    wrong = []
    for d in documents:
        for p in d.passages:
            canon = (p.metadata or {}).get("canon")
            label = (p.metadata or {}).get("chapter") or p.chapter_label
            m = _BUILT_CHAPTER.search(label or "")
            if canon in source_chapters and m and m.group(1).upper() != source_chapters[canon]:
                wrong.append(str(canon))
    return ({"structure.canon_law.chapter_number_agreement:canon-law": wrong}
            if wrong else {})


# --------------------------------------------------------------------------- Vatican II

_NUMBERED_CHAPTER = re.compile(r"^Chapter ([IVXLC]+)\b")


def chapter_sequence(collection: str, documents: list[Document]) -> Failures:
    """Vatican II documents (source key councils/vat2-*): the numbered chapter labels, in
    reading order, run 1, 2, 3… with no gap or repeat."""
    out: Failures = {}
    for d in documents:
        if not (d.metadata or {}).get("source_key", "").startswith("councils/vat2-"):
            continue
        numerals = [m.group(1) for label, _ in itertools.groupby(p.chapter_label for p in d.passages)
                    if (m := _NUMBERED_CHAPTER.match(label))]
        units, seen, previous = [], set(), None
        for n in numerals:
            value = roman(n)
            if value in seen:
                units.append(f"repeat:{n}")
            elif previous is not None and value != previous + 1:
                units.append(f"gap:{_numeral(previous)}-{n}")
            elif previous is None and value != 1:
                units.append(f"gap:start-{n}")
            seen.add(value)
            previous = value
        if units:
            out[f"structure.chapter_sequence:{collection}/{d.id}"] = units
    return out


def _numeral(n: int) -> str:
    out = ""
    for value, letters in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                           (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out, n = out + letters, n - value
    return out


# --------------------------------------------------------------------------- papal buckets

BUCKET_LABEL = re.compile(r"^Paragraphs \d+[–-]\d+$")
_HEADING_END = re.compile(r"[.!?:;,\"”’)\]…]$")
SOURCE_HEADING_MAX = 90


def source_has_headings(units: list[SourceUnit]) -> bool:
    """Whether a papal source prints a section heading between its numbered paragraphs:
    a "heading" unit, or an unnumbered body line under SOURCE_HEADING_MAX characters that
    starts with a capital and has no final punctuation (the line 1.3a will read as a
    heading)."""
    units = [u for u in units if u.region in ("body", "heading")]
    numbered = [i for i, u in enumerate(units) if u.unit_id]
    if not numbered:
        return False
    for u in units[numbered[0] + 1:numbered[-1]]:
        text = u.text.strip()
        if u.region == "heading" or (u.unit_id is None and 0 < len(text) < SOURCE_HEADING_MAX
                                     and text[:1].isupper() and not _HEADING_END.search(text)):
            return True
    return False


def bucket_chapters_with_headings(collection: str, documents_by_file: dict[str, list[Document]],
                                  units_by_file: dict[str, list[SourceUnit]]) -> Failures:
    ids = []
    for f, docs in documents_by_file.items():
        if not source_has_headings(units_by_file.get(f, [])):
            continue
        ids += [d.id for d in docs if any(BUCKET_LABEL.match(p.chapter_label) for p in d.passages)]
    return ({f"structure.bucket_chapters_with_headings:{collection}": sorted(ids)}
            if ids else {})


# --------------------------------------------------------------------------- Syllabus

SYLLABUS_FILE = "syllabus-of-errors.html"
_SECTION = re.compile(r"§(\d+)\s*$")


def syllabus_body_boundary(documents: list[Document], units: list[SourceUnit]) -> Failures:
    """The Syllabus's passages name exactly the propositions 1 to 80, and no measurable
    sentence of the source's body after its proposition 80 is in them."""
    docs = [d for d in documents
            if (d.metadata or {}).get("source_key") == "encyclicals/syllabus-of-errors"]
    if not docs or not units:
        return {}
    numbers = {int(m.group(1)) for d in docs for p in d.passages
               if (m := _SECTION.search(unit_reference(p.reference)))}
    failing = []
    if numbers != set(range(1, SYLLABUS_PROPOSITIONS + 1)):
        failing.append(f"propositions:{len(numbers)}")
    body = [u for u in units if u.region == "body"]
    last = next((i for i, u in enumerate(body) if u.unit_id == str(SYLLABUS_PROPOSITIONS)), None)
    if last is not None:
        text = match_key(normalize(" ".join(p.content for d in docs for p in d.passages)))
        after = [match_key(s) for u in body[last + 1:] for s in split_sentences(u.text)
                 if measurable(s)]
        if any(s in text for s in after):
            failing.append(f"after-{SYLLABUS_PROPOSITIONS}")
    return {"structure.syllabus_body_boundary:encyclicals": failing} if failing else {}


# --------------------------------------------------------------------------- Summa

def summa_role(label: str | None) -> str | None:
    """The part a Summa unit_label names: objection, sed contra, determination, reply."""
    if not label:
        return None
    for prefix, role in (("Objection", "objection"), ("On the contrary", "sed-contra"),
                         ("I answer that", "determination"), ("Reply", "reply")):
        if label.startswith(prefix):
            return role
    return None


def load_summa_corrections(path: str = SUMMA_CORRECTIONS) -> dict:
    """R7's reviewed corrections file (docs/research/R7-summa-structure.md, section 8)."""
    if not os.path.exists(path):
        return {"paragraphs": {}, "articles": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reply_only_articles(corrections: dict) -> set[str]:
    """Articles R7 confirmed have no determination in the Latin either (I q.74 a.3 and
    q.91 a.4). R7 found I q.117 a.2 is not one: CCEL lost its determination's opening."""
    return {a for a, facts in corrections.get("articles", {}).items() if facts.get("reply_only")}


def article_id(passage) -> str:
    """The source div id a Summa passage's structural anchor names (summa/<div>/<para>)."""
    parts = passage.anchor.split("/")
    return parts[1] if len(parts) > 2 else passage.chapter_key


def summa_one_disputation(documents: list[Document], reply_only: set[str]) -> Failures:
    failing = []
    for d in documents:
        for key, group in itertools.groupby(d.passages, key=lambda p: p.chapter_key):
            passages = list(group)
            roles = [summa_role(p.unit_label) for p in passages]
            runs = [r for r, _ in itertools.groupby(r for r in roles if r)]
            determinations = runs.count("determination")
            article = article_id(passages[0])
            restart = False
            if "determination" in roles:
                after = passages[roles.index("determination"):]
                restart = any(p.unit_label == "Objection 1" for p in after)
            if (determinations > 1 or restart
                    or (determinations == 0 and runs and article not in reply_only)):
                failing.append(article)
    return ({"structure.summa.one-disputation-per-article:summa": failing} if failing else {})


# --------------------------------------------------------------------------- ThML works

_BOOK_PREFIX = re.compile(r"^(?:Book|Bk\.)\s")
_CHAPTER_ONLY = re.compile(r"^(?:Chap\.|Chapter)\s+[IVXLC\d]+\b")


def embedded_work_labelled(collection: str, documents: list[Document]) -> Failures:
    out: Failures = {}
    for d in documents:
        chapters = [(label, next(group)) for label, group
                    in itertools.groupby(d.passages, key=lambda p: p.chapter_label)]
        booked = [bool(_BOOK_PREFIX.match(label)) for label, _ in chapters]
        if not any(booked):
            continue
        runs, current = [], []
        for (label, first), is_booked in list(zip(chapters, booked))[booked.index(True):]:
            if not is_booked and _CHAPTER_ONLY.match(label) and not first.work_key:
                current.append(first.chapter_key)
                continue
            if current:
                runs.append(current)
            current = []
        if current:
            runs.append(current)
        units = [run[0] for run in runs if len(run) >= CHAPTER_RUN_MIN]
        if units:
            out[f"structure.embedded_work_labelled:{collection}/{d.id}"] = units
    return out


# --------------------------------------------------------------------------- report only

def large_chapters(collection: str, documents: list[Document],
                   limit: int = CHAPTER_SIZE_LIMIT) -> list[dict]:
    """Report only: chapters over `limit` characters, largest first."""
    sizes: dict[tuple[str, str], list[int]] = {}
    for d in documents:
        for p in d.passages:
            entry = sizes.setdefault((d.id, p.chapter_key), [0, 0])
            entry[0] += len(p.content)
            entry[1] += 1
    rows = [{"collection": collection, "document_id": doc, "chapter_key": key,
             "characters": chars, "passages": n}
            for (doc, key), (chars, n) in sizes.items() if chars > limit]
    return sorted(rows, key=lambda r: -r["characters"])


# --------------------------------------------------------------------------- entry point

def run(collection: str, documents: list[Document], *,
        documents_by_file: dict[str, list[Document]] | None = None,
        units_by_file: dict[str, list[SourceUnit]] | None = None,
        sources: str = SOURCES, corrections: dict | None = None) -> Failures:
    """Every failing structure check for one collection. The source-reading checks
    (canon chapter numbers, papal buckets, the Syllabus) run when `units_by_file` is
    given or, for canon law, when the sources are present."""
    out: Failures = {}
    if collection in CONTIGUOUS_COLLECTIONS:
        out.update(chapter_contiguous(collection, documents))
    if collection == "canon-law" and os.path.isdir(os.path.join(sources, "canon-law")):
        out.update(canon_chapter_number_agreement(documents, canon_chapters(sources)))
    if collection == "councils":
        out.update(chapter_sequence(collection, documents))
    if collection in PAPAL_COLLECTIONS and documents_by_file is not None and units_by_file:
        out.update(bucket_chapters_with_headings(collection, documents_by_file, units_by_file))
    if collection == "encyclicals" and units_by_file:
        out.update(syllabus_body_boundary(documents, units_by_file.get(SYLLABUS_FILE, [])))
    if collection == "summa":
        corrections = load_summa_corrections() if corrections is None else corrections
        out.update(summa_one_disputation(documents, reply_only_articles(corrections)))
    if collection in ("church-fathers", "medieval"):
        out.update(embedded_work_labelled(collection, documents))
    return out
