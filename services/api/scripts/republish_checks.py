#!/usr/bin/env python
"""Corpus cleanup 4.2: accuracy checks on the staged and the published corpus.

Each check is one of:

- a search: a question run through the production pipeline in process, as
  `run_eval_suite.py` does, with assertions over the passages it returns. Paid
  (HyDE, embedding, Cohere, the listwise reranker), so it runs only with `--spend`.
  A few also ask the explanation model about one returned passage.
- a keyword search: the full-text path alone (`retrieve_fts`), which is SQL. Free.
- a database check: one read-only SELECT. Free.
- an aggregate: an assertion over every passage the searches of this run returned.

Nothing is written anywhere. The pool is the API's, so `CORPUS_READ_SCHEMA=staging`
reads the staged corpus read-only (2.2w), and `QDRANT_READ_COLLECTION` names the
collection vector search reads (2.2b).

Usage (from services/api):
    python scripts/republish_checks.py --list                # every check; no calls
    python scripts/republish_checks.py                       # the free checks only
    python scripts/republish_checks.py --spend               # every check
    python scripts/republish_checks.py --only 4.2.ccc-2267 --spend
    python scripts/republish_checks.py --spend --json /path/to/result.json

Staging (4.1b step 2):
    CORPUS_READ_SCHEMA=staging QDRANT_READ_COLLECTION=chunks-<release> \\
        python scripts/republish_checks.py --spend

The spec is docs/corpus-cleanup/P4-P5-republish-expand.md, item 4.2.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import json
import re
import sys
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REMOVALS = Path(__file__).resolve().parents[3] / "datapipeline/registry/removals.json"

# Each search asks for this many results, the most a standard search returns.
QUOTA = 5

# The most a one-collection search cost in production over the 30 days to 15 Nov 2026
# (search_costs: average $0.0062, highest $0.0074, without explanations), for the
# estimate printed before a paid run. The run reports what it actually spent.
COST_PER_SEARCH = 0.0075


# --------------------------------------------------------------------------- results

@dataclass(frozen=True)
class Hit:
    """One passage a search returned, read back from the corpus by its ID."""

    id: str
    document_id: str
    collection: str
    document_title: str = ""
    # The author a card shows: the work's inside a container document, else the
    # document's (document_facts). A quoted Father's `passage_author` is separate.
    author: str | None = None
    anchor: str | None = None
    reference: str | None = None
    unit_label: str | None = None
    content: str = ""
    searchable: bool = True
    retired: bool = False
    voice: str | None = None
    language: str | None = None
    work_key: str | None = None
    text_source: str | None = None
    text_status: str | None = None
    official_latin_url: str | None = None
    # A Summa passage's article, as stored (metadata.article, 1.7).
    article: str | None = None
    # False when the corpus holds no row for an ID the pipeline returned.
    found: bool = True


@dataclass
class SearchRun:
    question: str
    collections: tuple[str, ...]
    results: list[Hit] = field(default_factory=list)
    # Every candidate the vector path returned, before fusion and reranking.
    vector: list[Hit] = field(default_factory=list)
    outcome: str = "success"
    degradations: list[str] = field(default_factory=list)
    error: str | None = None
    # Explanation text by passage ID, for the checks that ask for one.
    explanations: dict[str, str] = field(default_factory=dict)
    # What production gives the explanation model for a result, by passage ID: the
    # card as assembled, a Summa objection with its answer (stitch.with_stitched_content).
    explain_inputs: dict[str, str] = field(default_factory=dict)
    cost: float = 0.0
    # Wall-clock seconds for the whole run and for its vector search (4.0 step 5: the
    # pre-cutover run times search on the new Qdrant collection).
    seconds: float | None = None
    vector_seconds: float | None = None


@dataclass(frozen=True)
class Verdict:
    ok: bool
    detail: str


def _short(hit: Hit) -> str:
    return f"{hit.reference or hit.anchor or hit.id} [{hit.collection}]"


def _listing(hits: Sequence[Hit], limit: int = 5) -> str:
    if not hits:
        return "no results"
    shown = "; ".join(_short(h) for h in hits[:limit])
    more = f" (+{len(hits) - limit} more)" if len(hits) > limit else ""
    return shown + more


# --------------------------------------------------------------------------- registry

class Registry:
    """The removal registry (2.1, D4): which documents and passages an item removes."""

    def __init__(self, entries: list[dict]) -> None:
        self._entries = entries

    @classmethod
    def load(cls, path: Path = REMOVALS) -> Registry:
        return cls(json.loads(path.read_text()))

    def removed(
        self, added_by: str | Sequence[str], reason: str | None = None,
        documents: Sequence[str] = (),
    ) -> tuple[frozenset[str], frozenset[str]]:
        """Document IDs and passage IDs the open entries of these items retire.

        `documents` narrows to entries on those documents: a document entry retires
        the document, a passage entry one passage of it. Span and class entries cut
        text inside a passage that stays, so they are not counted. Raises LookupError
        when nothing matches, so a check never passes by checking nothing.
        """
        items = {added_by} if isinstance(added_by, str) else set(added_by)
        docs, passages = set(), set()
        for e in self._entries:
            if e.get("added_by") not in items or e.get("closed_by"):
                continue
            if reason is not None and e.get("reason") != reason:
                continue
            if documents and e.get("document_id") not in documents:
                continue
            if e.get("scope") == "document":
                docs.add(e["document_id"])
            elif e.get("scope") == "passage" and e.get("passage_id"):
                passages.add(e["passage_id"])
        if not docs and not passages:
            raise LookupError(
                f"the removal registry has no open document or passage entry added by "
                f"{', '.join(sorted(items))}"
                + (f" with reason {reason}" if reason else "")
                + (f" on {len(documents)} named documents" if documents else "")
                + "; has that item merged?"
            )
        return frozenset(docs), frozenset(passages)


# --------------------------------------------------------------------------- matchers

@dataclass(frozen=True)
class Match:
    """A passage, described by the facts that identify it. Every field set must hold."""

    document: str | None = None
    collection: str | None = None
    # The unit and its later pieces: "nostra-aetate/4" matches "nostra-aetate/4" and
    # "nostra-aetate/4/from-e18", not "nostra-aetate/40".
    anchor: str | None = None
    reference: str | None = None    # regex, searched
    label: str | None = None        # regex on unit_label, searched
    text: str | None = None         # substring of the text, any case
    voice: str | None = None
    text_source: str | None = None
    text_status: str | None = None
    work_key: str | None = None
    author: str | None = None       # regex on the author the card shows
    what: str = ""                  # how --list names it; generated when empty

    def matches(self, hit: Hit, registry: Registry | None = None) -> bool:
        if self.document and hit.document_id != self.document:
            return False
        if self.collection and hit.collection != self.collection:
            return False
        if self.anchor and not (
            hit.anchor == self.anchor or (hit.anchor or "").startswith(self.anchor + "/")
        ):
            return False
        if self.reference and not re.search(self.reference, hit.reference or ""):
            return False
        if self.label and not re.search(self.label, hit.unit_label or ""):
            return False
        if self.text and self.text.lower() not in hit.content.lower():
            return False
        for name in ("voice", "text_source", "text_status", "work_key"):
            wanted = getattr(self, name)
            if wanted and getattr(hit, name) != wanted:
                return False
        if self.author and not re.search(self.author, hit.author or ""):
            return False
        return True

    def describe(self) -> str:
        if self.what:
            return self.what
        parts = []
        if self.anchor:
            parts.append(f"anchor {self.anchor}")
        if self.reference:
            parts.append(f"citation /{self.reference}/")
        if self.label:
            parts.append(f"label /{self.label}/")
        if self.text:
            parts.append(f'text "{self.text}"')
        for name in ("voice", "text_source", "text_status", "work_key", "collection"):
            if getattr(self, name):
                parts.append(f"{name} {getattr(self, name)}")
        if self.author:
            parts.append(f"author /{self.author}/")
        if self.document:
            parts.append(f"in document {self.document[:8]}")
        return "a passage with " + ", ".join(parts)


@dataclass(frozen=True)
class Removed:
    """Any passage an item's removal entries retire, read from the registry."""

    added_by: str | tuple[str, ...]
    documents: tuple[str, ...] = ()
    reason: str | None = None
    what: str = ""

    def matches(self, hit: Hit, registry: Registry | None = None) -> bool:
        assert registry is not None
        docs, passages = registry.removed(self.added_by, self.reason, self.documents)
        return hit.document_id in docs or hit.id in passages

    def describe(self) -> str:
        return self.what or f"a passage {self.added_by} removes"


Matcher = Match | Removed


def _resolve(match: Matcher, registry: Registry | None) -> None:
    """Read a removal selector's targets before looking at any result, so a selector
    that names nothing errors even when the search returned nothing."""
    if isinstance(match, Removed):
        assert registry is not None
        registry.removed(match.added_by, match.reason, match.documents)


# --------------------------------------------------------------------------- search assertions

class Assertion:
    def __call__(self, run: SearchRun, registry: Registry) -> Verdict:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class Some(Assertion):
    """At least one result matches, within the first `within` when it is set."""

    match: Matcher
    within: int | None = None

    def __call__(self, run, registry):
        _resolve(self.match, registry)
        pool = run.results[: self.within] if self.within else run.results
        found = [h for h in pool if self.match.matches(h, registry)]
        if found:
            return Verdict(True, f"found {_short(found[0])}")
        return Verdict(False, f"none of: {_listing(run.results)}")

    def describe(self):
        where = f" in the first {self.within}" if self.within else ""
        return f"returns {self.match.describe()}{where}"


@dataclass(frozen=True)
class First(Assertion):
    match: Matcher

    def __call__(self, run, registry):
        _resolve(self.match, registry)
        if run.results and self.match.matches(run.results[0], registry):
            return Verdict(True, f"first is {_short(run.results[0])}")
        return Verdict(False, f"first is not it: {_listing(run.results)}")

    def describe(self):
        return f"returns {self.match.describe()} first"


@dataclass(frozen=True)
class NoneOf(Assertion):
    match: Matcher

    def __call__(self, run, registry):
        _resolve(self.match, registry)
        bad = [h for h in run.results if self.match.matches(h, registry)]
        if bad:
            return Verdict(False, f"returned {_listing(bad)}")
        return Verdict(True, f"none among {len(run.results)} results")

    def describe(self):
        return f"never returns {self.match.describe()}"


@dataclass(frozen=True)
class Answers(Assertion):
    """An ordinary search of one collection succeeds with results from it."""

    collection: str

    def __call__(self, run, registry):
        own = [h for h in run.results if h.collection == self.collection]
        if run.outcome != "success" or run.degradations:
            return Verdict(False, f"outcome {run.outcome}, degraded {run.degradations}")
        if not own:
            return Verdict(False, f"no {self.collection} result: {_listing(run.results)}")
        return Verdict(True, f"{len(own)} results, first {_short(own[0])}")

    def describe(self):
        return f"succeeds, undegraded, with results from {self.collection}"


@dataclass(frozen=True)
class ViaVector(Assertion):
    """The vector path alone finds the passage (the synthesis's open item)."""

    match: Matcher

    def __call__(self, run, registry):
        _resolve(self.match, registry)
        found = [h for h in run.vector if self.match.matches(h, registry)]
        if found:
            return Verdict(True, f"vector path found {_short(found[0])}")
        return Verdict(False, f"not among {len(run.vector)} vector candidates")

    def describe(self):
        return f"vector search alone finds {self.match.describe()}"


@dataclass(frozen=True)
class ExplanationSays(Assertion):
    """The explanation of the first result matching `match` uses words for each of
    `patterns` (regexes, any case). The run asks the explanation model for it."""

    match: Matcher
    patterns: tuple[str, ...]

    def __call__(self, run, registry):
        _resolve(self.match, registry)
        target = next((h for h in run.results if self.match.matches(h, registry)), None)
        if target is None:
            return Verdict(False, f"no result to explain: {_listing(run.results)}")
        text = run.explanations.get(target.id)
        if not text:
            return Verdict(False, f"no explanation for {_short(target)}")
        missing = [p for p in self.patterns if not re.search(p, text, re.IGNORECASE)]
        if missing:
            return Verdict(False, f"explanation lacks {missing}: {text!r}")
        return Verdict(True, f"explanation: {text!r}")

    def describe(self):
        return (f"the explanation of {self.match.describe()} uses words for "
                + " and ".join(f"/{p}/" for p in self.patterns))


@dataclass(frozen=True)
class AllOf(Assertion):
    parts: tuple[Assertion, ...]

    def __call__(self, run, registry):
        verdicts = [part(run, registry) for part in self.parts]
        return Verdict(all(v.ok for v in verdicts),
                       " | ".join(("ok: " if v.ok else "FAIL: ") + v.detail for v in verdicts))

    def describe(self):
        return "; and ".join(part.describe() for part in self.parts)


def all_of(*parts: Assertion) -> Assertion:
    return parts[0] if len(parts) == 1 else AllOf(parts)


# --------------------------------------------------------------------------- SQL expectations

@dataclass(frozen=True)
class AtLeast:
    n: int

    def holds(self, value) -> bool:
        return value is not None and value >= self.n

    def __str__(self) -> str:
        return f"at least {self.n}"


@dataclass(frozen=True)
class Row:
    """The SELECT returns one row whose named columns hold these values."""

    expected: dict

    def __call__(self, rows: list[dict]) -> Verdict:
        if len(rows) != 1:
            return Verdict(False, f"expected one row, got {len(rows)}")
        row = rows[0]
        wrong = []
        for column, want in self.expected.items():
            got = row.get(column)
            ok = want.holds(got) if isinstance(want, AtLeast) else got == want
            if not ok:
                wrong.append(f"{column} = {got!r}, expected {want}")
        shown = ", ".join(f"{k} = {row.get(k)!r}" for k in self.expected)
        return Verdict(not wrong, "; ".join(wrong) if wrong else shown)

    def describe(self) -> str:
        return ", ".join(f"{k} {v}" if isinstance(v, AtLeast) else f"{k} = {v}"
                         for k, v in self.expected.items())


@dataclass(frozen=True)
class CountsBy:
    """The SELECT returns (key, n) rows: exactly the `exact` keys with those counts,
    plus each `at_least` key with at least that many, and no other key."""

    exact: dict[str, int]
    at_least: dict[str, int] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)

    def __call__(self, rows: list[dict]) -> Verdict:
        got = {str(r["key"]): r["n"] for r in rows}
        wrong = []
        for key, n in self.exact.items():
            if got.get(key) != n:
                wrong.append(f"{self.names.get(key, key)}: {got.get(key)}, expected {n}")
        for key, n in self.at_least.items():
            if (got.get(key) or 0) < n:
                wrong.append(f"{self.names.get(key, key)}: {got.get(key)}, expected at least {n}")
        extra = sorted(set(got) - set(self.exact) - set(self.at_least))
        if extra:
            wrong.append(f"unexpected: {', '.join(f'{k} ({got[k]})' for k in extra)}")
        if wrong:
            return Verdict(False, "; ".join(wrong))
        return Verdict(True, ", ".join(f"{self.names.get(k, k)} {got[k]}" for k in got))

    def describe(self) -> str:
        parts = [f"{self.names.get(k, k)} {n}" for k, n in self.exact.items()]
        parts += [f"{self.names.get(k, k)} at least {n}" for k, n in self.at_least.items()]
        return "exactly: " + ", ".join(parts) + "; nothing else"


# 1.4c's passage counts per book, Sirach's prologue included (1.4c "As built").
DEUTEROCANONICAL_PASSAGES = {
    "Tobit": 31, "Judith": 45, "Wisdom": 47, "Sirach": 125, "Baruch": 20,
    "1 Maccabees": 101, "2 Maccabees": 74,
}


def deuterocanonical_pericopes(rows: list[dict]) -> Verdict:
    """Every book is there with its pericopes, each cited by verse range."""
    got = {r["key"]: r for r in rows}
    wrong = []
    for book, n in DEUTEROCANONICAL_PASSAGES.items():
        row = got.get(book) or {"n": 0, "miscited": 0}
        if row["n"] < n:
            wrong.append(f"{book}: {row['n']} passages, expected at least {n}")
        if row["miscited"]:
            wrong.append(f"{book}: {row['miscited']} not cited by verse range")
    if wrong:
        return Verdict(False, "; ".join(wrong))
    return Verdict(True, ", ".join(f"{b} {got[b]['n']}" for b in DEUTEROCANONICAL_PASSAGES))


_SUMMA_PARTS = {"FP": "I", "FS": "I-II", "SS": "II-II", "TP": "III", "XP": "Suppl.",
                "AP1": "Suppl., App. 1", "AP2": "Suppl., App. 2"}
_ARTICLE_ID = re.compile(r"^(FP|FS|SS|TP|XP|AP1|AP2)_Q(\d+)(?:_A(\d+))?")
_CITED = re.compile(
    r"^Summa Theologiae (I|I-II|II-II|III|Suppl\.(?:, App\. \d)?), q\. (\d+), a\. (\d+)"
)


def summa_citations_agree(rows: list[dict]) -> Verdict:
    """C-07: each Summa passage cites the article its text belongs to. A passage's
    article is `metadata.article`, the div it was read from (1.7); its citation must
    name that part, question and article. Prologues carry no article."""
    checked, wrong = 0, []
    for row in rows:
        article = row.get("article")
        if not article:
            continue
        own = _ARTICLE_ID.match(article)
        cited = _CITED.match(row.get("reference") or "")
        checked += 1
        if not own or not cited:
            wrong.append(f"{row.get('reference')!r} ({article})")
            continue
        part, question, number = own.groups()
        if (cited.group(1), cited.group(2), cited.group(3)) != (
            _SUMMA_PARTS[part], question, number or "1"
        ):
            wrong.append(f"{row.get('reference')!r} ({article})")
    if not checked:
        return Verdict(False, "no Summa passage carries its article")
    if wrong:
        return Verdict(False, f"{len(wrong)} of {checked} disagree, e.g. {wrong[:3]}")
    return Verdict(True, f"all {checked} Summa passages cite their own article")


# --------------------------------------------------------------------------- aggregate expectations

def results_of(runs: Iterable[SearchRun]) -> list[Hit]:
    return [h for run in runs if run.error is None for h in run.results]


def every_result(predicate: Callable[[Hit], bool], what: str
                 ) -> Callable[[list[SearchRun]], Verdict]:
    def check(runs: list[SearchRun]) -> Verdict:
        hits = results_of(runs)
        if not hits:
            return Verdict(False, "no search of this run returned a result")
        bad = [h for h in hits if not predicate(h)]
        if bad:
            return Verdict(False, f"{len(bad)} of {len(hits)} fail: {_listing(bad)}")
        return Verdict(True, f"all {len(hits)} results across {len(runs)} searches")
    check.__doc__ = what
    return check


def summa_results_cite_their_article(runs: list[SearchRun]) -> Verdict:
    hits = [h for h in results_of(runs) if h.collection == "summa"]
    if not hits:
        return Verdict(False, "no search of this run returned a Summa result")
    return summa_citations_agree([{"reference": h.reference, "article": h.article}
                                  for h in hits])


summa_results_cite_their_article.__doc__ = (
    "every Summa result's returned citation names the article it is stored under")


# --------------------------------------------------------------------------- checks

@dataclass(frozen=True)
class Check:
    id: str
    items: str          # the cleanup items whose outcome it shows
    proves: str         # what a pass shows Carter, in one sentence

    kind = "check"

    def expectation(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class SearchCheck(Check):
    question: str = ""
    collections: tuple[str, ...] = ()
    expect: Assertion | None = None
    quota: int = QUOTA

    kind = "search"

    def explain_targets(self) -> list[Matcher]:
        parts = self.expect.parts if isinstance(self.expect, AllOf) else (self.expect,)
        return [p.match for p in parts if isinstance(p, ExplanationSays)]

    def expectation(self) -> str:
        return self.expect.describe()


@dataclass(frozen=True)
class KeywordCheck(Check):
    question: str = ""
    collection: str = ""
    expect: Assertion | None = None
    limit: int = 10

    kind = "keyword"

    def expectation(self) -> str:
        return f"keyword search alone {self.expect.describe()}"


@dataclass(frozen=True)
class SqlCheck(Check):
    sql: str = ""
    # Query arguments, or a function of the removal registry that returns them.
    params: tuple | Callable[[Registry], tuple] = ()
    expect: Callable[[list[dict]], Verdict] | None = None
    expect_text: str = ""

    kind = "database"

    def args(self, registry: Registry) -> tuple:
        return self.params(registry) if callable(self.params) else self.params

    def expectation(self) -> str:
        if self.expect_text:
            return self.expect_text
        return self.expect.describe()


@dataclass(frozen=True)
class AggregateCheck(Check):
    expect: Callable[[list[SearchRun]], Verdict] | None = None

    kind = "aggregate"

    def expectation(self) -> str:
        return f"across every search of this run: {self.expect.__doc__}"


@dataclass(frozen=True)
class PlaceholderCheck(Check):
    kind = "placeholder"

    def expectation(self) -> str:
        return "not written yet"


# Document IDs (frozen in datapipeline/registry/works.json; a test holds the titles).
CATECHISM = "9679c400-d314-5394-b916-f6fc27b50104"
CANON_LAW = "aa889573-50b2-5a1d-9264-f309583c0c1b"
SUMMA = "31b2bc0a-0b16-5002-822a-26d3215dd256"
PSALMS = "12ffdbe3-6498-55b7-bef6-afbf368461ea"
NOSTRA_AETATE = "137ada7a-dc69-5a40-9fa1-24469f21dcbb"
LUMEN_GENTIUM = "c1b748c6-a250-5ca1-a087-4f6be5e75bbb"
TRENT = "e33e591b-9e2e-5059-974f-28c8e4ab6aae"
VATICAN_I = "5c3cb0a3-883a-5f43-a747-b5e7196e68e1"
CHALCEDON = "758019ee-d1fe-59c6-97cd-3b9ab03ae8a9"
EPHESUS = "5972a5c6-4f04-5ef0-901d-d9a4a189fc0f"
LATERAN_IV = "49b534a0-0692-5f8c-8ab7-9da0288e4de1"
CONSTANCE = "bfcce97d-adf8-5e3c-8b8f-7e7887a6b205"
EXSURGE_DOMINE = "616dfaea-6099-593e-951f-2b017a7ec938"
SYLLABUS = "6bafb4a7-2d6e-55cc-92b8-cdc221bea175"
INEFFABILIS_DEUS = "a9956e54-3212-501d-96b4-51c14137b8b1"
QUANTA_CURA_1864 = "9b41d623-88c4-5e59-9984-a7134ba900a9"
MIRARI_VOS = "891ae0fa-5a7f-518c-9d1c-9ad4f180bc77"
UBI_LUTETIAM = "ba74d920-a179-5c9e-a1a5-5d677116c82a"
RERUM_NOVARUM = "c5faaf87-76a5-57f0-990f-ab3c646953a7"
FAMILIARIS_CONSORTIO = "335e3467-a3fa-598d-892d-a75664ee4e77"
ORDINATIO_SACERDOTALIS = "638693a3-342c-5614-9c9a-dd6817faf862"
CONFESSIONS = "7f04ae49-2ffe-5cdf-acd9-2b7e8576b441"
INCARNATION = "cf235300-e37d-5a7a-a421-f50efff38355"
OCTAVIUS = "9e93f3ef-cd33-598f-9aac-f2a5886d3e21"
ARCHELAUS = "0e326c02-a623-538c-898b-56623197c955"
CYPRIAN_EPISTLES = "aaf1a0e4-9bf5-5e26-9eaf-8f4f38ff60fe"
TO_HIS_WIFE = "3717ce05-ad42-5ec3-b3ce-ff3964908e05"
APPAREL_OF_WOMEN = "e73bb326-8ba6-5334-b79e-3a15c9892581"
STROMATA = "3a68ef3f-b829-5e95-9eeb-f1ef299c4a38"
INSTRUCTOR = "96584290-90c2-50bc-9d3d-c353b8969e1f"
DIVINE_INSTITUTES = "9e03c96d-8295-5e5e-a4d3-3570ddcf0415"
WORKMANSHIP_OF_GOD = "f913305f-b259-578b-a5ca-532fac927aab"
IGNATIUS_SHORTER_AND_LONGER = (
    "89853cef", "c1bcdc39", "bb72e2f6", "fa2cd483", "995d76f9", "f9e64ef8", "fc317c73",
)
PROSLOGIUM = "c556327d-58ae-5934-ac53-ab8edb93943f"
CUR_DEUS_HOMO = "82d38756-6fba-5af7-9905-fd508a620f38"
VATICAN_II = (
    "c1d5382f-c7c7-564d-989a-89775b36fd58", "1b432ce6-ff64-5a1f-ae2e-a075e67d2b6c",
    "bd4adb5d-500e-5995-ab95-3f61fdc92067", "4451c2f8-e836-58ab-a2eb-495a9cacef89",
    "5f0ff7e9-3b76-5c1f-949f-4980a943244b", "62f7a128-a847-588b-84f0-51d33294b236",
    "6f6474ba-c632-5bdb-a550-b8d5c61797a9", "b4285357-dc78-5c8b-98f1-b50fdf6c83e1",
    LUMEN_GENTIUM, NOSTRA_AETATE,
    "b58729e8-fa6e-5b91-9d66-b0734050a471", "1d8e4438-b930-5fa4-93cb-b393786064fa",
    "88c5b670-accc-5b2a-b936-7b1c205b3ffa", "28f0d5d5-9bf6-531a-862a-0a9ffed7c8ac",
    "29bf3975-5f39-5550-a949-6767cb666695", "13b94869-cf9c-590d-9573-66f1bd6ea457",
)

# 3.1's targets (PR #386), each the documents its removal entries sit on.
ORIGEN = ("5a05852b-4193-518f-9d01-afd796291979", "4c96eac3-f3f1-549c-84cf-070661393073",
          "9c052574-ccbc-5aa6-8a1e-b582b7dd73e4")
TERTULLIAN_SEVEN = (
    "d2b71f9f-111c-5f1b-9a43-5a897b13730c", "e5d235f3-a5f2-513e-90e7-04eedc71bf33",
    "89201a06-a747-53a5-8248-43e5a5cb5fae", "6b70b67f-bfb3-5cda-a2f0-323eff4621bc",
    "01abb5ad-1a95-5435-aa5b-62b04e87e1f2", "d7f29587-bcec-5a71-9633-e635fa8989f5",
    "17b7747f-273b-5841-b415-16dea3192635",
)
NOVATIAN_WORKS = ("0f23bbcf-1d0a-5bf3-849e-05e52a693da8", "2f22d9b5-b1fe-51e0-abf9-56685860ce61",
                  "5d75dc92-df2c-5421-904f-4249590ff48a")
TATIAN = ("356b9c9b-236c-5761-8d85-64a441551944",)
ARNOBIUS = ("85e7153f-b45d-5eb6-9f5b-e87967da6f29",)
ALEXANDER_OF_LYCOPOLIS = ("0d274c4c-d2f3-5e33-92b5-c592422a0bff",)
HIPPOLYTUS = ("c7a1cced-c7f1-57aa-b0ea-da3a99edcc33", "506ebe31-239c-509c-ba5e-b6c822d002df")
GREGORY_THAUMATURGUS = ("685b8763-d3f3-5bb7-bf9f-c34efedaadf5",)
LACTANTIUS_FRAGMENTS = ("8b42a526-e078-56f4-89ab-4a87b995ef3b",)
APOSTOLIC_CONSTITUTIONS = (
    "d72938c6-9f4d-5241-8af8-6feb01ee8dd6", "df17e279-df63-5610-95ae-f61e2fe09916",
    "df6fd2f7-c573-5486-9f76-739ba3aa947d", "aab0848e-3b88-5a1c-9dbd-a6897abf4e79",
    "49437294-5526-5a1b-b2df-3022c0c36e56", "f04e045b-64f1-57c1-bb8f-7d308e5d7c26",
    "fd6550b9-0122-5f2e-86ff-cb992d719a9e", "10d8d7c6-680c-5739-bc98-6ce557371f25",
)
FORGED_IGNATIUS = (
    "7073bae0-a0fd-5c22-8e36-8cf493f15af2", "4fe41814-a29f-572d-badb-e3f3b2488125",
    "56add0dd-d428-5843-9a61-23e8c255338f", "567be8a5-1eba-5a86-a5ce-688e2e2aab23",
    "0311d705-6fd6-5801-bb7a-33116ae11e0e", "5553da19-6597-56e0-ad6e-48113b7d855f",
)
SECTIONAL_CONFESSION = ("44fd52c3-fdef-518e-a463-a3273f39764c",)
PFAFF_FRAGMENTS = ("0066869a-28fb-5274-a847-c4d3e88a948e",)
MEDIEVAL_IGNATIUS = (
    "76b8b853-70d2-5821-8ee5-0149e4f59e03", "63e7f0b7-2b47-50d4-b7a8-9db26b5dca87",
    "830a2c63-f968-5861-9a10-c1ee3c6ee79d", "1a0a016b-395e-5307-9aea-19a896b87eae",
)
BOOK_VIII = "10d8d7c6-680c-5739-bc98-6ce557371f25"

# A passage users can find: searchable, and neither it nor its document retired.
VISIBLE = "c.searchable AND c.retired_at IS NULL AND d.retired_at IS NULL"

_REMOVED_SQL = f"""
    SELECT (SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE (c.document_id = ANY($1::uuid[]) OR c.id = ANY($2::uuid[]))
              AND {VISIBLE}) AS visible,
           (SELECT count(*) FROM documents d
            WHERE d.id = ANY($1::uuid[]) AND d.retired_at IS NULL) AS live_documents
"""

_KEPT_SQL = f"""
    SELECT d.id::text AS key, count(c.id) FILTER (WHERE {VISIBLE}) AS n
    FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
    WHERE d.id = ANY($1::uuid[]) GROUP BY d.id
"""


def removal_check(id: str, items: str, proves: str, added_by: str | tuple[str, ...],
                  documents: Sequence[str] = (), reason: str | None = None) -> SqlCheck:
    """No passage the item's removal entries name is visible, and no document they
    retire whole is live. On staging the staged corpus simply leaves them out."""
    def params(registry: Registry) -> tuple:
        docs, passages = registry.removed(added_by, reason, documents)
        return sorted(docs), sorted(passages)

    return SqlCheck(
        id=id, items=items, proves=proves, sql=_REMOVED_SQL, params=params,
        expect=Row({"visible": 0, "live_documents": 0}),
    )


def kept_check(id: str, items: str, proves: str, documents: dict[str, int]) -> SqlCheck:
    """Each document stays, with at least the given number of visible passages."""
    return SqlCheck(
        id=id, items=items, proves=proves, sql=_KEPT_SQL, params=(sorted(documents),),
        expect=CountsBy({}, at_least=documents),
    )


# Words that say a position is rejected rather than taught. Not "argues" or "answers":
# an explanation can use them while presenting the position as the author's own.
REJECTED_WORDS = r"condemn|reject|refut|objection|error|heres"

ORDINARY = {
    "bible": "What does Scripture say about caring for widows and orphans?",
    "catechism": "What is prayer, and why should Christians pray?",
    "church-fathers": "How did the early Christians understand baptism?",
    "councils": "What have the councils taught about the Holy Spirit?",
    "encyclicals": "What do the popes teach about the rights of workers?",
    "apostolic-exhortations": "What do the popes say about family life?",
    "papal-documents": "What have the popes written about suffering?",
    "canon-law": "What does canon law require before a marriage can be celebrated?",
    "summa": "Is it ever lawful to tell a lie?",
    "medieval": "How should a Christian love God?",
}

# A reference-style question per collection, and the passage it names.
REFERENCES: dict[str, tuple[str, Match]] = {
    "bible": ("Psalm 23", Match(reference=r"^Psalms 23:")),
    "catechism": ("CCC 1471", Match(document=CATECHISM, anchor="ccc/1471")),
    "canon-law": ("canon 1055", Match(document=CANON_LAW, anchor="can/1055")),
    "summa": ("Summa Theologiae I, question 2, article 3",
              Match(document=SUMMA, anchor="summa/FP_Q2_A3")),
    "councils": ("Lumen Gentium 25", Match(document=LUMEN_GENTIUM, anchor="lumen-gentium/25")),
    "encyclicals": ("Rerum Novarum 20",
                    Match(document=RERUM_NOVARUM, anchor="rerum-novarum/20")),
    "apostolic-exhortations": (
        "Familiaris Consortio 11",
        Match(document=FAMILIARIS_CONSORTIO, anchor="familiaris-consortio/11"),
    ),
    "papal-documents": (
        "Ordinatio Sacerdotalis 4",
        Match(document=ORDINATIO_SACERDOTALIS, anchor="ordinatio-sacerdotalis/4"),
    ),
    "church-fathers": ("Augustine, Confessions, Book X, chapter 27",
                       Match(document=CONFESSIONS, anchor="xi.xxvii")),
    "medieval": ("Anselm, Proslogium, chapter 2",
                 Match(document=PROSLOGIUM, anchor="iii.iii")),
}

SEARCH_VECTOR_EXPRESSION = r"""
    setweight(to_tsvector('english',
              regexp_replace(content, '\{\{v:\d+\}\}', ' ', 'g')), 'A')
    || setweight(to_tsvector('english',
              regexp_replace(coalesce(reference, ''), '[§:;,.()–—-]', ' ', 'g')), 'B')
"""

CHECKS: list[Check] = [
    # ---- 4.2's targeted checks (the spec's list) ----------------------------------
    SearchCheck(
        id="4.2.nostra-aetate-4", items="4.2, 1.1",
        proves="Vatican II's sections are whole again: Nostra Aetate 4's passage on the "
               "Jews and the Passion, lost before, is found by a plain question.",
        question="What did the Second Vatican Council say about whether the Jewish people "
                 "are responsible for the death of Christ?",
        collections=("councils",),
        expect=Some(Match(document=NOSTRA_AETATE, anchor="nostra-aetate/4",
                          text="cannot be charged against all the Jews")),
    ),
    SearchCheck(
        id="4.2.trent-justification", items="4.2, 1.2b",
        proves="Trent is rebuilt from the whole Waterworth text, and its decree on "
               "justification is found.",
        question="What did the Council of Trent teach about how a sinner is justified?",
        collections=("councils",),
        expect=Some(Match(document=TRENT, anchor="council-of-trent/session-6")),
    ),
    SearchCheck(
        id="4.2.vatican-i-infallibility", items="4.2, 1.2d",
        proves="Vatican I's Pastor Aeternus, from Schaff, answers a question on papal "
               "infallibility.",
        question="When does the pope teach infallibly, according to the First Vatican Council?",
        collections=("councils",),
        expect=Some(Match(document=VATICAN_I,
                          anchor="first-vatican-council/pastor-aeternus/chapter-4")),
    ),
    SearchCheck(
        id="4.2.vatican-i-faith-reason", items="4.2, 1.2d",
        proves="Vatican I's Dei Filius, from Schaff, answers a question on faith and reason.",
        question="What did the First Vatican Council teach about faith and reason?",
        collections=("councils",),
        expect=Some(Match(document=VATICAN_I, anchor="first-vatican-council/dei-filius")),
    ),
    SearchCheck(
        id="4.2.ccc-2267", items="4.2, 1.6, #279",
        proves="The Catechism answers on the death penalty with the 2018 text, and the "
               "1997 text, kept as history, never appears in search.",
        question="What does the Catechism teach about the death penalty?",
        collections=("catechism",),
        expect=all_of(
            Some(Match(document=CATECHISM, reference=r"2267", text="inadmissible")),
            NoneOf(Match(text="practically non-existent", what="the 1997 text of §2267")),
        ),
    ),
    SqlCheck(
        id="4.2.ccc-2267-history", items="4.2, 1.6",
        proves="The 1997 text of §2267 is stored as a history passage that search skips.",
        sql="""
            SELECT count(*) AS stored, count(*) FILTER (WHERE c.searchable) AS searchable
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND c.anchor = 'ccc/2263/history-1997'
              AND c.retired_at IS NULL AND d.retired_at IS NULL
        """,
        params=(CATECHISM,),
        expect=Row({"stored": 1, "searchable": 0}),
    ),
    SearchCheck(
        id="4.2.canon-112", items="4.2, 1.5a, 1.5b, 2.4f",
        proves="\"Canon 112\" returns canon 112 first, on its own card (not glued to the "
               "next canon), labelled as an unofficial English translation.",
        question="canon 112",
        collections=("canon-law",),
        expect=all_of(
            First(Match(document=CANON_LAW, anchor="can/112",
                        text_status="unofficial_english")),
            NoneOf(Match(anchor="can/112", text="Can. 113",
                         what="a canon 112 card holding canon 113")),
        ),
    ),
    SearchCheck(
        id="4.2.susanna", items="4.2, 1.4a",
        proves="Susanna (Daniel 13) is published and found.",
        question="What happened to Susanna when the two elders accused her?",
        collections=("bible",),
        expect=Some(Match(reference=r"^Daniel 13:")),
    ),
    SearchCheck(
        id="4.2.bel-and-the-dragon", items="4.2, 1.4a",
        proves="Bel and the Dragon (Daniel 14) is published and found.",
        question="How did Daniel show that the idol Bel did not really eat the offerings?",
        collections=("bible",),
        expect=Some(Match(reference=r"^Daniel 14:")),
    ),
    AggregateCheck(
        id="4.2.no-short-results", items="4.2",
        proves="No search returns a stub card.",
        expect=every_result(lambda h: len(h.content) >= 20,
                            "every result has 20 or more characters"),
    ),
    SqlCheck(
        id="4.2.no-short-passages", items="4.2",
        proves="No searchable passage anywhere in the corpus is a stub under 20 characters.",
        sql=f"""
            SELECT count(*) AS short FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE {VISIBLE} AND char_length(btrim(c.content)) < 20
        """,
        expect=Row({"short": 0}),
    ),
    SqlCheck(
        id="4.2.vatican-ii-no-note-cards", items="4.2, 1.1",
        proves="Vatican II's footnotes are no longer cards: no searchable passage of the "
               "16 documents opens with \"Cf.\" or \"See\".",
        sql=f"""
            SELECT count(*) AS note_cards FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = ANY($1::uuid[]) AND {VISIBLE}
              AND c.content ~ '^\\s*(Cf\\.|See )'
        """,
        params=(list(VATICAN_II),),
        expect=Row({"note_cards": 0}),
    ),
    AggregateCheck(
        id="4.2.results-searchable", items="4.2, 2.2b",
        proves="No search returns a passage that is not searchable, retired, or missing "
               "from the corpus.",
        expect=every_result(lambda h: h.found and h.searchable and not h.retired,
                            "every result is a searchable, live passage the corpus holds"),
    ),
    AggregateCheck(
        id="4.2.summa-results-cite-their-article", items="1.7, C-07",
        proves="Every Summa passage a search returns cites the article its text belongs "
               "to, as the search returned it.",
        expect=summa_results_cite_their_article,
    ),
    AggregateCheck(
        id="4.2.vatican-ii-results-not-notes", items="4.2, 1.1",
        proves="No search returns a Vatican II card that opens with \"Cf.\" or \"See\".",
        expect=every_result(
            lambda h: h.document_id not in VATICAN_II
            or not re.match(r"\s*(Cf\.|See )", h.content),
            "no Vatican II result opens with \"Cf.\" or \"See\"",
        ),
    ),
    SearchCheck(
        id="4.2.indulgence", items="4.2, C-03",
        proves="\"What is an indulgence?\" finds the Catechism's definition, §1471.",
        question="What is an indulgence?",
        collections=("catechism",),
        expect=Some(Match(document=CATECHISM, anchor="ccc/1471")),
    ),
    SqlCheck(
        id="4.2.psalm-51-title", items="4.2, 1.4a, C-11",
        proves="Psalm 51's first passage opens with the psalm's title.",
        sql=f"""
            SELECT count(*) AS with_title FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND c.anchor = 'psalms/51/1' AND {VISIBLE}
              AND c.content LIKE 'For the Chief Musician. A Psalm by David, when Nathan%'
        """,
        params=(PSALMS,),
        expect=Row({"with_title": 1}),
    ),
    KeywordCheck(
        id="2.2c.keyword-canon-1055", items="2.2c, C-16",
        proves="Keyword search finds a canon by its citation.",
        question="canon 1055", collection="canon-law",
        expect=First(Match(document=CANON_LAW, anchor="can/1055")),
    ),
    KeywordCheck(
        id="2.2c.keyword-ccc-2267", items="2.2c, C-16",
        proves="Keyword search finds the Catechism passage holding a paragraph number.",
        question="ccc 2267", collection="catechism",
        expect=First(Match(document=CATECHISM, anchor="ccc/2263")),
    ),
    KeywordCheck(
        id="2.2c.keyword-john-3", items="2.2c, C-16",
        proves="Keyword search finds a Bible chapter by its citation, and verse markers "
               "no longer match as words.",
        question="john 3", collection="bible", limit=6,
        expect=Some(Match(reference=r"^John 3:")),
    ),
    SqlCheck(
        id="2.2c.search-vector-rebuilt", items="2.2c, 4.0",
        proves="Every passage's keyword index uses 2.2c's definition (no verse markers, "
               "the citation added).",
        sql=f"SELECT count(*) AS stale FROM chunks WHERE search_vector IS DISTINCT FROM "
            f"({SEARCH_VECTOR_EXPRESSION})",
        expect=Row({"stale": 0}),
    ),
    SqlCheck(
        id="1.7.summa-citations", items="1.7, C-07",
        proves="No Summa passage cites an article its text does not belong to.",
        sql=f"""
            SELECT c.reference, c.metadata->>'article' AS article
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND {VISIBLE}
        """,
        params=(SUMMA,),
        expect=summa_citations_agree,
        expect_text="every passage's citation names the part, question and article "
                    "its text was read from",
    ),
    SqlCheck(
        id="1.8c.firmilian-credited", items="1.8c, C-02",
        proves="Firmilian's letter in Cyprian's Epistles is credited to Firmilian, not "
               "Cyprian.",
        sql=f"""
            SELECT count(*) AS passages,
                   count(*) FILTER (WHERE COALESCE(w.author, d.author, '') NOT ILIKE '%Firmilian%')
                       AS credited_otherwise
            FROM chunks c JOIN documents d ON d.id = c.document_id
            LEFT JOIN document_works w
                   ON w.document_id = c.document_id AND w.work_key = c.work_key
            WHERE c.document_id = $1 AND c.anchor LIKE 'iv.iv.lxxiv%' AND {VISIBLE}
        """,
        params=(CYPRIAN_EPISTLES,),
        expect=Row({"passages": AtLeast(1), "credited_otherwise": 0}),
    ),
    SearchCheck(
        id="1.8c.firmilian-search", items="1.8c, C-02",
        proves="A search that finds Firmilian's letter shows Firmilian as its author.",
        question="What did the bishop of Caesarea in Cappadocia write to Cyprian about "
                 "baptism given by heretics?",
        collections=("church-fathers",),
        expect=all_of(
            Some(Match(document=CYPRIAN_EPISTLES, anchor="iv.iv.lxxiv", author="Firmilian")),
            NoneOf(Match(document=CYPRIAN_EPISTLES, anchor="iv.iv.lxxiv", author=r"^Cyprian",
                         what="a card of Firmilian's letter credited to Cyprian")),
        ),
    ),

    # ---- 3.1: whole works and passages removed under rules A to C ------------------
    removal_check("3.1.origen", "3.1",
                  "Origen's three works are gone (condemned by name, Constantinople II).",
                  "3.1", ORIGEN),
    removal_check("3.1.tertullian-seven-works", "3.1",
                  "Tertullian's seven excluded works are gone (De Fuga, Exhortation to "
                  "Chastity, On Fasting, On Modesty, On Monogamy, On the Pallium, On the "
                  "Veiling of Virgins).",
                  "3.1", TERTULLIAN_SEVEN),
    removal_check("3.1.novatian-works", "3.1",
                  "Novatian's On the Trinity and On the Jewish Meats, and Treatises I and "
                  "III among the Treatises Attributed to Cyprian, are gone.",
                  "3.1", NOVATIAN_WORKS),
    removal_check("3.1.novatian-letters", "3.1, C-02",
                  "Epistles XXV, XXIX and XXX in Cyprian's Epistles, Novatian's, are gone.",
                  "3.1", (CYPRIAN_EPISTLES,)),
    removal_check("3.1.tatian", "3.1", "Tatian's Address to the Greeks is gone.",
                  "3.1", TATIAN),
    removal_check("3.1.arnobius", "3.1", "Arnobius's Against the Heathen is gone.",
                  "3.1", ARNOBIUS),
    removal_check("3.1.alexander-of-lycopolis", "3.1",
                  "Alexander of Lycopolis's Of the Manichaeans is gone.",
                  "3.1", ALEXANDER_OF_LYCOPOLIS),
    removal_check("3.1.hippolytus", "3.1",
                  "Hippolytus's Refutation of All Heresies and his undatable works are gone.",
                  "3.1", HIPPOLYTUS),
    removal_check("3.1.panegyric-to-origen", "3.1",
                  "Gregory Thaumaturgus's Panegyric to Origen is gone.",
                  "3.1", GREGORY_THAUMATURGUS),
    removal_check("3.1.phoenix", "3.1", "Lactantius's The Phoenix is gone.",
                  "3.1", LACTANTIUS_FRAGMENTS),
    removal_check("3.1.apostolic-constitutions", "3.1",
                  "The Apostolic Constitutions are gone, all but Book VIII's canons.",
                  "3.1", APOSTOLIC_CONSTITUTIONS),
    removal_check("3.1.forged-ignatius", "3.1", "The six forged Ignatius letters are gone.",
                  "3.1", FORGED_IGNATIUS),
    removal_check("3.1.sectional-confession", "3.1",
                  "The Sectional Confession of Faith (Apollinaris) is gone.",
                  "3.1", SECTIONAL_CONFESSION),
    removal_check("3.1.pfaff-fragments", "3.1",
                  "The forged Pfaff fragments of Irenaeus (XXXVI to XXXIX) are gone.",
                  "3.1", PFAFF_FRAGMENTS),
    removal_check("3.1.medieval-ignatius", "3.1",
                  "The four medieval Latin Ignatius letters are gone.",
                  "3.1", MEDIEVAL_IGNATIUS),
    kept_check("3.1.kept-works", "3.1, R1",
               "What 3.1 keeps is still there: To His Wife, On the Apparel of Women, Book "
               "VIII's canons, Treatises II and IV, and Hippolytus's other works.",
               {TO_HIS_WIFE: 1, APPAREL_OF_WOMEN: 1, BOOK_VIII: 6, NOVATIAN_WORKS[2]: 1,
                HIPPOLYTUS[1]: 1}),
    SearchCheck(
        id="3.1.search-against-celsus", items="3.1, 4.2",
        proves="A question Origen's Against Celsus used to answer returns none of the "
               "removed works.",
        question="How did early Christians answer the charge that Jesus worked his "
                 "miracles by sorcery?",
        collections=("church-fathers",),
        expect=NoneOf(Removed("3.1", what="a passage of a work 3.1 removes")),
    ),
    SearchCheck(
        id="3.1.search-flight-in-persecution", items="3.1, 4.2",
        proves="A question on fleeing persecution, the subject of Tertullian's De Fuga, "
               "returns none of the removed works.",
        question="May a Christian flee to escape persecution?",
        collections=("church-fathers",),
        expect=NoneOf(Removed("3.1", what="a passage of a work 3.1 removes")),
    ),
    SearchCheck(
        id="3.1.search-naassenes", items="3.1, 4.2",
        proves="A question only Hippolytus's Refutation answered returns none of it.",
        question="What did the Naassenes teach about the serpent?",
        collections=("church-fathers",),
        expect=NoneOf(Removed("3.1", HIPPOLYTUS, what="a passage of Hippolytus that 3.1 removes")),
    ),
    SearchCheck(
        id="3.1.search-roman-clergy-letters", items="3.1, 4.2, C-02",
        proves="A question on the Roman clergy's letters to Cyprian returns none of "
               "Novatian's letters (Epistles XXV, XXIX, XXX).",
        question="What did the clergy of Rome write to Cyprian about the lapsed during "
                 "the persecution?",
        collections=("church-fathers",),
        expect=NoneOf(Removed("3.1", (CYPRIAN_EPISTLES,), what="a letter of Novatian's")),
    ),
    SearchCheck(
        id="3.1.search-to-his-wife", items="3.1, R1",
        proves="Tertullian's To His Wife, which R1 keeps, is still found.",
        question="What did Tertullian advise his wife about marrying again after his death?",
        collections=("church-fathers",),
        expect=Some(Match(document=TO_HIS_WIFE)),
    ),
    SearchCheck(
        id="3.1.search-apparel-of-women", items="3.1, R1",
        proves="Tertullian's On the Apparel of Women, which R1 keeps, is still found.",
        question="What did Tertullian say about how Christian women should dress?",
        collections=("church-fathers",),
        expect=Some(Match(document=APPAREL_OF_WOMEN)),
    ),

    # ---- 3.3: non-English passages --------------------------------------------------
    removal_check("3.3.ubi-lutetiam", "3.3",
                  "Ubi Lutetiam, which has only the Italian, is gone.",
                  "3.3", (UBI_LUTETIAM,)),
    removal_check("3.3.latin-passages", "3.3",
                  "The 45 passages the ANF translators left in Latin (Stromata III, "
                  "Instructor II.10, Divine Institutes VI.23, Workmanship 12) are gone.",
                  "3.3", (STROMATA, INSTRUCTOR, DIVINE_INSTITUTES, WORKMANSHIP_OF_GOD)),
    SqlCheck(
        id="3.3.omission-notes", items="3.3",
        proves="The four Fathers works that lose Latin passages carry the omission note.",
        sql="""
            SELECT id::text AS key,
                   (notes ILIKE '%no public-domain English translation exists%')::int AS n
            FROM documents WHERE id = ANY($1::uuid[]) AND retired_at IS NULL
        """,
        params=([STROMATA, INSTRUCTOR, DIVINE_INSTITUTES, WORKMANSHIP_OF_GOD],),
        expect=CountsBy({STROMATA: 1, INSTRUCTOR: 1, DIVINE_INSTITUTES: 1,
                         WORKMANSHIP_OF_GOD: 1},
                        names={STROMATA: "Stromata", INSTRUCTOR: "Instructor",
                               DIVINE_INSTITUTES: "Divine Institutes",
                               WORKMANSHIP_OF_GOD: "Workmanship of God"}),
    ),
    SearchCheck(
        id="3.3.search-stromata-iii", items="3.3",
        proves="A question on Stromata III returns none of its Latin passages.",
        question="What did Clement of Alexandria teach about marriage and continence?",
        collections=("church-fathers",),
        expect=NoneOf(Removed("3.3", what="a Latin passage 3.3 removes")),
    ),
    SearchCheck(
        id="3.3.search-ubi-lutetiam", items="3.3",
        proves="A question on Pius VI and revolutionary France returns no Italian text.",
        question="What did Pope Pius VI write about the Church in France during the "
                 "Revolution?",
        collections=("encyclicals",),
        expect=NoneOf(Match(document=UBI_LUTETIAM, what="a passage of Ubi Lutetiam")),
    ),

    # ---- 1.3d: older papal documents ------------------------------------------------
    removal_check("1.3d.held-documents", "1.3d, ADR 0001",
                  "The 51 papal documents held for permission, and the 84 paragraphs the "
                  "printings lack, are not shown.",
                  "1.3d", reason="awaiting-permission"),
    SearchCheck(
        id="1.3d.search-held", items="1.3d",
        proves="A question a held document answered (Benedict XIV on church music) "
               "returns none of the held text.",
        question="What did Pope Benedict XIV write about music and singing in churches?",
        collections=("encyclicals",),
        expect=NoneOf(Removed("1.3d", reason="awaiting-permission",
                              what="held papal text")),
    ),
    SearchCheck(
        id="1.3d.ineffabilis-deus", items="1.3d, 2.4f",
        proves="Ineffabilis Deus is the 1855 printing, labelled as text from a scanned "
               "edition.",
        question="How did Pius IX define the Immaculate Conception of Mary?",
        collections=("encyclicals",),
        expect=Some(Match(document=INEFFABILIS_DEUS, text_source="ocr")),
    ),
    SearchCheck(
        id="1.3d.mirari-vos", items="1.3d",
        proves="Mirari Vos, rebuilt from its 1833 printing, is found.",
        question="What did Gregory XVI teach about indifferentism and liberty of conscience?",
        collections=("encyclicals",),
        expect=Some(Match(document=MIRARI_VOS)),
    ),
    SqlCheck(
        id="1.3d.quanta-cura-restored", items="1.3d",
        proves="Quanta Cura (1864) holds the words the site's copy had lost (§1's "
               "eye-skip, restored from the Dublin Review).",
        sql=f"""
            SELECT count(*) AS restored FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND {VISIBLE}
              AND c.content LIKE '%vindicators of the august catholic religion%'
        """,
        params=(QUANTA_CURA_1864,),
        expect=Row({"restored": 1}),
    ),

    # ---- 1.5b: canon law ------------------------------------------------------------
    SqlCheck(
        id="1.5b.unofficial-english", items="1.5b, 2.4f",
        proves="The nine canons in L'Osservatore Romano's English carry the unofficial-"
               "English label and a link to the Latin.",
        sql=f"""
            SELECT count(*) AS labelled FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND {VISIBLE}
              AND c.anchor = ANY($2::text[])
              AND c.metadata->>'text_status' = 'unofficial_english'
              AND c.metadata->>'official_latin_url' LIKE 'https://www.vatican.va/%'
        """,
        params=(CANON_LAW, ["can/111", "can/112", "can/535", "can/1108", "can/1109",
                            "can/1111", "can/1112", "can/1116", "can/1127"]),
        expect=Row({"labelled": 9}),
    ),
    removal_check("1.5b.retired-canons", "1.5b",
                  "Canons 295, 296, 579, 695, 700 and 868, whose current text has no "
                  "English, are not shown.",
                  "1.5b"),
    SqlCheck(
        id="1.5b.latin-links", items="1.5b, 2.4f",
        proves="The Code records a Latin link for each canon not shown, which its removal "
               "notice opens.",
        sql="""
            SELECT count(*) AS links FROM documents d,
                   jsonb_object_keys(d.metadata->'official_latin_urls') AS k
            WHERE d.id = $1 AND k = ANY($2::text[])
        """,
        params=(CANON_LAW, ["can/295", "can/296", "can/579", "can/695", "can/700",
                            "can/868"]),
        expect=Row({"links": 6}),
    ),
    SearchCheck(
        id="1.5b.search-personal-prelatures", items="1.5b",
        proves="A question on personal prelatures returns no canon 295 or 296 text.",
        question="What does canon law say about personal prelatures?",
        collections=("canon-law",),
        expect=NoneOf(Removed("1.5b", what="a canon 1.5b withholds")),
    ),

    # ---- 1.7: Summa -----------------------------------------------------------------
    SearchCheck(
        id="1.7.q71", items="1.7",
        proves="Prima Pars q. 71, lost by the old splitter, is found.",
        question="What does Aquinas say about the creation of fish and birds on the fifth day?",
        collections=("summa",),
        expect=Some(Match(document=SUMMA, reference=r"^Summa Theologiae I, q\. 71,")),
    ),
    SearchCheck(
        id="1.7.q72", items="1.7",
        proves="Prima Pars q. 72, lost by the old splitter, is found.",
        question="What does Aquinas say about the creation of land animals on the sixth day?",
        collections=("summa",),
        expect=Some(Match(document=SUMMA, reference=r"^Summa Theologiae I, q\. 72,")),
    ),
    SqlCheck(
        id="1.7.question-prologues", items="1.7",
        proves="Aquinas's question prologues are passages, cited as prologues.",
        sql=f"""
            SELECT count(*) AS prologues FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND {VISIBLE}
              AND c.unit_label ~ '^Question \\d+, prologue$'
              AND c.reference ~ ', q\\. \\d+, prologue$'
        """,
        params=(SUMMA,),
        expect=Row({"prologues": AtLeast(611)}),
    ),

    # ---- 3.4 and 2.4d: rejected voices ------------------------------------------------
    SqlCheck(
        id="3.4.rejected-voice-ranges", items="3.4, 1.7",
        proves="Exactly 3.4's passages, and the Summa's objections, carry the rejected "
               "role.",
        sql=f"""
            SELECT c.document_id::text AS key, count(*) AS n
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.voice = 'rejected' AND {VISIBLE}
            GROUP BY c.document_id
        """,
        expect=CountsBy(
            {EXSURGE_DOMINE: 41, SYLLABUS: 80, CONSTANCE: 4, EPHESUS: 4, OCTAVIUS: 10,
             ARCHELAUS: 11},
            at_least={SUMMA: 10_000},
            names={EXSURGE_DOMINE: "Exsurge Domine", SYLLABUS: "Syllabus",
                   CONSTANCE: "Constance", EPHESUS: "Ephesus", OCTAVIUS: "Octavius",
                   ARCHELAUS: "Acts of Archelaus", SUMMA: "Summa"},
        ),
    ),
    SearchCheck(
        id="2.4d.exsurge-domine-31", items="2.4d, 3.4, 1.3d",
        proves="Luther's condemned proposition is found with its label, and its "
               "explanation says Leo X condemned it.",
        question="Does the just man sin in every good work?",
        collections=("papal-documents",),
        expect=all_of(
            Some(Match(document=EXSURGE_DOMINE, anchor="exsurge-domine/31", voice="rejected",
                       label=r"^Condemned proposition 31 of Martin Luther")),
            ExplanationSays(Match(document=EXSURGE_DOMINE, anchor="exsurge-domine/31"),
                            (r"condemn|reject", r"Leo")),
        ),
    ),
    SearchCheck(
        id="2.4d.summa-objection", items="2.4d, 1.7",
        proves="A Summa objection's explanation says it is a position Aquinas answers, "
               "not his teaching.",
        question="Is the existence of evil an argument against the existence of God?",
        collections=("summa",),
        expect=all_of(
            Some(Match(document=SUMMA, voice="rejected")),
            ExplanationSays(Match(document=SUMMA, voice="rejected"), (REJECTED_WORDS,)),
        ),
    ),
    SearchCheck(
        id="2.4d.caecilius", items="2.4d, 3.4",
        proves="Caecilius's speech in the Octavius is found labelled as a pagan objection, "
               "and its explanation says so.",
        question="What arguments against divine providence are made in the Octavius of "
                 "Minucius Felix?",
        collections=("church-fathers",),
        expect=all_of(
            Some(Match(document=OCTAVIUS, voice="rejected", label=r"^Caecilius, pagan")),
            ExplanationSays(Match(document=OCTAVIUS, voice="rejected"),
                            (r"Caecilius|pagan", REJECTED_WORDS)),
        ),
    ),
    SearchCheck(
        id="3.4.syllabus", items="3.4, 1.3d",
        proves="The Syllabus's propositions are found labelled as condemned.",
        question="Did Pius IX condemn the view that a person may choose any religion "
                 "they judge true by reason?",
        collections=("encyclicals",),
        expect=Some(Match(document=SYLLABUS, voice="rejected",
                          label=r"^Condemned proposition \d+ \(condemned by Pius IX")),
    ),
    SearchCheck(
        id="3.4.wyclif", items="3.4, 1.2e",
        proves="Wyclif's articles at Constance, from Deferrari, are found labelled as "
               "condemned.",
        question="Which teachings of John Wyclif did the Council of Constance condemn?",
        collections=("councils",),
        expect=Some(Match(document=CONSTANCE, voice="rejected",
                          label=r"^Condemned articles of John Wyclif")),
    ),
    SearchCheck(
        id="3.4.nestorius", items="3.4, 1.2c",
        proves="Nestorius's letter at Ephesus is found labelled as condemned.",
        question="What did Nestorius write to Cyril about calling Mary the Mother of God?",
        collections=("councils",),
        expect=Some(Match(document=EPHESUS, voice="rejected",
                          label=r"^Letter of Nestorius, condemned")),
    ),
    SearchCheck(
        id="3.4.mani", items="3.4",
        proves="Mani's teaching in the Acts of Archelaus is found labelled as refuted.",
        question="What did Mani teach about the two principles of good and evil?",
        collections=("church-fathers",),
        expect=Some(Match(document=ARCHELAUS, voice="rejected", label=r"^Mani's teaching")),
    ),

    # ---- 2.4f: passage text labels ----------------------------------------------------
    SearchCheck(
        id="2.4f.lateran-iv-scanned", items="2.4f, 1.2e",
        proves="Lateran IV's canons, from Schroeder's scan, are found and labelled as "
               "text from a scanned edition.",
        question="What did the Fourth Lateran Council require about confessing sins once "
                 "a year?",
        collections=("councils",),
        expect=Some(Match(document=LATERAN_IV, anchor="fourth-lateran-council/canon/21",
                          text_source="ocr")),
    ),
    SqlCheck(
        id="2.4f.scanned-label-counts", items="2.4f, 1.2e, 1.3d",
        proves="Scanned text is labelled in every collection that holds it.",
        sql=f"""
            SELECT d.collection AS key, count(*) AS n
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.metadata->>'text_source' = 'ocr' AND {VISIBLE}
            GROUP BY d.collection
        """,
        expect=CountsBy({}, at_least={"councils": 300, "encyclicals": 400,
                                      "apostolic-exhortations": 150, "papal-documents": 1}),
    ),

    # ---- the other items since the spec was written -------------------------------------
    SearchCheck(
        id="1.2c.chalcedon", items="1.2c",
        proves="Chalcedon's Definition, now Percival's text, is found.",
        question="How did the Council of Chalcedon define the two natures of Christ?",
        collections=("councils",),
        expect=Some(Match(document=CHALCEDON, anchor="council-of-chalcedon/definition")),
    ),
    SearchCheck(
        id="1.4b.joel-numbering", items="1.4b, #317",
        proves="Joel uses the Church's chapter numbers: \"I will pour out my spirit\" is "
               "Joel 3:1, not 2:28.",
        question="Where does Scripture say God will pour out his spirit on all flesh?",
        collections=("bible",),
        expect=Some(Match(reference=r"^Joel 3:1", text="pour out my Spirit")),
    ),
    SqlCheck(
        id="1.4b.daniel-hosea-numbering", items="1.4b, #317",
        proves="Daniel and Hosea follow the Church's numbers where they differ from "
               "WEB-C's (Daniel 6:1 is Darius's verse; Hosea 14:2 opens the call to return).",
        sql=f"""
            SELECT count(*) FILTER (WHERE c.reference LIKE 'Daniel 6:1–%'
                                      AND c.content LIKE 'Darius the Mede%') AS daniel,
                   count(*) FILTER (WHERE c.reference LIKE 'Hosea 14:2–%'
                                      AND c.content LIKE 'Israel, return to the LORD%') AS hosea
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE d.collection = 'bible' AND {VISIBLE}
        """,
        expect=Row({"daniel": 1, "hosea": 1}),
    ),
    SqlCheck(
        id="1.4a.book-names-and-prologue", items="1.4a",
        proves="The Song of Songs carries its Catholic name and Sirach's prologue is a "
               "passage.",
        sql=f"""
            SELECT (SELECT count(*) FROM documents d
                    WHERE d.collection = 'bible' AND d.title = 'Song of Songs'
                      AND d.retired_at IS NULL) AS song_of_songs,
                   (SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id
                    WHERE c.anchor = 'sirach/prologue' AND {VISIBLE}) AS sirach_prologue
        """,
        expect=Row({"song_of_songs": 1, "sirach_prologue": 1}),
    ),
    SqlCheck(
        id="1.4c.deuterocanonical-pericopes", items="1.4c",
        proves="The seven deuterocanonical books are in pericopes (as many as 1.4c built), "
               "each cited by verse range, never a bare chapter.",
        sql=f"""
            SELECT b.book AS key, count(c.id) AS n,
                   count(c.id) FILTER (WHERE coalesce(c.reference, '') <> 'Sirach, Prologue'
                       AND coalesce(c.reference, '') !~ ('^' || b.book
                           || ' \\d+:\\d+(–(\\d+:)?\\d+)?( \\(part \\d+ of \\d+\\))?$'))
                       AS miscited
            FROM unnest($1::text[]) AS b(book)
            LEFT JOIN documents d ON d.collection = 'bible' AND d.title = b.book
            LEFT JOIN chunks c ON c.document_id = d.id AND {VISIBLE}
            GROUP BY b.book
        """,
        params=(list(DEUTEROCANONICAL_PASSAGES),),
        expect=deuterocanonical_pericopes,
        expect_text="each book has at least as many passages as 1.4c built ("
                    + ", ".join(f"{b} {n}" for b, n in DEUTEROCANONICAL_PASSAGES.items())
                    + "), and none is cited other than by verse range",
    ),
    SqlCheck(
        id="1.8c.ignatius-shorter-recension", items="1.8c, 3.1",
        proves="Ignatius's seven genuine letters show the shorter recension only.",
        sql=f"""
            SELECT count(*) FILTER (WHERE c.anchor ~ '/short(/|$)') AS shorter,
                   count(*) FILTER (WHERE c.anchor !~ '/short(/|$)'
                                      AND c.anchor !~ '/salutation$') AS other
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE left(c.document_id::text, 8) = ANY($1::text[]) AND {VISIBLE}
        """,
        params=(list(IGNATIUS_SHORTER_AND_LONGER),),
        expect=Row({"shorter": AtLeast(90), "other": 0}),
    ),
    SearchCheck(
        id="1.8d.robertson-incarnation", items="1.8d",
        proves="On the Incarnation is Robertson's public-domain translation, by section.",
        question="Why did the Word of God become man, according to Athanasius?",
        collections=("church-fathers",),
        expect=Some(Match(document=INCARNATION, reference=r"Section \d+")),
    ),
    SqlCheck(
        id="1.8d.robertson-text", items="1.8d",
        proves="Robertson's text replaced Lawson's: his \"made man that we might be made "
               "God\" is there and Lawson's wording is not.",
        sql=f"""
            SELECT count(*) FILTER (WHERE c.content LIKE '%was made man that we might be made God%')
                       AS robertson,
                   count(*) FILTER (WHERE c.content LIKE '%assumed humanity that we might become God%')
                       AS lawson,
                   count(*) AS passages
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = $1 AND {VISIBLE}
        """,
        params=(INCARNATION,),
        expect=Row({"robertson": 1, "lawson": 0, "passages": AtLeast(57)}),
    ),
    SqlCheck(
        id="1.9.anselm", items="1.9",
        proves="Anselm's works carry their fixes: Cur Deus Homo's title, the Proslogium's "
               "date and its preface.",
        sql=f"""
            SELECT (SELECT count(*) FROM documents
                    WHERE id = $1 AND title = 'Cur Deus Homo') AS cur_deus_homo,
                   (SELECT count(*) FROM documents
                    WHERE id = $2 AND date_display = '1077 to 1078') AS proslogium_date,
                   (SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id
                    WHERE c.document_id = $2 AND c.chapter_label = 'Preface' AND {VISIBLE})
                       AS proslogium_preface
        """,
        params=(CUR_DEUS_HOMO, PROSLOGIUM),
        expect=Row({"cur_deus_homo": 1, "proslogium_date": 1,
                    "proslogium_preface": AtLeast(1)}),
    ),
    removal_check("phase-1.removals", "1.1, 1.2b to 1.2e, 1.3a, 1.3c, 1.7, 1.8a to 1.8c, 1.9",
                  "What the Phase 1 rebuilds remove is not shown: Vatican II's footnote "
                  "cards, editors' introductions, notes and prefaces (rule G), site debris, "
                  "and the council passages kept as gaps until a translation is cleared.",
                  ("1.1", "1.2b", "1.2c", "1.2d", "1.2e-1", "1.2e-2", "1.2e-4", "1.2e-5",
                   "1.3a", "1.3c", "1.7", "1.8a", "1.8b", "1.8c", "1.9")),
    SqlCheck(
        id="contents.summa-and-catechism", items="#253, #254",
        proves="The Summa and the Catechism have stored contents trees; the Summa's shows "
               "the Supplement.",
        sql="""
            SELECT (SELECT count(*) FROM document_contents WHERE document_id = $1) AS summa,
                   (SELECT count(*) FROM document_contents WHERE document_id = $2) AS catechism,
                   (SELECT count(*) FROM document_contents
                    WHERE document_id = $1 AND depth = 0 AND short_label LIKE 'Suppl.%')
                       AS supplement
        """,
        params=(SUMMA, CATECHISM),
        expect=Row({"summa": AtLeast(3000), "catechism": AtLeast(400), "supplement": 1}),
    ),

    # ---- 3.2: labels and notes (placeholder) --------------------------------------------
    PlaceholderCheck(
        id="3.2.pending", items="3.2",
        proves="3.2 (labels, certainty and notes for works that stay) has not merged; its "
               "checks are added when it does.",
    ),
]

# Every collection answers an ordinary question, and a reference-style question
# through vector search too.
for _collection, _question in ORDINARY.items():
    CHECKS.append(SearchCheck(
        id=f"4.2.answers.{_collection}", items="4.2",
        proves=f"An ordinary question about {_collection} gets results.",
        question=_question, collections=(_collection,),
        expect=Answers(_collection),
    ))
for _collection, (_question, _match) in REFERENCES.items():
    CHECKS.append(SearchCheck(
        id=f"4.2.reference.{_collection}", items="4.2, C-16",
        proves=f"A citation-style question about {_collection} finds the passage it "
               f"names, through vector search as well as the final results.",
        question=_question, collections=(_collection,),
        expect=all_of(Some(_match), ViaVector(_match)),
    ))


# --------------------------------------------------------------------------- running

@dataclass
class Outcome:
    check: Check
    status: str        # PASS, FAIL, ERROR, NOT RUN or PENDING
    detail: str
    run: SearchRun | None = None


@dataclass
class Context:
    """What a run reads through. The live one is `_live_context`; tests pass fakes."""

    fetch: Callable[[str, tuple], Awaitable[list[dict]]]
    hydrate: Callable[[list[str]], Awaitable[dict[str, Hit]]]
    keyword: Callable[[str, str, int], Awaitable[list[str]]]
    # None when the run may not spend: the paid checks are then NOT RUN.
    search: Callable[[SearchCheck], Awaitable[SearchRun]] | None
    # (passage, question, the explanation input) -> (text, cost)
    explain: Callable[[Hit, str, str], Awaitable[tuple[str, float]]] | None
    registry: Registry


async def run_check(check: Check, ctx: Context, runs: list[SearchRun]) -> Outcome:
    try:
        if isinstance(check, PlaceholderCheck):
            return Outcome(check, "PENDING", check.proves)
        if isinstance(check, SqlCheck):
            verdict = check.expect(await ctx.fetch(check.sql, check.args(ctx.registry)))
            return Outcome(check, "PASS" if verdict.ok else "FAIL", verdict.detail)
        if isinstance(check, KeywordCheck):
            ids = await ctx.keyword(check.question, check.collection, check.limit)
            found = await ctx.hydrate(ids)
            run = SearchRun(check.question, (check.collection,),
                            results=[found[i] for i in ids if i in found])
            verdict = check.expect(run, ctx.registry)
            return Outcome(check, "PASS" if verdict.ok else "FAIL", verdict.detail, run)
        if isinstance(check, SearchCheck):
            if ctx.search is None:
                return Outcome(check, "NOT RUN", "paid; run with --spend")
            run = await ctx.search(check)
            runs.append(run)
            if run.error:
                return Outcome(check, "ERROR", run.error, run)
            # A search that did not run cleanly proves nothing, least of all that a
            # removed passage is absent. A healthy search may still find nothing.
            if run.degradations or run.outcome not in ("success", "no_candidates"):
                return Outcome(check, "ERROR", f"search outcome {run.outcome}, degraded "
                                               f"{run.degradations}; run it again", run)
            for target in check.explain_targets():
                hit = next((h for h in run.results if target.matches(h, ctx.registry)), None)
                if hit is not None and ctx.explain is not None:
                    text, cost = await ctx.explain(
                        hit, check.question, run.explain_inputs.get(hit.id, hit.content))
                    run.explanations[hit.id] = text
                    run.cost += cost
            verdict = check.expect(run, ctx.registry)
            return Outcome(check, "PASS" if verdict.ok else "FAIL", verdict.detail, run)
        if isinstance(check, AggregateCheck):
            if not runs:
                return Outcome(check, "NOT RUN", "needs the searches of this run (--spend)")
            verdict = check.expect(runs)
            return Outcome(check, "PASS" if verdict.ok else "FAIL", verdict.detail)
        raise TypeError(f"unknown check {type(check).__name__}")
    except Exception as exc:  # noqa: BLE001 - one broken check must not hide the others
        return Outcome(check, "ERROR", f"{type(exc).__name__}: {exc}")


async def run_checks(checks: Sequence[Check], ctx: Context) -> list[Outcome]:
    """Every check, aggregates last so they see every search of the run."""
    runs: list[SearchRun] = []
    ordered = ([c for c in checks if not isinstance(c, AggregateCheck)]
               + [c for c in checks if isinstance(c, AggregateCheck)])
    outcomes = []
    for check in ordered:
        outcome = await run_check(check, ctx, runs)
        outcomes.append(outcome)
        print(f"  {outcome.status:<7} {check.id}: {outcome.detail[:200]}", flush=True)
    return outcomes


# --------------------------------------------------------------------------- the live context

_HYDRATE_SQL = """
    SELECT c.id::text AS id, c.document_id::text AS document_id, d.collection,
           d.title AS document_title, COALESCE(w.author, d.author) AS author,
           c.anchor, c.reference, c.unit_label, c.content, c.searchable,
           (c.retired_at IS NOT NULL OR d.retired_at IS NOT NULL) AS retired,
           c.voice, c.language, c.work_key,
           c.metadata->>'text_source' AS text_source,
           c.metadata->>'text_status' AS text_status,
           c.metadata->>'official_latin_url' AS official_latin_url,
           c.metadata->>'article' AS article
    FROM chunks c JOIN documents d ON d.id = c.document_id
    LEFT JOIN document_works w ON w.document_id = c.document_id AND w.work_key = c.work_key
    WHERE c.id = ANY($1::uuid[])
"""


def _hits(rows: Iterable[dict]) -> dict[str, Hit]:
    return {r["id"]: Hit(**dict(r)) for r in rows}


# What a search returns travels with the passage (the Qdrant payload or the keyword
# row): the text, citation, label and role the models and the card see. The checks
# judge those as returned; the corpus row adds only what the card reads from it
# (author, text labels) and whether the passage is visible.
_RETURNED = ("document_id", "collection", "anchor", "reference", "unit_label", "content",
             "voice")


def as_returned(returned: dict, stored: Hit | None) -> Hit:
    fields = {k: returned[k] for k in _RETURNED if k in returned}
    if stored is None:
        return Hit(id=returned["id"], **{"collection": "", "document_id": "", **fields},
                   found=False)
    return dataclasses.replace(stored, **fields)


@contextlib.contextmanager
def _recording_vector_paths(captured: list[dict]):
    """Record the rows the vector path returns, for `ViaVector`, at no extra cost."""
    from app.rag.steps import retrieve_vector

    original = retrieve_vector.run

    async def recording(*args, **kwargs):
        paths = await original(*args, **kwargs)
        for strategies in paths.values():
            for strategy in strategies:
                captured.extend(strategy.rows)
        return paths

    retrieve_vector.run = recording
    try:
        yield
    finally:
        retrieve_vector.run = original


async def _live_context(spend: bool, registry: Registry) -> tuple[Context, Callable]:
    from app.db import close_pool, get_pool, init_pool
    from app.rag.steps import retrieve_fts

    await init_pool()
    pool = get_pool()
    if pool is None:
        raise SystemExit("no database pool; check DATABASE_URL")
    closers: list[Callable[[], Awaitable[None]]] = [close_pool]

    async def fetch(sql: str, args: tuple) -> list[dict]:
        async with pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch(sql, *args)]

    async def hydrate(ids: list[str]) -> dict[str, Hit]:
        return _hits(await fetch(_HYDRATE_SQL, (list(dict.fromkeys(ids)),))) if ids else {}

    async def keyword(question: str, collection: str, limit: int) -> list[str]:
        found = await retrieve_fts.run(question, [collection], QUOTA, k=limit,
                                       mode="min_match")
        return [row["id"] for row in found.get(collection, [])]

    search = explain = None
    if spend:
        from app.rag.api_keys import close_api_keys, init_api_keys
        from app.rag.pipelines import runner
        from app.rag.pipelines.registry import PIPELINES
        from app.rag.pipeline import _PRODUCTION_PIPELINE
        from app.rag.qdrant_client import close_qdrant, init_qdrant
        from app.rag.search_plan import resolve_search_plan
        from app.rag.steps import explain as explain_step
        from app.rag.steps import stitch
        from app.rag.steps.cost_tracker import CostTracker
        from app.rag.steps.embed import close_embed, init_embed
        from app.rag.steps.hyde_luna import close as close_hyde_luna
        from app.rag.steps.hyde_luna import init as init_hyde_luna
        from app.rag.steps.llm_rerank.openai_provider import close as close_luna
        from app.rag.steps.llm_rerank.openai_provider import init as init_luna
        from app.rag.steps.rerank_cohere import close_cohere, init_cohere
        from app.rag.steps.rerank_haiku import close_rerank, init_rerank

        init_embed(); init_qdrant(); init_api_keys(); init_hyde_luna()
        init_rerank(); init_cohere(); init_luna(); explain_step.init_explain()
        closers += [explain_step.close_explain, close_luna, close_cohere, close_rerank,
                    close_hyde_luna, close_api_keys, close_embed, close_qdrant]
        config = PIPELINES[_PRODUCTION_PIPELINE]

        async def search(check: SearchCheck) -> SearchRun:
            tracker = CostTracker()
            vector_rows: list[dict] = []
            run = SearchRun(check.question, check.collections)
            try:
                plan = resolve_search_plan(check.collections, check.quota)
                with _recording_vector_paths(vector_rows):
                    result = await runner.run(config, check.question, list(plan.collections),
                                              plan.quota, search_plan=plan,
                                              cost_tracker=tracker)
            except Exception as exc:  # noqa: BLE001 - reported as the check's ERROR
                run.error = f"{type(exc).__name__}: {exc}"
                run.cost = tracker.total_cost()
                return run
            found = await hydrate([c.chunk_id for c in result.chunks]
                                  + [row["id"] for row in vector_rows])
            run.results = [as_returned({"id": c.chunk_id, **{k: getattr(c, k)
                                                            for k in _RETURNED}},
                                       found.get(c.chunk_id))
                           for c in result.chunks]
            run.vector = [as_returned(row, found.get(row["id"])) for row in vector_rows]
            for chunk in result.chunks:
                attached = result.context.get(chunk.chunk_id)
                run.explain_inputs[chunk.chunk_id] = stitch.with_stitched_content(
                    stitch.Stitched(chunk, attached.parts if attached else [],
                                    attached.relation if attached else None)
                ).content
            run.outcome = result.outcome
            run.degradations = list(result.degradations)
            run.cost = tracker.total_cost()
            run.seconds = result.total_duration_s
            run.vector_seconds = next((t.duration_s for t in result.step_timings
                                       if t.step == "retrieve_vector"), None)
            return run

        async def explain(hit: Hit, question: str, content: str) -> tuple[str, float]:
            tracker = CostTracker()
            parts = [delta async for delta in explain_step.stream(
                content, hit.reference, hit.collection, question,
                unit_label=hit.unit_label, cost_tracker=tracker, voice=hit.voice,
            )]
            return "".join(parts), tracker.total_cost()

    async def close() -> None:
        for closer in closers:
            await closer()

    return Context(fetch, hydrate, keyword, search, explain, registry), close


# --------------------------------------------------------------------------- output

def print_list(checks: Sequence[Check]) -> None:
    paid = sum(1 for c in checks if isinstance(c, SearchCheck))
    explained = sum(len(c.explain_targets()) for c in checks if isinstance(c, SearchCheck))
    print(f"{len(checks)} checks: {paid} searches through the production pipeline "
          f"({explained} with an explanation), the rest free.\n")
    for check in checks:
        print(f"[{check.kind}] {check.id}   ({check.items})")
        print(f"    Proves:   {check.proves}")
        if isinstance(check, (SearchCheck, KeywordCheck)):
            where = check.collections if isinstance(check, SearchCheck) else (check.collection,)
            print(f"    Question: {check.question}   [{', '.join(where)}]")
        print(f"    Expects:  {check.expectation()}")
        print()


def _timing(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    return {"median_s": round(ordered[len(ordered) // 2], 2), "max_s": round(ordered[-1], 2)}


def summarise(outcomes: Sequence[Outcome]) -> dict:
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1
    runs = [o.run for o in outcomes if o.run is not None]
    return {
        "counts": counts,
        "cost_usd": round(sum(r.cost for r in runs), 4),
        "search_timing": _timing([r.seconds for r in runs if r.seconds is not None]),
        "vector_search_timing": _timing(
            [r.vector_seconds for r in runs if r.vector_seconds is not None]),
    }


def outcome_record(o: Outcome) -> dict:
    record = {"id": o.check.id, "items": o.check.items, "kind": o.check.kind,
              "status": o.status, "detail": o.detail, "expects": o.check.expectation()}
    if o.run is not None:
        record["question"] = o.run.question
        record["results"] = [{"reference": h.reference, "anchor": h.anchor,
                              "collection": h.collection} for h in o.run.results]
        record["explanations"] = o.run.explanations
        record["cost_usd"] = round(o.run.cost, 5)
        record["seconds"] = o.run.seconds
        record["vector_seconds"] = o.run.vector_seconds
    return record


def select(checks: Sequence[Check], only: Sequence[str] | None) -> list[Check]:
    if not only:
        return list(checks)
    chosen = [c for c in checks if any(c.id == o or c.id.startswith(o + ".") for o in only)]
    if not chosen:
        raise SystemExit(f"no check matches {only}")
    return chosen


async def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print every check; no calls")
    ap.add_argument("--spend", action="store_true",
                    help="also run the paid searches through the production pipeline")
    ap.add_argument("--only", nargs="+", help="check IDs, or ID prefixes such as 3.1")
    ap.add_argument("--json", help="write each check's outcome to this file")
    args = ap.parse_args(argv)

    checks = select(CHECKS, args.only)
    if args.list:
        print_list(checks)
        return 0

    from app.config import settings

    schema, collection = settings.corpus_read_schema, settings.qdrant_read_collection
    if args.spend and schema != "public" and collection in ("chunks", "chunks_live"):
        raise SystemExit(
            f"CORPUS_READ_SCHEMA={schema} but QDRANT_READ_COLLECTION={collection}: vector "
            f"search would read the live corpus. Name the staged collection."
        )
    print(f"corpus: schema {schema}; vector search: {collection if args.spend else 'not used'}")
    searches = sum(1 for c in checks if isinstance(c, SearchCheck))
    if args.spend:
        print(f"spend : {searches} searches through the production pipeline, at most "
              f"about ${searches * COST_PER_SEARCH:.2f}", flush=True)

    registry = Registry.load()
    ctx, close = await _live_context(args.spend, registry)
    try:
        outcomes = await run_checks(checks, ctx)
    finally:
        await close()

    summary = summarise(outcomes)
    print("\n" + ", ".join(f"{n} {s}" for s, n in sorted(summary["counts"].items()))
          + f"; cost ${summary['cost_usd']:.4f} (the pipeline's cost tracker)")
    for label, key in (("search", "search_timing"), ("vector search", "vector_search_timing")):
        if summary[key]:
            print(f"{label}: median {summary[key]['median_s']}s, "
                  f"slowest {summary[key]['max_s']}s")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"schema": schema, "qdrant_read_collection": collection if args.spend else None,
             **summary, "checks": [outcome_record(o) for o in outcomes]},
            indent=2, ensure_ascii=False,
        ) + "\n")
    return 0 if not summary["counts"].get("FAIL") and not summary["counts"].get("ERROR") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
