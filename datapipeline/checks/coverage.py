"""How much of each source file's body text reaches a passage.

Body units are split into sentences. A sentence counts as covered when its normalized
form is a substring of the normalized concatenation of every passage built from the
same source file. Coverage is covered characters over the characters of the sentences
measured (30 characters or more); shorter fragments are counted separately.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from checks.source_text import SEGMENT_BREAK, SOURCES, SourceUnit
from model import Document

MIN_SENTENCE_CHARS = 30
MAX_UNCOVERED_LOCATIONS = 20

_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
                         "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
                         "\u00ab": '"', "\u00bb": '"'})
# Footnote markers ("[12]", "[12a]"), page markers ("[Page 45]") and the Bible's verse
# markers ("{{v:12}}"). A bracketed number after the Summa's reference tokens is part of
# the reference, not a marker: "Q[1], A[2]", "AA[3]", "QQ[1]-114", "OBJ[2]".
_MARKERS = re.compile(r"\[\s*(?:[Pp]age\s+)?\d+[a-z]?\s*\]|\{\{v:\d+\}\}")
_SUMMA_REF = re.compile(r"\b(?:Q|A|AA|QQ|OBJ)$")


def _drop_marker(m: re.Match) -> str:
    if m.group(0).startswith("[") and _SUMMA_REF.search(m.string, 0, m.start()):
        return m.group(0)
    return " "


_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[\W_]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def normalize(text: str) -> str:
    """NFKC, lowercase, curly quotes to straight, markers removed, whitespace collapsed."""
    text = _MARKERS.sub(_drop_marker, unicodedata.normalize("NFKC", text))
    return _WS.sub(" ", text.lower().translate(_QUOTES)).strip()


def match_key(normalized: str) -> str:
    """The form compared for coverage: the normalized text reduced to letters and
    digits. Adapters and this extractor join inline markup differently
    (`get_text(" ")` puts a space between "<i>Gentium</i>" and ","), print ellipses
    differently, and move markers such as "Objection 1:" into a label, so spacing and
    punctuation are not evidence either way."""
    return _NON_ALNUM.sub("", normalized)


def measurable(sentence: str) -> bool:
    """A sentence long enough to measure, with letters or digits to compare. A rule of
    asterisks or dots has an empty match key, which every text would contain."""
    return len(sentence) >= MIN_SENTENCE_CHARS and bool(match_key(sentence))


def split_sentences(text: str) -> list[str]:
    """Sentences of a text: split at SEGMENT_BREAK, blank lines, and [.!?] followed by
    whitespace and an uppercase letter. Returned normalized."""
    out: list[str] = []
    text = unicodedata.normalize("NFKC", text)
    for segment in re.split(rf"{SEGMENT_BREAK}|\n\s*\n", text):
        for sentence in _SENTENCE_END.split(segment):
            s = normalize(sentence)
            if s:
                out.append(s)
    return out


# --------------------------------------------------------------------------- mapping

_BIBLE_DIR = "eng-web-c_usfm"
_MANIFEST_COLLECTIONS = ("apostolic-exhortations", "councils", "encyclicals",
                         "papal-documents", "medieval")


def _bible_titles(sources: str) -> dict[str, str]:
    """USFM file → book title, from the file's \\toc2 short name. Greek-text books carry
    a " (Greek)" suffix the documents do not."""
    out = {}
    base = os.path.join(sources, "bible", _BIBLE_DIR)
    for name in sorted(os.listdir(base)):
        if not name.endswith(".usfm"):
            continue
        with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("\\toc2 "):
                    title = re.sub(r"\s*\(Greek\)\s*$", "", line[6:].strip())
                    out[f"{_BIBLE_DIR}/{name}"] = title
                    break
    return out


def documents_by_file(collection: str, documents: list[Document], files: list[str],
                      sources: str = SOURCES) -> dict[str, list[Document]]:
    """Which documents each source file feeds: `metadata["source_file"]` where the
    adapter sets it, else the vendored manifest (by URL), else the collection's single
    document. Raises when a document cannot be placed, so nothing escapes measurement."""
    out: dict[str, list[Document]] = {f: [] for f in files}
    by_url: dict[str, str] = {}
    if collection in _MANIFEST_COLLECTIONS:
        with open(os.path.join(sources, collection, "manifest.json"), encoding="utf-8") as f:
            by_url = {e["url"]: e["file"] for e in json.load(f) if e.get("url")}
    titles = _bible_titles(sources) if collection == "bible" else {}
    file_by_title = {t: f for f, t in titles.items()}
    for doc in documents:
        meta = doc.metadata or {}
        if meta.get("source_file") in out:
            out[meta["source_file"]].append(doc)
        elif meta.get("url") in by_url and by_url[meta["url"]] in out:
            out[by_url[meta["url"]]].append(doc)
        elif collection == "bible" and file_by_title.get(doc.title) in out:
            out[file_by_title[doc.title]].append(doc)
        elif collection in ("canon-law", "catechism", "summa") and len(documents) == 1:
            for f in files:
                out[f].append(doc)
        elif meta.get("source_file") or meta.get("url") in by_url or collection == "bible":
            continue    # placed on a file outside this measurement
        else:
            raise ValueError(f"{collection}: cannot place document {doc.title!r} on a source file")
    return out


# --------------------------------------------------------------------------- results

@dataclass
class FileCoverage:
    source_file: str
    documents: list[str]                 # document IDs built from this file
    body_chars: int = 0                  # characters of measured body sentences
    covered_chars: int = 0
    short_chars: int = 0                 # body text in sentences too short to measure
    note_chars: int = 0                  # all note text in the source
    note_leakage: int = 0                # note sentences found in passages
    passage_chars: int = 0               # characters of the passages built from it
    unattributed_chars: int = 0          # body characters no document could be given
    uncovered: list[tuple[str | None, str]] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return round(100 * self.covered_chars / self.body_chars, 2) if self.body_chars else 100.0

    @property
    def pct_with_notes(self) -> float:
        total = self.body_chars + self.note_chars
        return round(100 * self.covered_chars / total, 2) if total else 100.0


@dataclass
class DocumentCoverage:
    document_id: str
    title: str
    source_file: str
    body_chars: int = 0
    covered_chars: int = 0
    note_leakage: int = 0
    passage_chars: int = 0

    @property
    def pct(self) -> float:
        return round(100 * self.covered_chars / self.body_chars, 2) if self.body_chars else 100.0


@dataclass
class CoverageResult:
    collection: str
    files: dict[str, FileCoverage]
    documents: dict[str, DocumentCoverage]

    @property
    def body_chars(self) -> int:
        return sum(f.body_chars for f in self.files.values())

    @property
    def covered_chars(self) -> int:
        return sum(f.covered_chars for f in self.files.values())

    @property
    def note_chars(self) -> int:
        return sum(f.note_chars for f in self.files.values())

    @property
    def pct(self) -> float:
        return round(100 * self.covered_chars / self.body_chars, 2) if self.body_chars else 100.0

    def to_json(self, with_text: bool) -> dict:
        """with_text adds the uncovered-sentence snippets, for local output only."""
        files = {}
        for name, f in sorted(self.files.items()):
            row = {"documents": f.documents, "body_chars": f.body_chars,
                   "covered_chars": f.covered_chars, "pct": f.pct,
                   "pct_with_notes": f.pct_with_notes, "short_chars": f.short_chars,
                   "note_chars": f.note_chars, "note_leakage": f.note_leakage,
                   "passage_chars": f.passage_chars,
                   "unattributed_chars": f.unattributed_chars}
            if with_text:
                row["uncovered"] = [[u, s] for u, s in f.uncovered]
            files[name] = row
        documents = {d: {"title": c.title, "source_file": c.source_file,
                         "body_chars": c.body_chars, "covered_chars": c.covered_chars,
                         "pct": c.pct, "note_leakage": c.note_leakage,
                         "passage_chars": c.passage_chars}
                     for d, c in sorted(self.documents.items())}
        return {"collection": self.collection, "body_chars": self.body_chars,
                "covered_chars": self.covered_chars, "pct": self.pct,
                "note_chars": self.note_chars, "files": files, "documents": documents}


# --------------------------------------------------------------------------- matching

class _PassageText:
    """The match keys of a set of passages, searchable by sentence.

    A passage's text is its unit_label (the "Objection 1", "§4" or verse number a
    reader shows with it) followed by its content. Most source sentences equal a
    passage sentence exactly and are found in a dict; the rest are searched as
    substrings, through a sampled k-gram index when the text is large.
    """

    _K = 16          # k-gram length
    _STEP = 8        # every _STEP-th position of the text is indexed
    _INDEX_FROM = 1_000_000

    def __init__(self, documents: list[Document]):
        self._build([[f"{p.unit_label}\n\n{p.content}" if p.unit_label else p.content
                      for p in doc.passages] for doc in documents])

    @classmethod
    def from_texts(cls, texts: list[str]) -> "_PassageText":
        """The same index over plain texts (one owner), such as a source's body."""
        index = cls.__new__(cls)
        index._build([texts])
        return index

    def _build(self, owners: list[list[str]]) -> None:
        parts: list[str] = []
        self.owner: list[tuple[int, int]] = []   # (start offset, owner index)
        self.sentences: dict[str, int] = {}
        offset = 0
        for i, texts in enumerate(owners):
            self.owner.append((offset, i))
            for text in texts:
                for sentence in split_sentences(text):
                    key = match_key(sentence)
                    parts.append(key)
                    offset += len(key)
                    self.sentences.setdefault(key, i)
        self.text = "".join(parts)
        self._index: dict[str, list[int]] | None = None

    def _document_at(self, position: int) -> int:
        doc = self.owner[0][1]
        for start, i in self.owner:
            if start > position:
                break
            doc = i
        return doc

    def _search(self, key: str) -> int:
        if len(self.text) < self._INDEX_FROM or len(key) < self._K + self._STEP - 1:
            return self.text.find(key)
        if self._index is None:
            index: dict[str, list[int]] = defaultdict(list)
            for pos in range(0, len(self.text) - self._K + 1, self._STEP):
                index[self.text[pos:pos + self._K]].append(pos)
            self._index = index
        # The match starts somewhere; one of the next _STEP positions is indexed.
        for j in range(self._STEP):
            for pos in self._index.get(key[j:j + self._K], ()):
                start = pos - j
                if start >= 0 and self.text.startswith(key, start):
                    return start
        return -1

    def find(self, key: str) -> int | None:
        """Index of the document whose passages contain key, or None."""
        hit = self.sentences.get(key)
        if hit is not None:
            return hit
        position = self._search(key)
        return None if position < 0 else self._document_at(position)


def _div_ancestors(unit_id: str | None) -> list[str]:
    """ThML ids are dotted paths ("v.xiv.i" is inside "v.xiv"), so their ancestors
    can be read off the id. Deepest first, stopping at two segments (a work)."""
    if not unit_id:
        return []
    parts = unit_id.split(".")
    return [".".join(parts[:n]) for n in range(len(parts), 1, -1)]


def coverage(collection: str, documents: list[Document],
             units: list[SourceUnit], sources: str = SOURCES) -> CoverageResult:
    files = sorted({u.source_file for u in units})
    placed = documents_by_file(collection, documents, files, sources)
    units_by_file: dict[str, list[SourceUnit]] = defaultdict(list)
    for u in units:
        units_by_file[u.source_file].append(u)

    result = CoverageResult(collection, {}, {})
    for name in files:
        docs = placed[name]
        fc = FileCoverage(name, [d.id for d in docs])
        fc.passage_chars = sum(len(p.content) for d in docs for p in d.passages)
        result.files[name] = fc
        for d in docs:
            dc = result.documents.setdefault(
                d.id, DocumentCoverage(d.id, d.title, name))
            dc.passage_chars = sum(len(p.content) for p in d.passages)
        text = _PassageText(docs)

        # (unit, sentence length, document index or None) for each measured sentence.
        measured: list[tuple[SourceUnit, int, int | None, str]] = []
        for u in units_by_file[name]:
            if u.region == "note":
                for s in split_sentences(u.text):
                    fc.note_chars += len(s)
                    if measurable(s):
                        hit = text.find(match_key(s))
                        if hit is not None:
                            fc.note_leakage += 1
                            result.documents[docs[hit].id].note_leakage += 1
                continue
            if u.region != "body":
                continue
            for s in split_sentences(u.text):
                if not measurable(s):
                    fc.short_chars += len(s)
                    continue
                hit = text.find(match_key(s))
                fc.body_chars += len(s)
                measured.append((u, len(s), hit, s))
                if hit is not None:
                    fc.covered_chars += len(s)
                elif len(fc.uncovered) < MAX_UNCOVERED_LOCATIONS:
                    fc.uncovered.append((u.unit_id, s[:60]))

        _attribute(fc, docs, measured, result)
    return result


def _attribute(fc: FileCoverage, docs: list[Document],
               measured: list[tuple[SourceUnit, int, int | None, str]],
               result: CoverageResult) -> None:
    """Share a file's body characters among its documents. A single-document file gives
    them all to it. A multi-document ThML volume gives each sentence to the document
    whose passages cover most of the nearest enclosing work-level div; text in a div
    with no covered sentence at all (a work the adapter dropped) stays unattributed."""
    if not docs:
        fc.unattributed_chars = fc.body_chars
        return
    if len(docs) == 1:
        dc = result.documents[docs[0].id]
        dc.body_chars += fc.body_chars
        dc.covered_chars += fc.covered_chars
        return
    votes: dict[str, Counter] = defaultdict(Counter)
    for u, n, hit, _ in measured:
        if hit is not None:
            for prefix in _div_ancestors(u.unit_id):
                votes[prefix][hit] += n
    for u, n, hit, _ in measured:
        owner = hit
        if owner is None:
            for prefix in _div_ancestors(u.unit_id):
                if votes.get(prefix):
                    owner = votes[prefix].most_common(1)[0][0]
                    break
        if owner is None:
            fc.unattributed_chars += n
            continue
        dc = result.documents[docs[owner].id]
        dc.body_chars += n
        if hit is not None:
            dc.covered_chars += n


__all__ = ["CoverageResult", "DocumentCoverage", "FileCoverage", "coverage",
           "documents_by_file", "match_key", "measurable", "normalize", "split_sentences"]
