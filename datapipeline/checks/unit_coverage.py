"""Unit-level coverage and sentinels for the 6 Oct 2026 corpus reviews (corpus-cleanup
item 0.1d). They measure text that 0.1a's sentence coverage cannot see, because the loss
sits in a few units of a large file or in text the extractor used to call a heading.

- `coverage.catechism.paragraph_words:<n>`: for every CCC number, the words of its source
  paragraph (the US edition, `us-edition/ccc-us.json`, since #279) are at least
  PARAGRAPH_WORDS_MIN present in the passages whose reference cites it (C-03, Opus A-001).
  Words are compared as a multiset, so a paragraph split over pieces, or printed across
  lines, still counts.
- `coverage.bible.superscriptions`: each Psalm title (USFM `\\d`, which the extractor now
  counts as body text) is in the passage holding its psalm's first verse (C-11, Opus-2
  B-004). Psalm 119's later letter headings (BETH, GIMEL, …) head its later stanzas, so
  only a psalm's first title is held to its first passage; the rest must be in one of
  that psalm's passages (1.4a). One check; its units are the psalms ("PSA/51").
- `sentinel.ccc_1471_definition`: the sentence of CCC 1471 that defines an indulgence is in
  a passage. The test holds only its hash and length, no text: the sentence is found in
  the source by its hash, then looked for in the passages.
- `sentinel.sirach_prologue`: the `\\ip` paragraphs after `\\is1 The Prologue` in Sirach
  reach a passage; WEB-C's own `\\ip` introductions stay apparatus. Its value is the
  percentage of the prologue's measurable sentences found.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter

from checks.coverage import match_key, measurable, normalize, split_sentences
from checks.source_text import SOURCES, SourceUnit, _usfm_plain
from model import Document

PARAGRAPH_WORDS_MIN = 0.99
_WORD = re.compile(r"[^\W_]+")
_CCC_REF = re.compile(r"§(\d+)(?:–(\d+))?")

# The defining sentence of CCC 1471, as its sha256 over coverage's match key (letters and
# digits, lowercased) and that key's length. No text is kept here.
CCC_1471_SHA256 = "d038d0c7d3802055c0fa6c3647526b46d1c34a7b0f7e0780a2f5a8a11df1e971"
CCC_1471_LENGTH = 314
SIRACH_FILE = "eng-web-c_usfm/46-SIReng-web-c.usfm"


def _words(text: str) -> Counter:
    return Counter(w.lower() for w in _WORD.findall(normalize(text)))


def cited_paragraphs(reference: str) -> range:
    """The CCC numbers a Catechism passage's reference cites ("CCC §13–17 (part)")."""
    m = _CCC_REF.search(reference)
    if not m:
        return range(0)
    first = int(m.group(1))
    return range(first, int(m.group(2) or first) + 1)


def catechism_paragraph_words(documents: list[Document], units: list[SourceUnit],
                              minimum: float = PARAGRAPH_WORDS_MIN) -> dict[str, list[str]]:
    citing: dict[int, Counter] = {}
    for d in documents:
        for p in d.passages:
            for n in cited_paragraphs(p.reference):
                citing.setdefault(n, Counter()).update(_words(p.content))
    out: dict[str, list[str]] = {}
    for u in units:
        if u.region != "body" or not (u.unit_id or "").isdigit():
            continue
        source = _words(u.text)
        total = sum(source.values())
        if not total:
            continue
        found = sum((source & citing.get(int(u.unit_id), Counter())).values())
        if found / total < minimum:
            out[f"coverage.catechism.paragraph_words:{u.unit_id}"] = [
                f"{round(100 * found / total, 1)}%"]
    return out


def bible_superscriptions(documents: list[Document], units: list[SourceUnit]) -> dict[str, list[str]]:
    """Psalms whose first `\\d` title is not in the passage holding their first verse, or
    one of whose later `\\d` lines (Psalm 119's letters) is not in one of their passages
    directly before the opening words of the verse it heads."""
    titles: dict[str, list[str]] = {}
    heads: dict[str, list[str]] = {}     # a later title with the verse after it
    pending: str | None = None
    for u in units:
        if u.region != "body" or not u.unit_id:
            continue
        if u.unit_id.endswith("/d"):
            psalm = u.unit_id.rsplit("/", 1)[0]
            titles.setdefault(psalm, []).append(u.text)
            pending = psalm if len(titles[psalm]) > 1 else None
        elif pending is not None:
            heads.setdefault(pending, []).append(f"{titles[pending][-1]} {u.text[:60]}")
            pending = None
    if not titles:
        return {}
    psalms = next((d for d in documents if d.title == "Psalms"), None)
    first: dict[str, str] = {}
    every: dict[str, list[str]] = {}
    for p in psalms.passages if psalms else []:
        chapter = p.chapter_key.rsplit("/", 1)[-1]
        key = match_key(normalize(p.content))
        first.setdefault(chapter, key)
        every.setdefault(chapter, []).append(key)
    failing = []
    for psalm, texts in titles.items():
        chapter = psalm.split("/")[1]
        later = [match_key(normalize(h)) for h in heads.get(psalm, [])]
        if match_key(normalize(texts[0])) not in first.get(chapter, "") or any(
                not any(h in c for c in every.get(chapter, [])) for h in later):
            failing.append(psalm)
    return {"coverage.bible.superscriptions": sorted(failing, key=lambda x: int(x.split("/")[1]))
            } if failing else {}


def ccc_1471_definition(documents: list[Document], units: list[SourceUnit]) -> int:
    """1 when the defining sentence of CCC 1471 is in a Catechism passage, else 0 (also
    when the source no longer holds a sentence with the recorded hash and length)."""
    sentence = None
    for u in units:
        if u.region == "body" and u.unit_id == "1471":
            for s in split_sentences(u.text):
                key = match_key(s)
                if len(key) == CCC_1471_LENGTH and \
                        hashlib.sha256(key.encode()).hexdigest() == CCC_1471_SHA256:
                    sentence = key
    if sentence is None:
        return 0
    text = match_key(normalize(" ".join(p.content for d in documents for p in d.passages)))
    return int(sentence in text)


def sirach_prologue_text(path: str) -> list[str]:
    """The `\\ip` paragraphs after `\\is1 The Prologue`, up to the next other marker."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    out, inside = [], False
    for line in lines:
        if line.startswith("\\is1") and "Prologue" in line:
            inside = True
            continue
        if inside:
            if line.startswith("\\ip"):
                out.append(_usfm_plain(line[3:]))
            elif line.strip():
                break
    return out


def sirach_prologue(documents: list[Document], sources: str = SOURCES) -> int:
    """The percentage of the prologue's measurable sentences found in Sirach's passages."""
    path = os.path.join(sources, "bible", SIRACH_FILE)
    if not os.path.exists(path):
        return 0
    sentences = [s for text in sirach_prologue_text(path) for s in split_sentences(text)
                 if measurable(s)]
    if not sentences:
        return 0
    sirach = next((d for d in documents if d.title == "Sirach"), None)
    text = match_key(normalize(" ".join(p.content for p in sirach.passages))) if sirach else ""
    found = sum(len(s) for s in sentences if match_key(s) in text)
    return int(100 * found / sum(len(s) for s in sentences))
