"""Numbered units: each present exactly once, none invented.

One function per numbered family, each returning a SequenceResult of unit ids. A unit id
names one unit (a verse "DAG/13/1", canon "266", article "FP_Q71"); `check_ids` groups a
result into the stable check ids that `known_defects.json` lists.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from checks.coverage import _PassageText, documents_by_file, match_key, measurable
from checks.coverage import split_sentences
from checks.source_text import SourceUnit
from model import Document

CCC_LAST = 2865
CANON_LAST = 1752
THML_CHAPTER_MIN_CHARS = 100
THML_CHAPTER_MIN_COVERED = 0.5
# A source paragraph number opens a section only when it advances the count by at most
# this much; lower numbers are list items or restarted note numbers.
MAX_SECTION_STEP = 3


@dataclass
class SequenceResult:
    missing: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    out_of_range: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.duplicated or self.out_of_range)

    def to_json(self) -> dict:
        return {"missing": self.missing, "duplicated": self.duplicated,
                "out_of_range": self.out_of_range}


def _anchor_base(anchor: str) -> str:
    """The unit an anchor names, without the split-piece suffix ("/p2", "-p2", "-2" on a
    Bible piece)."""
    return re.sub(r"(?:/p\d+|-p\d+)(?:-\d+)?$", "", anchor)


def _numeric_sort(ids):
    def key(s: str):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
    return sorted(set(ids), key=key)


# --------------------------------------------------------------------------- Bible

_BIBLE_REF = re.compile(r"^(?P<book>.+?) (?P<c1>\d+)(?::(?P<v1>\d+)(?:–(?:(?P<c2>\d+):)?(?P<v2>\d+))?)?$")


def bible_verses(documents: list[Document], units: list[SourceUnit]) -> SequenceResult:
    """Every USFM verse with text falls inside some passage's verse range, read from
    the passage reference ("Esther 4:4–17", "Genesis 1:1–2:3", "Psalms 23")."""
    files = sorted({u.source_file for u in units})
    placed = documents_by_file("bible", documents, files)
    result = SequenceResult()
    for name in files:
        verses = [u.unit_id for u in units
                  if u.source_file == name and u.region == "body" and u.unit_id]
        code = verses[0].split("/")[0] if verses else ""
        order = {v: i for i, v in enumerate(verses)}
        by_chapter: dict[int, list[int]] = defaultdict(list)
        for v in verses:
            _, c, n = v.split("/")
            by_chapter[int(c)].append(int(n))
        hits: Counter = Counter()
        for doc in placed[name]:
            seen: set[str] = set()
            for p in doc.passages:
                base = _anchor_base(re.sub(r"-\d+$", "", p.anchor))
                if (base, p.reference) in seen:
                    continue
                seen.add((base, p.reference))
                m = _BIBLE_REF.match(p.reference)
                if not m:
                    result.out_of_range.append(f"{code}:{p.reference}")
                    continue
                c1 = int(m["c1"])
                if m["v1"] is None:          # a whole chapter
                    span = [f"{code}/{c1}/{n}" for n in by_chapter.get(c1, [])]
                    if not span:
                        result.out_of_range.append(f"{code}/{c1}")
                else:
                    v1 = int(m["v1"])
                    c2 = int(m["c2"]) if m["c2"] else c1
                    v2 = int(m["v2"]) if m["v2"] else v1
                    first, last = f"{code}/{c1}/{v1}", f"{code}/{c2}/{v2}"
                    for end in (first, last):
                        if end not in order:
                            result.out_of_range.append(end)
                    if first in order and last in order:
                        span = verses[order[first]:order[last] + 1]
                    else:
                        span = [v for v in verses
                                if (c1, v1) <= tuple(map(int, v.split("/")[1:])) <= (c2, v2)]
                hits.update(span)
        result.missing += [v for v in verses if not hits[v]]
        result.duplicated += [v for v in verses if hits[v] > 1]
    return result


# --------------------------------------------------------------------------- Catechism

_CCC_REF = re.compile(r"§(\d+)(?:–(\d+))?")


def ccc_paragraphs(documents: list[Document]) -> SequenceResult:
    """Paragraphs 1 to 2865 each present once, read from passage references
    ("CCC §1–5", "CCC §12, §14 (part)") and unit labels."""
    counts: Counter = Counter()
    for doc in documents:
        seen: set[str] = set()
        for p in doc.passages:
            base = _anchor_base(p.anchor)
            if base in seen:
                continue
            seen.add(base)
            numbers: set[int] = set()
            for m in _CCC_REF.finditer(p.reference):
                lo = int(m[1])
                hi = int(m[2]) if m[2] else lo
                numbers.update(range(lo, hi + 1))
            if p.unit_label:
                numbers.update(int(n) for n in re.findall(r"§(\d+)", p.unit_label))
            counts.update(numbers)
    return SequenceResult(
        missing=[str(n) for n in range(1, CCC_LAST + 1) if not counts[n]],
        duplicated=[str(n) for n in range(1, CCC_LAST + 1) if counts[n] > 1],
        out_of_range=[str(n) for n in sorted(counts) if not 1 <= n <= CCC_LAST])


# --------------------------------------------------------------------------- canons

_CANON_ANCHOR = re.compile(r"^can/(\d+)$")
# A canon heading inside a passage's text: "Can. N" at the start of a line or straight
# after a full stop, optionally behind the "n" amendment marker. Cross-references read
# "can. 1376" or "in Can. 312, §1", preceded by a word.
_CANON_HEADING = re.compile(r"(?:^|[\n.])\s*n?Can\.\s*(\d+)")


def canons(documents: list[Document]) -> SequenceResult:
    """Canons 1 to 1752 each the subject of exactly one passage anchored can/<n>, and
    no passage whose text holds another canon's "Can. <m>" heading. A canon whose
    heading sits inside another canon's passage is reported as duplicated."""
    anchored: Counter = Counter()
    glued: list[str] = []
    for doc in documents:
        for p in doc.passages:
            m = _CANON_ANCHOR.match(_anchor_base(p.anchor))
            own = int(m[1]) if m else None
            if own is not None:
                anchored[own] += 1
            for h in _CANON_HEADING.finditer(p.content):
                if int(h[1]) != own:
                    glued.append(h[1])
    duplicated = [str(n) for n in sorted(anchored) if anchored[n] > 1] + glued
    return SequenceResult(
        missing=[str(n) for n in range(1, CANON_LAST + 1) if not anchored[n]],
        duplicated=_numeric_sort(duplicated),
        out_of_range=[str(n) for n in sorted(anchored) if not 1 <= n <= CANON_LAST])


# --------------------------------------------------------------------------- Summa

# An editor's note inside a Summa title: "OF ENJOYMENT [*Or, Fruition], WHICH IS …".
_TITLE_NOTE = re.compile(r"\[\*(?:[^\[\]]|\[[^\]]*\])*\]")


def _title_key(text: str) -> str:
    """A div title as compared with passage references: editor's notes removed, then
    letters and digits only. "Question. 71 - ON THE WORK…" and "Question 71 - On the
    Work…" agree."""
    return match_key(_TITLE_NOTE.sub(" ", text).lower())


def summa_articles(documents: list[Document], units: list[SourceUnit],
                   articles: list[tuple[str, str, str, str]]) -> SequenceResult:
    """Every article in summa.xml present. `articles` is (id, part title, question
    title, article title) for every div4, and for every question div3 that holds its
    text directly ("one article" questions such as FP_Q71, and the Prologue of the
    First Part of the Second Part), whose article title is "". An article is present
    when some passage's reference names its question number and its article title."""
    references = [_title_key(ref) for ref in dict.fromkeys(
        p.reference for d in documents for p in d.passages)]
    keys: Counter = Counter(a[0] for a in articles)
    result = SequenceResult(duplicated=[a for a, n in keys.items() if n > 1])
    for art_id, _part, question, article in articles:
        # The question's number and the article's own title, or for a question holding
        # its text directly the question's title. Part names are not compared: the
        # adapter rewrites "(XP)" as "Supplement".
        number = re.search(r"(\d+)", question)
        q = re.compile(rf"question{number[1]}(?!\d)" if number else "")
        title = _title_key(article) if article else _title_key(question.split(" - ", 1)[-1])
        if not any(title in ref and q.search(ref) for ref in references):
            result.missing.append(art_id)
    return result


def summa_article_list(path: str) -> list[tuple[str, str, str, str]]:
    """(id, part, question, article) for the Summa's articles, read from the ThML."""
    from checks.source_text import _read_thml

    root = _read_thml(path)
    out = []
    for div1 in root.iter("div1"):
        part = div1.get("title") or ""
        for div3 in div1.iter("div3"):
            div4s = list(div3.iter("div4"))
            if div4s:
                out += [(d.get("id") or "", part, div3.get("title") or "", d.get("title") or "")
                        for d in div4s]
            elif any(len("".join(p.itertext()).strip()) >= THML_CHAPTER_MIN_CHARS
                     for p in div3.iter("p")):
                out.append((div3.get("id") or "", part, div3.get("title") or "", ""))
    return out


def summa_article_coverage(documents: list[Document], units: list[SourceUnit],
                           article_ids: set[str]) -> dict[str, tuple[int, int]]:
    """Body characters and covered characters per article (div4 id, or div3 id for a
    question holding its text directly), so a long article kept only in part is
    visible. Articles differ in length by two orders of magnitude, so presence alone
    says little about how much of a long one survives."""
    text = _PassageText(documents)
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for u in units:
        # Only articles: a question's introduction sits under the question's id.
        if u.region != "body" or u.unit_id not in article_ids:
            continue
        for s in split_sentences(u.text):
            if not measurable(s):
                continue
            row = out[u.unit_id]
            row[0] += len(s)
            if text.find(match_key(s)) is not None:
                row[1] += len(s)
    return {k: (v[0], v[1]) for k, v in out.items()}


# --------------------------------------------------------------------------- § numbers

def source_section_numbers(units: list[SourceUnit]) -> list[int]:
    """The section numbers of an HTML source's body, in order. A number counts only when
    it advances the count by 1 to MAX_SECTION_STEP, or jumps further and the next number
    follows on, so list items ("1. … 2. …") inside a section and restarted note numbers
    are not read as sections."""
    raw = [int(u.unit_id) for u in units
           if u.region == "body" and u.unit_id and u.unit_id.isdigit()]
    out: list[int] = []
    last = 0
    for i, n in enumerate(raw):
        following = raw[i + 1] if i + 1 < len(raw) else None
        # A longer jump counts when the next number continues from it (a gap in the
        # source's numbering, not a stray list item).
        if last < n <= last + MAX_SECTION_STEP or (n > last and following == n + 1):
            out.append(n)
            last = n
    return out


_SECTION_REF = re.compile(r"§(\d+)\s*$")


def numbered_paragraphs(document: Document, units: list[SourceUnit]) -> SequenceResult:
    """The § numbers in a document's passage references match the section numbers in
    its source body: none missing, none twice, none above the source's last (which
    catches footnotes read as sections)."""
    source = source_section_numbers(units)
    top = max(source, default=0)
    built: dict[int, set[str]] = defaultdict(set)
    for p in document.passages:
        m = _SECTION_REF.search(p.reference)
        if m:
            built[int(m[1])].add(_anchor_base(p.anchor))
    return SequenceResult(
        missing=[str(n) for n in source if n not in built],
        duplicated=[str(n) for n in sorted(built) if len(built[n]) > 1],
        out_of_range=[str(n) for n in sorted(built) if n > top])


# --------------------------------------------------------------------------- ThML

def thml_chapters(documents: list[Document], units: list[SourceUnit],
                  editorial: set[str] = frozenset()) -> SequenceResult:
    """Every ThML div holding 100 or more characters of body text of its own is
    represented by its passages: at least THML_CHAPTER_MIN_COVERED of its measured
    characters reach one. The test is by characters, not by any one sentence, because
    divs range from a 100-character greeting to a 66,000-character work, and a long
    dropped work can share a quoted verse or two with the passages around it.
    Divs whose own text is all short sentences cannot be judged and are skipped.

    The editorial divs (`editorial`, from editorial_divs.json) are the reverse: one
    that does reach a passage is reported in `out_of_range`, text that should not be
    in the corpus under rule G."""
    text = _PassageText(documents)
    own: dict[str, list[str]] = defaultdict(list)
    edited: dict[str, list[str]] = defaultdict(list)
    for u in units:
        if u.region == "body" and u.unit_id:
            own[u.unit_id].append(u.text)
        elif u.region == "apparatus" and u.unit_id in editorial:
            edited[u.unit_id].append(u.text)
    result = SequenceResult()
    for div_id, texts in edited.items():
        measured, covered = _covered_chars(text, texts)
        if measured and covered >= THML_CHAPTER_MIN_COVERED * measured:
            result.out_of_range.append(div_id)
    for div_id, texts in own.items():
        if sum(len(" ".join(t.split())) for t in texts) < THML_CHAPTER_MIN_CHARS:
            continue
        measured, covered = _covered_chars(text, texts)
        if measured and covered < THML_CHAPTER_MIN_COVERED * measured:
            result.missing.append(div_id)
    return result


def _covered_chars(text: _PassageText, texts: list[str]) -> tuple[int, int]:
    measured = covered = 0
    for t in texts:
        for s in split_sentences(t):
            if not measurable(s):
                continue
            measured += len(s)
            if text.find(match_key(s)) is not None:
                covered += len(s)
    return measured, covered


# --------------------------------------------------------------------------- check ids

def check_ids(family: str, scope: str, result: SequenceResult) -> dict[str, list[str]]:
    """Group a result into stable check ids → the unit ids behind each. Canons, Catechism
    paragraphs, Summa articles and ThML divs are one check per unit (a div is
    "<collection>/<file>#<div id>"); Bible verses one per chapter; § numbers one per
    source file (`scope`)."""
    out: dict[str, list[str]] = defaultdict(list)
    for kind in ("missing", "duplicated", "out_of_range"):
        for unit in getattr(result, kind):
            if family in ("canons", "ccc_paragraphs", "summa_articles"):
                key = f"sequence.{family}.{kind}:{unit}"
            elif family == "bible_verses":
                key = f"sequence.{family}.{kind}:{'/'.join(unit.split('/')[:2])}"
            elif family == "thml_chapters":
                key = f"sequence.{family}.{kind}:{scope}#{unit}"
            else:
                key = f"sequence.{family}.{kind}:{scope}"
            out[key].append(unit)
    return dict(out)
