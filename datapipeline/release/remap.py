"""Old-to-new passage remap for the release report (corpus-cleanup item 0.1c).

Maps every live passage to exactly one outcome and checks D1 (a passage ID names one unit
of text for good). This module defines the outcome vocabulary, and nothing else may (D5):
4.1a's user-data remap uses these words, and redirect kinds (2.1's redirects.json, 2.2a's
corpus_redirects) are the four middle words only (D11).

Pure functions over in-memory data. Nothing here reads a database, a file or `ingest/`:
`release.report` loads the snapshot, the build and 2.1's registry files and passes them in.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from typing import Callable

import identity
from model import Document, Passage

# The six outcomes (D5). Each old passage takes exactly one.
OUTCOMES = ("same", "moved", "split", "merged", "renumbered", "removed")
# The outcomes a redirect may declare (D11). `same` and `removed` are report outcomes only.
REDIRECT_KINDS = ("moved", "split", "merged", "renumbered")
# The evidence an outcome rests on, in the order they are tried.
METHODS = ("id", "redirect", "text_hash", "containment", "union", "jaccard")
# Build passages that are no old passage's successor are reported as `new`; it is not an
# outcome, because no old passage takes it.
NEW = "new"

# D1: a passage that keeps its ID must keep at least this much of its text.
ANCHOR_STABILITY_THRESHOLD = 0.5
SHINGLE_WORDS = 8
# Texts under this many words are compared word by word instead of by shingles.
SHORT_WORDS = 16
CONTAINMENT_MIN = 0.9
UNION_MIN = 0.9
JACCARD_MIN = 0.5

# The checks that fail a report. Each failure's check id is
# release.<check>:<collection>/<passage id>, keyed by passage ID because 2.1 keeps IDs
# when it re-anchors, so a known_defects.json entry survives that change.
CHECKS = ("stability", "removed", "unbacked", "anchor_reuse", "bad_redirect")


# --------------------------------------------------------------------------- data

@dataclass(frozen=True)
class OldPassage:
    """One live passage, as the 0.1c snapshot holds it."""
    id: str
    document_id: str
    collection: str
    anchor: str
    chapter_key: str
    reference: str
    position: int
    content: str
    unit_label: str | None = None
    chapter_label: str = ""


@dataclass(frozen=True)
class NewPassage:
    """One build passage with its resolved ID."""
    id: str
    document_id: str
    collection: str
    anchor: str
    chapter_key: str
    reference: str
    position: int
    content: str
    unit_label: str | None = None
    text_replaced: str | None = None


@dataclass
class Registry:
    """What 2.1's registry files declare. Until 2.1 merges every list is empty."""
    redirects: list[dict] = field(default_factory=list)
    removals: list[dict] = field(default_factory=list)
    # Old document ID → the document that supersedes it (works.json `supersedes`).
    supersedes: dict[str, str] = field(default_factory=dict)
    # Once 2.1 lands, every outcome other than `same` must be a declared redirect or a
    # removal entry; computed matches are then only the evidence a reviewer checks.
    enforce_redirects: bool = False


@dataclass(frozen=True)
class RemapRow:
    old_id: str
    outcome: str
    method: str | None
    new_ids: tuple[str, ...]          # primary first
    score: float | None
    old_document_id: str
    new_document_id: str | None
    old_anchor: str
    new_anchor: str | None
    old_chapter_key: str
    new_chapter_key: str | None
    collection: str
    # The removal-registry entry that explains a `removed` outcome, if any.
    removal: str | None = None

    def to_json(self) -> dict:
        return {"old_id": self.old_id, "outcome": self.outcome, "method": self.method,
                "new_ids": list(self.new_ids),
                "score": None if self.score is None else round(self.score, 4),
                "old_document_id": self.old_document_id,
                "new_document_id": self.new_document_id, "old_anchor": self.old_anchor,
                "new_anchor": self.new_anchor, "old_chapter_key": self.old_chapter_key,
                "new_chapter_key": self.new_chapter_key, "collection": self.collection,
                "removal": self.removal}


@dataclass(frozen=True)
class Failure:
    check: str
    collection: str
    document_id: str
    passage_id: str
    anchor: str | None
    score: float | None
    detail: str

    @property
    def check_id(self) -> str:
        return f"release.{self.check}:{self.collection}/{self.passage_id}"


@dataclass
class RemapResult:
    rows: list[RemapRow]
    new: list[NewPassage]
    failures: list[Failure]
    # Every build passage that declares `text_replaced`, with its stability score.
    replacements: list[dict]

    def outcome_counts(self) -> Counter:
        return Counter(r.outcome for r in self.rows)


# --------------------------------------------------------------------------- text

_WORD = re.compile(r"[^\W_]+")


def words(text: str) -> list[str]:
    """Letters and digits only, after NFKC and lowercasing: spacing, punctuation and
    quote styles are not evidence of a different text."""
    return _WORD.findall(unicodedata.normalize("NFKC", text or "").lower())


def shingles(ws: list[str], k: int = SHINGLE_WORDS) -> set[tuple[str, ...]]:
    return {tuple(ws[i:i + k]) for i in range(len(ws) - k + 1)}


def similarity(a: str, b: str) -> float:
    """The larger of two containments, a's text found in b and b's found in a, so a unit
    that only gained restored prose or only lost notes scores near 1. The larger is always
    the shorter text's containment in the longer. On 8-word shingles, or, when either side
    is under SHORT_WORDS words, word by word: the best difflib ratio between the shorter
    text's words and any window of the longer one with as many words."""
    wa, wb = words(a), words(b)
    if wa == wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    if min(len(wa), len(wb)) < SHORT_WORDS:
        return _short_containment(*sorted((wa, wb), key=len))
    ha, hb = shingles(wa), shingles(wb)
    shared = len(ha & hb)
    return max(shared / len(ha), shared / len(hb))


def _short_containment(short: list[str], long: list[str]) -> float:
    # Words, not characters: two different English sentences of this length share about
    # 45% of their characters in order, and 15% of different short Summa parts reached the
    # 0.5 threshold that way (measured on the 6 Oct snapshot); by words it was 2%. A window
    # of the shorter text's length stops letters or words scattered through a long text
    # from counting.
    best = 0.0
    for i in range(len(long) - len(short) + 1):
        matcher = SequenceMatcher(None, short, long[i:i + len(short)], autojunk=False)
        if matcher.real_quick_ratio() > best and matcher.quick_ratio() > best:
            best = max(best, matcher.ratio())
            if best == 1.0:
                break
    return best


# A display piece's trailing number: /p2, -p2, or the Bible's -2.
_PIECE = re.compile(r"(/p|-p|-)\d+$")
# A bare /2 is a piece number only inside a labelled part (the Summa numbers every part of
# an article in one running sequence); elsewhere it numbers distinct paragraphs, as in a
# council's synodal letter, which share a reference and have no label.
_RUNNING = re.compile(r"/\d+$")


def unit_key(p: OldPassage | NewPassage) -> tuple:
    """Consecutive passages with equal keys are display pieces of one unit: same chapter,
    citation and unit label, and anchors that differ only in a trailing piece number."""
    base = _PIECE.sub("", p.anchor)
    if p.unit_label:
        base = _RUNNING.sub("", base)
    return (p.chapter_key, p.reference, p.unit_label, base)


def units(passages: list) -> list[list]:
    """`passages` (one document, in position order) grouped into units."""
    out: list[list] = []
    previous = None
    for p in passages:
        key = unit_key(p)
        if out and key == previous:
            out[-1].append(p)
        else:
            out.append([p])
        previous = key
    return out


# --------------------------------------------------------------------------- matching

@dataclass(frozen=True)
class _Match:
    method: str
    targets: tuple[int, ...]       # indices into the document's passages, primary first
    score: float


class _DocumentIndex:
    """One successor document's passages, indexed for the old passages that need a
    computed match. Only shingles those old passages hold are indexed."""

    def __init__(self, passages: list[NewPassage], wanted: set[tuple[str, ...]]):
        self.passages = passages
        self.words = [words(p.content) for p in passages]
        self.joined = [" ".join(w) for w in self.words]
        self.by_text: dict[str, int] = {}
        for i, text in enumerate(self.joined):
            self.by_text.setdefault(text, i)
        self.shingles = [shingles(w) & wanted for w in self.words]
        self.sizes = [max(len(w) - SHINGLE_WORDS + 1, 0) for w in self.words]
        self.index: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for i, sh in enumerate(self.shingles):
            for s in sh:
                self.index[s].append(i)

    def match(self, old: OldPassage) -> _Match | None:
        ws = words(old.content)
        if not ws:
            return None
        text = " ".join(ws)
        if text in self.by_text:
            return _Match("text_hash", (self.by_text[text],), 1.0)
        if len(ws) < SHINGLE_WORDS:
            needle = f" {text} "
            for i, joined in enumerate(self.joined):
                if needle in f" {joined} ":
                    return _Match("containment", (i,), 1.0)
            return None

        sh = shingles(ws)
        counts = Counter(i for s in sh for i in self.index.get(s, ()))
        if not counts:
            return None
        best = min(counts, key=lambda i: (-counts[i], i))
        if counts[best] / len(sh) >= CONTAINMENT_MIN:
            return _Match("containment", (best,), counts[best] / len(sh))

        union = self._union(ws, sh, sorted(counts))
        if union is not None:
            return union

        def jaccard(i: int) -> float:
            return counts[i] / (len(sh) + self.sizes[i] - counts[i])
        best = min(counts, key=lambda i: (-jaccard(i), i))
        if jaccard(best) >= JACCARD_MIN:
            return _Match("jaccard", (best,), jaccard(best))
        return None

    def _union(self, ws: list[str], sh: set, candidates: list[int]) -> _Match | None:
        """The best run of 2 or more consecutive passages that together hold the old text."""
        runs: list[list[int]] = []
        for i in candidates:
            if runs and i == runs[-1][-1] + 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        best: tuple[float, list[int]] | None = None
        for run in runs:
            # Drop passages at either end that add nothing the rest of the run lacks.
            while len(run) > 1 and not (self.shingles[run[0]] & sh) - _union_of(self, run[1:]):
                run = run[1:]
            while len(run) > 1 and not (self.shingles[run[-1]] & sh) - _union_of(self, run[:-1]):
                run = run[:-1]
            if len(run) < 2:
                continue
            # Measured on the run's joined text, so shingles that cross a cut count.
            joined = [w for i in run for w in self.words[i]]
            covered = len(sh & shingles(joined)) / len(sh)
            if best is None or covered > best[0]:
                best = (covered, run)
        if best is None or best[0] < UNION_MIN:
            return None
        first = tuple(ws[:SHINGLE_WORDS])
        primary = next((i for i in best[1] if first in self.shingles[i]), best[1][0])
        targets = (primary,) + tuple(i for i in best[1] if i != primary)
        return _Match("union", targets, best[0])


def _union_of(index: _DocumentIndex, run: list[int]) -> set:
    out: set = set()
    for i in run:
        out |= index.shingles[i]
    return out


# --------------------------------------------------------------------------- remap

def default_passage_id(document: Document, passage: Passage) -> str:
    """The ID the writer gives a build passage. A frozen ID set in metadata (2.1's
    registry, or a test) wins; otherwise identity.passage_id, as the writer computes it."""
    frozen = (passage.metadata or {}).get("passage_id")
    return frozen or identity.passage_id(document.id, passage.anchor)


def new_passages(documents: list[Document],
                 passage_id: Callable[[Document, Passage], str] = default_passage_id
                 ) -> list[NewPassage]:
    out = []
    for d in documents:
        for p in d.passages:
            out.append(NewPassage(
                id=passage_id(d, p), document_id=d.id, collection=d.collection,
                anchor=p.anchor, chapter_key=p.chapter_key, reference=p.reference,
                position=p.position, content=p.content, unit_label=p.unit_label,
                text_replaced=(p.metadata or {}).get("text_replaced")))
    return out


def remap(old: list[OldPassage], new: list[Document], registry: Registry | None = None,
          *, passage_id: Callable[[Document, Passage], str] = default_passage_id
          ) -> RemapResult:
    """Map every old passage to one outcome, check D1, and list the build's new passages.
    Computed matches are looked for only in the old passage's own document, or the one
    the registry says supersedes it, never across documents otherwise."""
    registry = registry or Registry()
    built = new_passages(new, passage_id)
    by_id: dict[str, NewPassage] = {}
    by_document: dict[str, list[NewPassage]] = defaultdict(list)
    for p in built:
        by_id.setdefault(p.id, p)
        by_document[p.document_id].append(p)
    for passages in by_document.values():
        passages.sort(key=lambda p: (p.position, p.id))
    old = sorted(old, key=lambda o: (o.collection, o.document_id, o.position, o.id))

    redirects: dict[str, list[dict]] = defaultdict(list)
    for r in registry.redirects:
        redirects[r["old_passage_id"]].append(r)
    removals_by_id, removals_by_anchor, removed_documents = _removals(registry.removals)

    rows: dict[str, RemapRow] = {}
    failures: list[Failure] = []
    pending: dict[str, list[OldPassage]] = defaultdict(list)
    for o in old:
        if o.id in redirects:
            row, failure = _redirect_row(o, redirects[o.id], by_id)
            rows[o.id] = row
            if failure:
                failures.append(failure)
        elif o.id in by_id:
            n = by_id[o.id]
            rows[o.id] = RemapRow(o.id, "same", "id", (n.id,), None, o.document_id,
                                  n.document_id, o.anchor, n.anchor, o.chapter_key,
                                  n.chapter_key, o.collection)
        else:
            entry = (removals_by_id.get(o.id) or removals_by_anchor.get((o.document_id, o.anchor))
                     or removed_documents.get(o.document_id))
            if entry is not None:
                rows[o.id] = _removed(o, entry["id"])
            else:
                pending[o.document_id].append(o)

    # Computed matches, one successor document at a time.
    computed: dict[str, tuple[_Match, list[NewPassage]]] = {}
    for document_id, olds in pending.items():
        successor = document_id if document_id in by_document \
            else registry.supersedes.get(document_id)
        passages = by_document.get(successor or "", [])
        if not passages:
            for o in olds:
                rows[o.id] = _removed(o, None)
            continue
        wanted = set().union(*(shingles(words(o.content)) for o in olds))
        index = _DocumentIndex(passages, wanted)
        for o in olds:
            match = index.match(o)
            if match is None:
                rows[o.id] = _removed(o, None)
            else:
                computed[o.id] = (match, passages)

    # One target holding text from two or more old passages is a merge; else a move.
    holders: Counter = Counter(r.new_ids[0] for r in rows.values() if r.outcome == "same")
    for match, passages in computed.values():
        if match.method != "union":
            holders[passages[match.targets[0]].id] += 1
    for o in old:
        if o.id not in computed:
            continue
        match, passages = computed[o.id]
        targets = [passages[i] for i in match.targets]
        if match.method == "union":
            outcome = "split"
        else:
            outcome = "merged" if holders[targets[0].id] > 1 else "moved"
        primary = targets[0]
        rows[o.id] = RemapRow(o.id, outcome, match.method, tuple(t.id for t in targets),
                              match.score, o.document_id, primary.document_id, o.anchor,
                              primary.anchor, o.chapter_key, primary.chapter_key, o.collection)

    ordered = [rows[o.id] for o in old]
    for row in ordered:
        # A bad redirect is reported as such, not again as a removal.
        if row.outcome == "removed" and row.removal is None and row.method != "redirect":
            failures.append(Failure("removed", row.collection, row.old_document_id, row.old_id,
                                    row.old_anchor, None, "no successor, and no removal-registry "
                                    "entry explains it"))
        if registry.enforce_redirects and row.outcome in REDIRECT_KINDS \
                and row.method != "redirect":
            failures.append(Failure("unbacked", row.collection, row.old_document_id, row.old_id,
                                    row.old_anchor, row.score, f"{row.outcome} by "
                                    f"{row.method} with no redirect row"))

    stable, replacements, scores = _stability(old, ordered, by_document)
    ordered = [replace(r, score=scores[r.old_id]) if r.old_id in scores else r
               for r in ordered]
    failures += stable
    failures += _anchor_reuse(old, built, registry.removals)

    successors = {i for r in ordered for i in r.new_ids}
    fresh = [p for p in built if p.id not in successors]
    order = {c: i for i, c in enumerate(CHECKS)}
    failures.sort(key=lambda f: (order[f.check], f.collection, f.document_id, f.passage_id))
    return RemapResult(ordered, fresh, failures, replacements)


def _removals(entries: list[dict]) -> tuple[dict, dict, dict]:
    """Open removal entries that retire passages: by passage ID, by (document, anchor),
    and whole documents. Span and class entries retire nothing."""
    by_id, by_anchor, documents = {}, {}, {}
    for e in entries:
        if e.get("closed_by"):
            continue
        if e.get("scope") == "passage":
            if e.get("passage_id"):
                by_id[e["passage_id"]] = e
            if e.get("anchor"):
                by_anchor[(e["document_id"], e["anchor"])] = e
        elif e.get("scope") == "document":
            documents[e["document_id"]] = e
    return by_id, by_anchor, documents


def _removed(o: OldPassage, removal: str | None) -> RemapRow:
    return RemapRow(o.id, "removed", None, (), None, o.document_id, None, o.anchor, None,
                    o.chapter_key, None, o.collection, removal)


def _redirect_row(o: OldPassage, declared: list[dict], by_id: dict[str, NewPassage]
                  ) -> tuple[RemapRow, Failure | None]:
    kinds = {r.get("kind") for r in declared}
    ids = tuple(r["new_passage_id"] for r in declared)
    primary = by_id.get(ids[0])
    problem = None
    if len(kinds) != 1 or not kinds <= set(REDIRECT_KINDS):
        problem = f"redirect kinds {sorted(map(str, kinds))}; allowed {list(REDIRECT_KINDS)}"
    elif missing := [i for i in ids if i not in by_id]:
        problem = f"redirect target {missing[0]} is not in the build"
    elif o.id in by_id:
        problem = "the redirected passage ID is still in the build"
    outcome = next(iter(kinds)) if len(kinds) == 1 and kinds <= set(REDIRECT_KINDS) \
        else "removed"
    row = RemapRow(o.id, outcome, "redirect", ids if outcome != "removed" else (), None,
                   o.document_id, primary.document_id if primary else None, o.anchor,
                   primary.anchor if primary else None, o.chapter_key,
                   primary.chapter_key if primary else None, o.collection)
    failure = None if problem is None else Failure(
        "bad_redirect", o.collection, o.document_id, o.id, o.anchor, None, problem)
    return row, failure


# --------------------------------------------------------------------------- D1 checks

def _stability(old: list[OldPassage], rows: list[RemapRow],
               by_document: dict[str, list[NewPassage]]
               ) -> tuple[list[Failure], list[dict], dict[str, float]]:
    """Every unit that keeps a passage ID must keep at least ANCHOR_STABILITY_THRESHOLD of
    its text, judged unit by unit: the display pieces on each side are joined, because a
    piece is a slice of one unit and piece boundaries move when text is restored."""
    outcome = {r.old_id: r for r in rows}
    new_unit: dict[str, tuple[str, int]] = {}
    new_units: dict[str, list[list[NewPassage]]] = {}
    for document_id, passages in by_document.items():
        new_units[document_id] = units(passages)
        for k, unit in enumerate(new_units[document_id]):
            for p in unit:
                new_unit[p.id] = (document_id, k)

    old_by_document: dict[str, list[OldPassage]] = defaultdict(list)
    for o in old:
        old_by_document[o.document_id].append(o)

    failures: list[Failure] = []
    scores: dict[tuple[str, int], float] = {}
    passage_scores: dict[str, float] = {}
    for document_id, olds in old_by_document.items():
        for unit in units(olds):
            kept = [o for o in unit if outcome[o.id].outcome == "same"]
            if not kept:
                continue
            keys = sorted({new_unit[o.id] for o in kept}, key=lambda k: (k[0], k[1]))
            successors = [p for key in keys for p in new_units[key[0]][key[1]]]
            score = similarity(" ".join(o.content for o in unit),
                               " ".join(p.content for p in successors))
            for key in keys:
                scores[key] = min(scores.get(key, 1.0), score)
            for o in kept:
                passage_scores[o.id] = score
            if score >= ANCHOR_STABILITY_THRESHOLD:
                continue
            if any(p.text_replaced for p in successors):
                continue
            first = kept[0]
            failures.append(Failure(
                "stability", first.collection, document_id, first.id, first.anchor, score,
                f"unit of {len(unit)} live passage{'s' * (len(unit) != 1)} "
                f"({unit[0].anchor} to {unit[-1].anchor}) keeps {score:.2f} of its text "
                f"in {len(successors)} build passage{'s' * (len(successors) != 1)}"))

    replacements = []
    for document_id, document_units in sorted(new_units.items()):
        for k, unit in enumerate(document_units):
            for p in unit:
                if p.text_replaced:
                    replacements.append({
                        "collection": p.collection, "document_id": document_id,
                        "passage_id": p.id, "anchor": p.anchor, "reason": p.text_replaced,
                        "score": None if (document_id, k) not in scores
                        else round(scores[(document_id, k)], 4)})
    return failures, replacements, passage_scores


def _anchor_reuse(old: list[OldPassage], built: list[NewPassage],
                  removals: list[dict]) -> list[Failure]:
    """A live anchor string may only name the unit that holds it today, so an old
    ?anchor= link never lands on different text; a retired anchor is never reused."""
    live = {(o.document_id, o.anchor): o for o in old}
    retired = {(e["document_id"], e["anchor"]): e for e in removals
               if e.get("scope") == "passage" and e.get("anchor") and not e.get("closed_by")}
    out = []
    for p in built:
        o = live.get((p.document_id, p.anchor))
        entry = retired.get((p.document_id, p.anchor))
        if o is not None and o.id != p.id and entry is None:
            out.append(Failure("anchor_reuse", o.collection, o.document_id, o.id, o.anchor,
                               None, f"live anchor now carried by build passage {p.id}"))
        if entry is not None:
            pid = entry.get("passage_id") or (o.id if o else p.id)
            out.append(Failure("anchor_reuse", p.collection, p.document_id, pid, p.anchor,
                               None, f"anchor retired by removal {entry.get('id')} is "
                               f"carried by build passage {p.id}"))
    return out


# --------------------------------------------------------------------------- chapters

def chapter_remap(old: list[OldPassage], rows: list[RemapRow],
                  references: dict | None = None) -> list[dict]:
    """One row per old (document_id, chapter_key): the new document and chapter that most
    of its passages' primary successors land in, the share of its passages that agree, and
    the anchors reading_progress rows hold there (from references.json). 4.1a rewrites
    reading_progress from this and remap.jsonl; 2.2w turns each changed chapter into a
    chapter redirect. A tie goes to the successor of the earliest passage."""
    outcome = {r.old_id: r for r in rows}
    chapters: dict[tuple[str, str], list[OldPassage]] = {}
    for o in sorted(old, key=lambda o: (o.document_id, o.position, o.id)):
        chapters.setdefault((o.document_id, o.chapter_key), []).append(o)
    positions = (references or {}).get("documents", {})

    out = []
    for (document_id, chapter_key), members in chapters.items():
        votes: Counter = Counter()
        first: dict[tuple, int] = {}
        for i, o in enumerate(members):
            r = outcome[o.id]
            if r.new_ids:
                key = (r.new_document_id, r.new_chapter_key)
                votes[key] += 1
                first.setdefault(key, i)
        if votes:
            target = min(votes, key=lambda k: (-votes[k], first[k]))
            agree = votes[target]
        else:
            target, agree = (None, None), 0
        held = [p for p in positions.get(document_id, {}).get("positions", [])
                if p["chapter_key"] == chapter_key]
        out.append({
            "collection": members[0].collection,
            "old_document_id": document_id, "old_chapter_key": chapter_key,
            "new_document_id": target[0], "new_chapter_key": target[1],
            "passages": len(members), "share": round(agree / len(members), 4),
            "reading_progress_rows": sum(p["rows"] for p in held),
            "reading_progress_anchors": sorted({p["anchor"] for p in held if p["anchor"]}),
        })
    return out


# --------------------------------------------------------------------------- user impact

USER_TABLES = ("retrievals", "bookmarks", "guest_trial_retrievals", "retrieval_labels")


# User-impact row for passages that keep their ID but fall below the stability threshold:
# saved rows that would open on different text (a stability failure or a declared
# replacement). Not an outcome; the spec's impact rows cover changed IDs only.
BELOW_THRESHOLD = "same, text below threshold"


def user_impact(rows: list[RemapRow], chapters: list[dict], references: dict) -> dict:
    """Saved user rows each outcome affects, per collection: for `removed` and for every
    outcome whose primary ID differs from the old ID, the rows of each user table pointing
    at the old ID, and the reading_progress rows whose anchor or chapter key changes. Rows
    pointing at a `same` passage scored below ANCHOR_STABILITY_THRESHOLD are counted
    under BELOW_THRESHOLD."""
    by_passage = references.get("passages", {})
    out: dict[str, dict] = {}

    def bucket(collection: str, outcome: str) -> dict:
        per = out.setdefault(collection, {})
        return per.setdefault(outcome, {"passages": 0, **{t: 0 for t in USER_TABLES},
                                        "reading_progress": 0})

    for r in rows:
        kept = r.outcome != "removed" and r.new_ids and r.new_ids[0] == r.old_id
        drifted = kept and r.score is not None and r.score < ANCHOR_STABILITY_THRESHOLD
        if kept and not drifted:
            continue
        counts = by_passage.get(r.old_id)
        if not counts or not any(counts.get(t) for t in USER_TABLES):
            continue
        b = bucket(r.collection, BELOW_THRESHOLD if drifted else r.outcome)
        b["passages"] += 1
        for t in USER_TABLES:
            b[t] += counts.get(t, 0)

    # A reading_progress row moves when its anchor's passage gets a new anchor or chapter
    # or none, or, for a row with no anchor, when its chapter maps elsewhere.
    by_anchor = {(r.old_document_id, r.old_anchor): r for r in rows}
    by_chapter = {(c["old_document_id"], c["old_chapter_key"]): c for c in chapters}
    for document_id, doc in references.get("documents", {}).items():
        for p in doc.get("positions", []):
            r = by_anchor.get((document_id, p["anchor"])) if p["anchor"] else None
            if r is not None:
                moved = (r.outcome == "removed" or r.new_document_id != document_id
                         or r.new_anchor != r.old_anchor or r.new_chapter_key != p["chapter_key"])
                collection, outcome = r.collection, r.outcome
            else:
                c = by_chapter.get((document_id, p["chapter_key"]))
                if c is None:
                    continue          # a chapter the snapshot does not hold: not ours to move
                moved = (c["new_document_id"] != document_id
                         or c["new_chapter_key"] != p["chapter_key"])
                collection, outcome = c["collection"], "chapter"
            if moved:
                bucket(collection, outcome)["reading_progress"] += p["rows"]
    return {c: dict(sorted(v.items())) for c, v in sorted(out.items())}
