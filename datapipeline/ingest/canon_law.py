"""Code of Canon Law (1983) ingestion (dual pipeline).

Reads the vendored vatican.va canon pages from sources/canon-law/ and builds a
single Document with one Passage per canon, plus one unsearchable history passage
for each superseded text a page prints (rule F, D11; item 1.5a).

Each page is read in two steps, segment first and then match: every block (a <p>,
or a loose "Can. N" run outside any <p>) is split at its <br>s, the amendment
marker (a brown "n") is taken out and remembered, and only then is "Can. N"
matched at the start of a segment, so a canon glued behind another after <br><br>
or behind its marker is found. The page is read in regions: the body; the notes
after a rule line or the marker legend, which are never canon text; and the
superseded versions after an "[Earlier version]" or "[Original version]" line,
which become history passages and are never the canon's content.

Each canon's heading path (Book, Part, Section, Title, Chapter, Article) comes from
the index page's table of contents joined to the body anchors by link, every lower
level reset at a higher boundary (C-13). The Book is assigned by canon number.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

from identity import anchor as make_anchor
from model import Document, Passage
from normalize.caps import smart_title_case
from normalize.text import clean_text
from registry import ANCHOR_SCHEME, resolve_document_id

_BASE = "http://www.vatican.va"
_DIR = os.path.dirname(os.path.dirname(__file__))
_SRC = os.path.join(_DIR, "sources", "canon-law")
_SPELLING = os.path.join(_DIR, "normalize", "canon_spelling.json")
_INDEX = "cic_index_en.html"

# 1983 CIC: fixed Book canon-number ranges + canonical English titles.
_BOOKS = [
    (1, 203, "Book I: General Norms"),
    (204, 746, "Book II: The People of God"),
    (747, 833, "Book III: The Teaching Function of the Church"),
    (834, 1253, "Book IV: The Sanctifying Function of the Church"),
    (1254, 1310, "Book V: The Temporal Goods of the Church"),
    (1311, 1399, "Book VI: Sanctions in the Church"),
    (1400, 1752, "Book VII: Processes"),
]
CANON_LAST = 1752
# Canons whose live passage held the superseded text, or a superseded text glued to the
# new one, and now hold the current text: same canon, new legal text (1.5a).
_TEXT_REPLACED = frozenset({265, 686, 694, 1308, 1310})
# The year the Code took effect: the year of every superseded text the page prints
# without the marker, which is the text as promulgated.
_CODE_YEAR = 1983


def _book_for(num: int) -> str:
    for lo, hi, name in _BOOKS:
        if lo <= num <= hi:
            return name
    return "Book ?: Unknown"


# Matches a full Roman numeral (used to re-uppercase ones smart_title_case
# lowercased — its acronym set only covers I–X, so XI+ come back as 'Xi').
_ROMAN_WORD = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def _fix_romans(label: str) -> str:
    return " ".join(
        w.upper() if len(w) > 1 and _ROMAN_WORD.match(w.upper()) else w
        for w in label.split())


def _clean_label(text: str) -> str:
    """Title-case an ALL-CAPS heading title; Roman numerals beyond X are re-uppercased."""
    return _fix_romans(smart_title_case(clean_text(text).strip().rstrip(".:").strip()))


# --------------------------------------------------------------------------- headings

_LEVELS = ("BOOK", "PART", "SECTION", "TITLE", "CHAPTER", "ARTICLE")
_LEVEL_NAMES = {"BOOK": "Book", "PART": "Part", "SECTION": "Section", "TITLE": "Title",
                "CHAPTER": "Chapter", "ARTICLE": "Article"}
_TOC_LINK = re.compile(r"(cic_lib\d-cann[\d-]+_en\.html)(?:#(.+))?$")
_TOC_HEADING = re.compile(
    r"^(BOOK|PART|SECTION|TITLE|CHAPTER|ARTICLE|ART\.)\s*([IVXLC]+|\d+)?\b\s*[.:]?\s*(.*)$",
    re.IGNORECASE | re.DOTALL)
_CANN_RANGE = re.compile(r"\(\s*Cann?\.[^)]*\)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Heading:
    level: str      # one of _LEVELS
    number: str     # "IV", "1"; "" when the source gives none
    title: str      # cleaned display title, "" when the source gives none

    @property
    def label(self) -> str:
        name = f"{_LEVEL_NAMES[self.level]} {self.number}".strip()
        return f"{name}: {self.title}" if self.title else name

    @property
    def key(self) -> str:
        return make_anchor(f"{self.level} {self.number}".strip())


def _toc(base: str = _SRC) -> dict[str, list[tuple[str | None, Heading]]]:
    """The index page's links, by body file: (anchor name or None for the file's top,
    heading), in index order."""
    with open(os.path.join(base, _INDEX), encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    out: dict[str, list[tuple[str | None, Heading]]] = defaultdict(list)
    for a in soup.find_all("a"):
        link = _TOC_LINK.search(a.get("href") or "")
        heading = _TOC_HEADING.match(_text(a))
        if not (link and heading):
            continue
        level = heading.group(1).upper().rstrip(".")
        title = _CANN_RANGE.sub("", heading.group(3)).strip()
        out[link.group(1)].append((
            link.group(2).rstrip(".") if link.group(2) else None,
            Heading("ARTICLE" if level == "ART" else level,
                    (heading.group(2) or "").upper(), _clean_label(title) if title else "")))
    return out


def _enter(path: tuple[Heading, ...], heading: Heading) -> tuple[Heading, ...]:
    """The heading path after `heading` opens: every level at or below its own resets."""
    rank = _LEVELS.index(heading.level)
    return tuple(h for h in path if _LEVELS.index(h.level) < rank) + (heading,)


# --------------------------------------------------------------------------- one page

_MARK = "\ue000"   # where an amendment marker stood
_BREAK = "\ue001"  # a <br>
_MARKER_COLOUR = "#663300"
_CANON = re.compile(r"^Can?\.?\s*(\d{1,4})\b\s*(.*)$", re.DOTALL)
_RULE = re.compile(r"^_{5,}$")
_LEGEND = re.compile(r"^\(\s*:?\s*(?:indicates that the text corresponds|Indica che il testo)",
                     re.IGNORECASE)
_VERSION = re.compile(r"^[\[(]\s*(?:Earlier|Original|precedente)\s+version|"
                      r"^\(\s*(?:earlier version|precedente versione)\s*\)", re.IGNORECASE)
_CONTINUATION = re.compile(r"^(?:§\s*\d|\d+\s*[/°]|\d+\.\s)")
_STRUCTURE = re.compile(r"^(?:BOOK|PART|SECTION|TITLE|CHAPTER|ART\.|ARTICLE)\b")
# The page's bracketed reference to an amending act, inside a canon (cc. 230, 588, 695,
# 699, 579): "[Cf. <act> (10 January 2021)]", "[<act>, 25 March 2026]", "(Cf. <act>, 18
# May 2022 – <dicastery>)", "(Apostolic Letter … 1st November 2020)". Rule G editorial text.
_ACT_BRACKET = re.compile(r"\s*(?:\[[^\[\]]*\b(?:19|20)\d\d\s*\)?\s*\]"
                          r"|\(\s*(?:Cf\.|Apostolic Letter|Rescript)[^()]*\b(?:19|20)\d\d\b[^()]*\))")
_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)? (January|February|March|April|May|June|July|"
                   r"August|September|October|November|December),? ((?:19|20)\d\d)\b|"
                   r"\b(?:January|February|March|April|May|June|July|August|September|"
                   r"October|November|December) \d{1,2}, ((?:19|20)\d\d)\b")
_LEADING_DASH = re.compile(r"^[—–]\s*")
_LEADING_COLON = re.compile(r"^:\s*")
_ACT_NOTE = re.compile(r"^Apostolic Letter issued\b")
_SECTION_SPACE = re.compile(r"^(§\s*\d+\.)(?=\w)")
_GUILLEMETS = re.compile(r"^«(.*)»\.?$", re.DOTALL)
# A note line that names a canon: "Can. 588: Cf. …", "Can. 604 §3.: Cf. …".
_NOTE_LINE = re.compile(r"^(?:§\s*\d+\.?\s*)?:\s*(?:Cf|Apostolic|Rescript|see)", re.IGNORECASE)
_NAMED = re.compile(r"\bCan(?:on)?s?\.?\s*(\d{1,4})")


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ")).strip()


@dataclass
class Act:
    """An amending act a page links to."""
    title: str
    url: str
    year: int | None


@dataclass
class CanonText:
    """One printed text of a canon on a page."""
    number: int
    parts: list[str]
    marked: bool
    superseded: bool
    file: str
    path: tuple[Heading, ...]
    acts: list[Act] = field(default_factory=list)     # acts linked inside its text
    note_acts: list[Act] = field(default_factory=list)  # the page's notes naming it
    after_acts: list[Act] = field(default_factory=list)  # a note right after a superseded text
    cut: list[str] = field(default_factory=list)      # editorial spans taken out

    @property
    def content(self) -> str:
        return "\n".join(p for p in self.parts if p)


def _is_marker(el: Tag) -> bool:
    colour = (el.get("color") or "").lower()
    style = (el.get("style") or "").lower()
    return (colour == _MARKER_COLOUR or "rgb(102, 51, 0)" in style) \
        and el.get_text(strip=True) == "n"


def _act(a: Tag, context: str = "") -> Act | None:
    href = a.get("href") or ""
    if not href or href.startswith("#") or "cod-iuris-canonici" in href:
        return None
    url = href if href.startswith("http") else "https://www.vatican.va" + href
    title = re.sub(r"\s*\|\s*Francis\s*$", "", re.sub(r"\s+", " ", a.get_text(""))).strip()
    m = _DATE.search(title) or _DATE.search(context)
    year = int(m.group(3) or m.group(4)) if m else None
    title = re.sub(r"\s*\(\s*[^()]*\b(?:19|20)\d\d\s*\)\s*$", "", title).strip()
    title = re.sub(r",\s*(?:\d{1,2}(?:st|nd|rd|th)?\s+)?[A-Z][a-z]+ \d{4}$", "", title).strip()
    return Act(title=title, url=url, year=year) if title else None


def _wrap_loose_canons(soup: BeautifulSoup) -> None:
    """Wrap a run of inline content outside any <p> that opens with "Can. N" (Book VI's
    `<b>Can. 1330</b>— …`) into a <p> of its own, so it is read like the others."""
    inline = {"b", "strong", "i", "em", "font", "a", "span", "sup", "u", "br"}
    for b in soup.find_all(["b", "strong"]):
        if b.find_parent("p") or not _CANON.match(_text(b)) or b.parent is None:
            continue
        run = [b]
        for sib in b.next_siblings:
            if isinstance(sib, NavigableString) or (isinstance(sib, Tag) and sib.name in inline):
                run.append(sib)
            else:
                break
        p = soup.new_tag("p")
        b.insert_before(p)
        for node in run:
            p.append(node.extract())


def _blocks(soup: BeautifulSoup) -> list[Tag]:
    out = []
    for el in soup.find_all(["p", "li", "hr"]):
        if el.name == "li" and el.find("p"):
            continue
        if el.find_parent("li") and el.name == "p":
            continue
        out.append(el)
    return out


def _segments(block: Tag) -> list[tuple[str, bool, list[Act]]]:
    """A block's text split at its <br>s: (text, marked, acts linked in it)."""
    for font in block.find_all(["font", "span"]):
        if _is_marker(font):
            font.replace_with(_MARK)
    for br in block.find_all("br"):
        br.replace_with(_BREAK)
    links: list[tuple[str, Tag]] = []
    for a in block.find_all("a"):
        if a.get("href"):
            links.append((re.sub(r"\s+", " ", a.get_text("")).strip(), a))
    out = []
    for raw in block.get_text("").split(_BREAK):
        text = re.sub(r"\s+", " ", raw).strip()
        if not text.replace(_MARK, "").strip():
            continue
        marked = _MARK in text
        text = re.sub(r"\s+", " ", text.replace(_MARK, " ")).strip()
        acts = [act for t, a in links if t and t in text
                for act in [_act(a, text)] if act is not None]
        out.append((text, marked, acts))
    return out


def parse_canon_page(html: str, file: str = "",
                     toc: list[tuple[str | None, Heading]] | None = None,
                     path: tuple[Heading, ...] = ()) -> tuple[list[CanonText], list[str]]:
    """Every printed canon text on one page, in page order, and the note texts the page
    prints outside any canon (dropped, returned for review). `path` is the heading path
    in force when the page starts; the page's own headings come from `toc`, its index
    entries, joined to the body by anchor name, forward only.

    The page is read in three regions. The body holds the current canons. A rule line or
    the marker legend opens the notes, which are never canon text; a structural heading
    after them returns to the body (c. 297's note sits mid-page). A version line
    ("[Earlier version]", "(precedente versione):") opens the superseded texts, which
    hold only canons and their paragraphs, and last to the end of the page or the next
    note."""
    soup = BeautifulSoup(html, "lxml")
    _wrap_loose_canons(soup)
    entries = list(toc or [])
    i = 0
    while i < len(entries) and entries[i][0] is None:      # the file opens these
        path = _enter(path, entries[i][1])
        i += 1
    names = {id(a): a["name"].rstrip(".") for a in soup.find_all("a") if a.get("name")}

    canons: list[CanonText] = []
    notes: list[str] = []
    region = "body"                  # body | note | superseded
    group_acts: list[Act] = []       # the acts the current note group names
    current: CanonText | None = None
    last_old: CanonText | None = None   # the superseded text the next note follows

    for block in _blocks(soup):
        if region == "body":
            for a in block.find_all("a"):
                if id(a) in names and i < len(entries) and entries[i][0] == names[id(a)]:
                    path = _enter(path, entries[i][1])
                    i += 1
        if block.name == "hr":
            if canons and region == "body":
                region = "note"
            current = None
            continue
        for text, marked, acts in _segments(block):
            if _RULE.match(text) or _LEGEND.match(text):
                if region == "superseded" or canons:
                    region = "note"
                group_acts, current, last_old = [], None, None
                continue
            if _VERSION.match(text):
                region, current, last_old = "superseded", None, None
                group_acts += acts
                continue
            m = _CANON.match(text)
            if region == "body":
                if m and current is not None and current.parts \
                        and re.match(r"^[,;]", m.group(2)) \
                        and not re.search(r"[.:;]$", current.parts[-1]):
                    # The page breaks a paragraph inside a cross-reference ("…according
                    # to the norm of</p><p>Can. 1423, the conference…", c. 1439).
                    current.parts[-1] += f" can. {m.group(1)}{m.group(2)}"
                elif m:
                    current = _start(m, marked, acts, False, file, path)
                    canons.append(current)
                elif _STRUCTURE.match(text):
                    current = None
                elif current is not None:
                    current.marked |= marked
                    current.acts += acts
                    _add(current, text)
                continue
            if region == "note" and _STRUCTURE.match(text) and not marked:
                region, current = "body", None
                continue
            if region == "superseded" and m and not _NOTE_LINE.match(m.group(2)):
                current = _start(m, marked, acts, True, file, path)
                current.note_acts = list(group_acts)
                canons.append(current)
                last_old = current
                continue
            if region == "superseded" and current is not None and _CONTINUATION.match(text):
                current.marked |= marked
                _add(current, text)
                continue
            # A note: kept out of every canon, and read for the acts it names.
            notes.append(text)
            named = _named_canons(text)
            for c in canons:
                if c.number in named and not c.superseded:
                    c.note_acts += acts
            if last_old is not None:
                last_old.after_acts += acts
            group_acts += acts
            current = None
    return canons, notes


def _start(m: re.Match, marked: bool, acts: list[Act], superseded: bool, file: str,
           path: tuple[Heading, ...]) -> CanonText:
    canon = CanonText(number=int(m.group(1)), parts=[], marked=marked, superseded=superseded,
                      file=file, path=path, acts=list(acts))
    rest = _LEADING_COLON.sub("", _LEADING_DASH.sub("", m.group(2).strip()))
    if rest:
        _add(canon, rest)
    return canon


def _add(canon: CanonText, text: str) -> None:
    """Append one segment to a canon, taking out the page's bracketed act references and,
    at a canon's start, the note that introduces a quoted new text (c. 700)."""
    def cut(m: re.Match) -> str:
        canon.cut.append(m.group(0).strip())
        return ""
    text = _ACT_BRACKET.sub(cut, text).strip()
    if not canon.parts and _ACT_NOTE.match(text):
        canon.cut.append(text)
        return
    q = _GUILLEMETS.match(text)
    if q and not canon.parts:            # c. 700's new text, quoted by its note
        text = q.group(1).strip().rstrip(".") + "."
    text = _SECTION_SPACE.sub(r"\1 ", text)
    if text:
        canon.parts.append(text)


def _named_canons(text: str) -> set[int]:
    """The canons a note names before its act: "For Can. 111 and Can. 112: Cf. …"."""
    head = re.split(r"\b(?:Cf\b|see\b|Apostolic Letter|Rescript)", text, maxsplit=1)[0]
    return {int(n) for n in _NAMED.findall(head)}


# --------------------------------------------------------------------------- the Code

def _spelling() -> dict[int, list[tuple[str, str]]]:
    with open(_SPELLING, encoding="utf-8") as f:
        rows = json.load(f)["corrections"]
    out: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        out[int(r["canon"])].append((r["broken"], r["corrected"]))
    return out


def _respell(num: int, text: str, fixes: dict[int, list[tuple[str, str]]]) -> str:
    """Apply the reviewed spelling corrections for one canon (C-16): the source prints
    capital V for "ff" and Y for "ffi" in a few words. Each listed word must be found."""
    for broken, corrected in fixes.get(num, ()):
        new = re.sub(rf"\b{re.escape(broken)}\b", corrected, text)
        if new == text:
            raise ValueError(f"canon {num}: spelling {broken!r} is not in its text")
        text = new
    return text


def read_pages(base: str = _SRC) -> tuple[list[CanonText], list[str]]:
    """Every printed canon text of every page, in reading order, and the dropped notes."""
    with open(os.path.join(base, "pages.json"), encoding="utf-8") as f:
        pages = [p for p in json.load(f) if p.get("parsed", True)]
    toc = _toc(base)
    texts: list[CanonText] = []
    notes: list[str] = []
    path: tuple[Heading, ...] = ()
    for name in dict.fromkeys(p["file"] for p in pages):   # the manifest lists one twice
        with open(os.path.join(base, name), "rb") as fh:
            html = fh.read().decode("utf-8", "replace")
        got, dropped = parse_canon_page(html, name, toc.get(name, []), path)
        body = [t for t in got if not t.superseded]
        if body:
            path = body[-1].path
        texts += got
        notes += dropped
    return texts, notes


def choose_current(texts: list[CanonText]) -> tuple[dict[int, CanonText], list[CanonText]]:
    """The current text of each canon, and the superseded texts. A canon printed more
    than once outside a superseded block keeps the marked text; two unmarked ones are an
    error. Every superseded text is history."""
    current: dict[int, CanonText] = {}
    history: list[CanonText] = []
    for t in texts:
        if t.superseded:
            history.append(t)
            continue
        old = current.get(t.number)
        if old is None:
            current[t.number] = t
        elif t.marked and not old.marked:
            history.append(old)
            current[t.number] = t
        elif old.marked and not t.marked:
            history.append(t)
        else:
            raise ValueError(f"canon {t.number} is printed twice as current text "
                             f"({old.file}, {t.file})")
    return current, history


def history_year(text: CanonText, current: CanonText) -> int:
    """The year a superseded text took effect: 1983 for the text as promulgated, which the
    page prints without the marker; for a marked one, the year of the act that made it."""
    if not text.marked:
        return _CODE_YEAR
    years = sorted({a.year for a in text.after_acts if a.year}) \
        or sorted({a.year for a in text.note_acts + text.acts if a.year})
    later = {a.year for a in current.acts + current.note_acts if a.year}
    years = [y for y in years if y not in later] or years
    if not years:
        raise ValueError(f"canon {text.number}: no act dates its superseded text")
    return years[0]


def amending_act(canon: CanonText) -> Act | None:
    """The act that made a marked canon's current text: one linked inside it, else the
    one the page's notes name it with, else the note heading its superseded text."""
    for acts in (canon.acts, canon.note_acts):
        dated = [a for a in acts if a.year]
        if dated:
            return max(dated, key=lambda a: a.year)
        if acts:
            return acts[0]
    return None


def _path_parts(num: int, path: tuple[Heading, ...]) -> tuple[str, str, dict]:
    book = _book_for(num)
    below = [h for h in path if h.level != "BOOK"]
    key = make_anchor("canon-law", book.split(":")[0], *[h.key for h in below])
    label = " — ".join([book] + [h.label for h in below])
    levels = {lv.lower(): "" for lv in _LEVELS[1:]}
    for h in below:
        levels[h.level.lower()] = h.label
    return key, label, levels


def build_documents() -> list[Document]:
    texts, _ = read_pages()
    current, superseded = choose_current(texts)
    history: dict[int, list[CanonText]] = defaultdict(list)
    for t in superseded:
        history[t.number].append(t)
    # A superseded text names the acts the page prints with it; the canon's current
    # text takes them when nothing in or about it names its own.
    for num, olds in history.items():
        cur = current.get(num)
        if cur is not None and not cur.acts and not cur.note_acts:
            cur.note_acts = [a for o in olds for a in o.note_acts]
    fixes = _spelling()

    did = resolve_document_id("canon-law", "canon-law", ("canon-law",))
    passages: list[Passage] = []
    for num in sorted(current):
        cur = current[num]
        key, label, levels = _path_parts(num, cur.path)
        meta = {"book": _book_for(num), **levels, "canon": num}
        if cur.marked:
            act = amending_act(cur)
            meta["amended"] = True
            meta["amended_by"] = {"title": act.title, "url": act.url} if act else None
        if num in _TEXT_REPLACED:
            meta["text_replaced"] = "current text replaces superseded version"
        passages.append(Passage(
            content=_respell(num, clean_text(cur.content), fixes),
            reference=f"Code of Canon Law, Can. {num}",
            anchor=make_anchor("can", num),
            chapter_key=key, chapter_label=label,
            position=len(passages), unit_label=f"Can. {num}", metadata=meta))
        seen: set[int] = set()
        for old in history.get(num, ()):
            year = history_year(old, cur)
            if year in seen:
                raise ValueError(f"canon {num}: two superseded texts from {year}")
            seen.add(year)
            passages.append(Passage(
                content=_respell(num, clean_text(old.content), fixes),
                reference=f"Code of Canon Law, Can. {num} (text in force from {year})",
                anchor=f"can/{num}/history-{year}",
                chapter_key=key, chapter_label=label,
                position=len(passages), unit_label=f"Can. {num} (text in force from {year})",
                metadata={"book": _book_for(num), **levels, "canon": num,
                          "history_of": num, "in_force_from": year},
                searchable=False, superseded_by_anchor=make_anchor("can", num)))
    return [Document(id=did, collection="canon-law", title="Code of Canon Law (1983)",
                     author="Catholic Church", year=1983,
                     metadata={"source": "vatican.va", "source_key": "canon-law",
                               "anchor_scheme": ANCHOR_SCHEME},
                     passages=passages)]


def deduplicate_urls(hrefs: list[str], base: str = _BASE) -> list[str]:
    """Strip fragments, prepend base for relative URLs, deduplicate preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for href in hrefs:
        url = href.split("#")[0]
        if url.startswith("http"):
            abs_url = url
        else:
            abs_url = base + url
        if abs_url not in seen:
            seen.add(abs_url)
            result.append(abs_url)
    return result
