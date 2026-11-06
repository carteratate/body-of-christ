"""The work registry (corpus-cleanup 2.1): frozen document and passage IDs, redirects and
removals, as tracked files under `datapipeline/registry/`.

- `works.json`: one entry per document, sorted by collection then `work_id`. Its
  `source_key` names the work in the source (`church-fathers/<file>#<div id>`,
  `bible/<USFM code>`, `<collection>/<manifest slug>`, or the collection name for a
  one-document collection); adapters look the frozen document ID up by it.
- `passages/<collection>.jsonl`: one row per passage unit, sorted by document then
  anchor. The structural anchor decides which unit a passage is; this file decides its ID
  (D1). `live_anchor` is the anchor the unit had when it was frozen.
- `redirects.json`: units whose identity genuinely changed, by old passage ID (D1).
- `removals.json`: everything any phase removes, by anchor (D4).
- `kept_text.json`: passages a review found still hold their live text though the
  release report's stability score says otherwise, each with its reason (1.10b).

IDs, anchors and short fields only, never passage text. Adapters call
`resolve_document_id`; writers and reports call `resolve_passage_id`. A unit the registry
does not know (a new work, a restored verse, a new piece) falls back to `identity`.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace

import identity
from identity import PIECE_MARK, unit_anchor
from model import Document
from registry.genres import ALL_GENRES

REGISTRY_DIR = os.path.dirname(os.path.abspath(__file__))
WORKS_FILE = "works.json"
PASSAGES_DIR = "passages"
REDIRECTS_FILE = "redirects.json"
REMOVALS_FILE = "removals.json"
KEPT_TEXT_FILE = "kept_text.json"
# A row whose anchor's text moved to another piece is renamed `<anchor>#moved-<item>`, a
# name no build emits, and the anchor takes a new ID (Carter, 31 Oct 2026; 1.10b).
MOVED_MARK = "#moved-"

# Recorded in every built document's metadata, so a reader of the store can tell which
# anchors it holds.
ANCHOR_SCHEME = 2

WORK_STATUSES = ("active", "removed", "moved")
PASSAGE_STATUSES = ("active", "retired", "redirected")
# Passage voice (D5): None is the document's own voice.
VOICES = ("rejected",)
# The only list of removal reasons (D11). `rolled-back` is reserved for the tombstones
# 2.2w's rollback writes; it never appears in removals.json.
REMOVAL_REASONS = ("rule-a", "rule-b", "rule-c", "rule-g-editorial", "note-split-off",
                   "duplicate", "debris", "other-author", "superseded-translation",
                   "translation-in-preparation", "not-current-law", "awaiting-permission")
ROLLED_BACK = "rolled-back"
REMOVAL_SCOPES = ("document", "passage", "span", "class")
# 0.1c's outcome words (D5, D11); `same` and `removed` are report outcomes only.
REDIRECT_KINDS = ("moved", "split", "merged", "renumbered")
CERTAINTIES = ("genuine", "disputed", "pseudonymous", "anonymous")
VERDICTS = ("genuine", "spurious", "dubious", "interpolated", "attributed")
ACT_EFFECTS = ("condemn", "prohibit", "warn", "lift")
RULE_A_DECISIONS = ("include", "exclude")
TOMBSTONE_MAX = 300
# Fields a passage-registry row may set over the adapter's value (3.3, 3.4).
OVERRIDES = ("searchable", "language", "passage_author", "voice", "unit_label", "note")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- loading

@dataclass
class WorkRegistry:
    works: list[dict] = field(default_factory=list)
    passages: list[dict] = field(default_factory=list)
    redirects: list[dict] = field(default_factory=list)
    removals: list[dict] = field(default_factory=list)
    kept_text: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.document_by_key = {(w["collection"], w["source_key"]): w["document_id"]
                                for w in self.works}
        self.row_by_anchor = {(r["document_id"], r["anchor"]): r for r in self.passages}
        self.frozen_ids = {r["passage_id"] for r in self.passages}


def load_registry(directory: str = REGISTRY_DIR) -> WorkRegistry:
    """The registry files in `directory`; a missing file counts as empty."""
    def read(name: str) -> list:
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    passages = []
    folder = os.path.join(directory, PASSAGES_DIR)
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".jsonl"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    passages += [json.loads(line) for line in f if line.strip()]
    return WorkRegistry(read(WORKS_FILE), passages, read(REDIRECTS_FILE), read(REMOVALS_FILE),
                        read(KEPT_TEXT_FILE))


_current: WorkRegistry | None = None


def current() -> WorkRegistry:
    """The tracked registry, loaded once."""
    global _current
    if _current is None:
        _current = load_registry()
    return _current


def activate(registry: WorkRegistry | None) -> WorkRegistry | None:
    """Make `registry` the one adapters and writers resolve against (None reloads the
    tracked files on next use). Returns the previous one, for tests and the freeze."""
    global _current
    previous, _current = _current, registry
    return previous


# --------------------------------------------------------------------------- resolution

def frozen_document_id(collection: str, source_key: str,
                       registry: WorkRegistry | None = None) -> str | None:
    return (registry or current()).document_by_key.get((collection, source_key))


def resolve_document_id(collection: str, source_key: str, fallback_parts: tuple,
                        registry: WorkRegistry | None = None) -> str:
    """The frozen ID of a registered work, else `identity.document_id(*fallback_parts)`
    (a new work)."""
    return (frozen_document_id(collection, source_key, registry)
            or identity.document_id(*fallback_parts))


def resolve_passage_id(document_id: str, anchor: str,
                       registry: WorkRegistry | None = None) -> str:
    """The frozen ID of the unit this anchor names, else `identity.passage_id` (a
    genuinely new unit). A redirected piece whose opening unit opens a piece again takes
    its old ID back (2.1, split pieces)."""
    row = (registry or current()).row_by_anchor.get((document_id, anchor))
    return row["passage_id"] if row else identity.passage_id(document_id, anchor)


def work_entry(*, collection: str, source_key: str, document_id: str, title: str,
               author: str | None, frozen_on: str, work_id: str | None = None) -> dict:
    """A new works.json entry with every rule A and attribution field empty."""
    return {"work_id": work_id or work_id_for(collection, source_key),
            "document_id": document_id, "collection": collection, "source_key": source_key,
            "title": title, "author": author, "frozen_on": frozen_on, "status": "active",
            "supersedes": [],
            "rule_a": {"applies": False, "communion_start": None, "communion_end": None,
                       "work_date": None, "chronology_source": None, "church_acts": [],
                       "decision": None, "decision_basis": None},
            "attribution": {"credited_as": None, "certainty": None, "clavis": None,
                            "basis": None, "editorial_judgments": []},
            "works": []}


def register_new_work(registry: WorkRegistry, document: Document, frozen_on: str,
                      work_id: str | None = None) -> dict:
    """Add a work the registry does not hold yet (a later item's new source) and return
    its entry. The document's ID becomes frozen under its `source_key`."""
    key = (document.metadata or {}).get("source_key")
    if not key:
        raise ValueError(f"{document.title}: no metadata['source_key'] to register")
    if (document.collection, key) in registry.document_by_key:
        raise ValueError(f"{document.collection}/{key} is already registered")
    entry = work_entry(collection=document.collection, source_key=key,
                       document_id=document.id, title=document.title,
                       author=document.author, frozen_on=frozen_on, work_id=work_id)
    registry.works.append(entry)
    registry.works.sort(key=lambda w: (w["collection"], w["work_id"]))
    registry.__post_init__()
    return entry


def work_id_for(collection: str, source_key: str) -> str:
    """`church-fathers/apostolic fathers.xml#ii.iii` → `church-fathers/apostolic-fathers/ii.iii`."""
    path = source_key[len(collection) + 1:] if source_key.startswith(collection + "/") \
        else "" if source_key == collection else source_key
    path, _, div = path.partition("#")
    stem = identity.slugify(re.sub(r"\.(xml|html?|json|usfm)$", "", path))
    return "/".join(p for p in (collection, stem, div) if p)


def apply_overrides(document: Document, registry: WorkRegistry | None = None) -> Document:
    """The document with each passage's registry overrides applied: a value in the
    passage registry wins over the adapter's (3.3). 2.2w calls this at stage time."""
    rows = (registry or current()).row_by_anchor
    passages = []
    for p in document.passages:
        row = rows.get((document.id, p.anchor)) or {}
        changes = {k: row[k] for k in OVERRIDES if k in row}
        if "work_key" in row and row["work_key"] is not None:
            changes["work_key"] = row["work_key"]
        passages.append(replace(p, **changes) if changes else p)
    return replace(document, passages=passages)


def removed_document_ids(registry: WorkRegistry | None = None) -> set[str]:
    """Documents an open `document` removal entry retires (D4)."""
    return {e["document_id"] for e in open_removals(registry or current())
            if e.get("scope") == "document"}


def drop_removed(document: Document, registry: WorkRegistry | None = None) -> Document:
    """The document without the passages an open `passage` removal entry retires, matched
    by frozen passage ID or, for an entry naming none, by anchor. An adapter that already
    skips them is unchanged. Whole removed documents are dropped by the caller
    (`removed_document_ids`). Span and class entries remove text inside passages, which
    the adapter does; they drop nothing here. The passages kept are renumbered 0..n-1."""
    reg = registry or current()
    by_id, by_anchor = set(), set()
    for e in open_removals(reg):
        if e.get("scope") != "passage" or e.get("document_id") != document.id:
            continue
        if e.get("passage_id"):
            by_id.add(e["passage_id"])
        elif e.get("anchor"):
            by_anchor.add(e["anchor"])
    if not by_id and not by_anchor:
        return document
    kept = [p for p in document.passages
            if p.anchor not in by_anchor
            and resolve_passage_id(document.id, p.anchor, reg) not in by_id]
    if len(kept) == len(document.passages):
        return document
    # Positions stay 0..n-1 in reading order (health rule H3).
    return replace(document, passages=[replace(p, position=i) for i, p in enumerate(kept)])


def assign_ids(document: Document, registry: WorkRegistry | None = None
               ) -> tuple[Document, list[str]]:
    """The document with every `Passage.id` set from the passage registry (D1), and the
    IDs the registry does not hold: genuinely new units, which `identity.passage_id`
    names. Each history passage's `superseded_by_anchor` must name a passage of the same
    document; a ValueError says which does not."""
    reg = registry or current()
    passages = [replace(p, id=resolve_passage_id(document.id, p.anchor, reg))
                for p in document.passages]
    by_anchor = {p.anchor: p.id for p in passages}
    for p in passages:
        if p.superseded_by_anchor and p.superseded_by_anchor not in by_anchor:
            raise ValueError(
                f"{document.title}: history passage {p.anchor} names "
                f"{p.superseded_by_anchor}, which is not a passage of the same document")
    new = [p.id for p in passages if p.id not in reg.frozen_ids]
    return replace(document, passages=passages), new


# --------------------------------------------------------------------------- validation

def validate(registry: WorkRegistry) -> list[str]:
    """Every rule the registry files must hold; an empty list means valid."""
    problems: list[str] = []
    problems += _validate_works(registry.works)
    documents = {w["document_id"]: w for w in registry.works}
    problems += _validate_passages(registry, documents)
    problems += _validate_redirects(registry, documents)
    problems += _validate_removals(registry, documents)
    problems += _validate_kept_text(registry)
    return problems


def _validate_kept_text(registry: WorkRegistry) -> list[str]:
    entries = registry.kept_text
    out = _sorted(entries, lambda e: (e["document_id"], e["anchor"]), KEPT_TEXT_FILE)
    rows = {r["passage_id"]: r for r in registry.passages}
    seen: set[str] = set()
    for e in entries:
        pid = e.get("passage_id")
        if pid in seen:
            out.append(f"kept text {pid} appears twice")
        seen.add(pid)
        row = rows.get(pid)
        if row is None or row["status"] != "active" or row["anchor"] != e.get("anchor") \
                or row["document_id"] != e.get("document_id"):
            out.append(f"kept text {pid}: not an active row under its anchor")
        for k in ("reason", "added_by"):
            if not e.get(k):
                out.append(f"kept text {pid}: no {k}")
    return out


def _sorted(items: list, key, what: str) -> list[str]:
    keys = [key(x) for x in items]
    return [] if keys == sorted(keys) else [f"{what} is not sorted"]


def _validate_works(works: list[dict]) -> list[str]:
    out = _sorted(works, lambda w: (w["collection"], w["work_id"]), WORKS_FILE)
    seen: dict[str, set] = {"work_id": set(), "document_id": set(), "source_key": set()}
    for w in works:
        name = w.get("work_id")
        for k in ("work_id", "document_id"):
            if w.get(k) in seen[k]:
                out.append(f"{name}: duplicate {k} {w.get(k)}")
            seen[k].add(w.get(k))
        key = (w.get("collection"), w.get("source_key"))
        if key in seen["source_key"]:
            out.append(f"{name}: source key {key[1]} is registered twice")
        seen["source_key"].add(key)
        if w.get("status") not in WORK_STATUSES:
            out.append(f"{name}: status {w.get('status')!r}")
        out += [f"{name}: {p}" for p in _rule_a_problems(w.get("rule_a") or {})]
        out += [f"{name}: {p}" for p in _attribution_problems(w.get("attribution") or {})]
        ordinals = [x.get("ordinal") for x in w.get("works", [])]
        if ordinals != sorted(ordinals):
            out.append(f"{name}: works are not sorted by ordinal")
        keys = [x.get("work_key") for x in w.get("works", [])]
        if len(keys) != len(set(keys)):
            out.append(f"{name}: duplicate work_key")
        for x in w.get("works", []):
            if x.get("genre") is not None and x["genre"] not in ALL_GENRES:
                out.append(f"{name}: work {x.get('work_key')} genre {x['genre']!r}")
            if x.get("certainty") is not None and x["certainty"] not in CERTAINTIES:
                out.append(f"{name}: work {x.get('work_key')} certainty {x['certainty']!r}")
    return out


def _rule_a_problems(rule_a: dict) -> list[str]:
    out = []
    for k in ("communion_start", "communion_end", "work_date"):
        if rule_a.get(k) is not None and not _DATE.match(str(rule_a[k])):
            out.append(f"rule_a.{k} {rule_a[k]!r} is not an ISO date")
    if rule_a.get("decision") is not None and rule_a["decision"] not in RULE_A_DECISIONS:
        out.append(f"rule_a.decision {rule_a['decision']!r}")
    for act in rule_a.get("church_acts") or []:
        out += _act_problems(act, effect=True)
    return out


def _act_problems(act: dict, effect: bool) -> list[str]:
    out = []
    if not _DATE.match(str(act.get("date"))):
        out.append(f"church act date {act.get('date')!r} is not an ISO date")
    if not act.get("citation"):
        out.append("church act has no citation")
    if not act.get("issuer") or not act.get("act"):
        out.append("church act needs an issuer and an act")
    if effect and act.get("effect") not in ACT_EFFECTS:
        out.append(f"church act effect {act.get('effect')!r}")
    return out


def _attribution_problems(attribution: dict) -> list[str]:
    out = []
    if attribution.get("certainty") is not None and attribution["certainty"] not in CERTAINTIES:
        out.append(f"attribution.certainty {attribution['certainty']!r}")
    for j in attribution.get("editorial_judgments") or []:
        if not j.get("source_file") or not j.get("element_id"):
            out.append("editorial judgment needs a source file and element id")
        if j.get("verdict") not in VERDICTS:
            out.append(f"editorial judgment verdict {j.get('verdict')!r}")
        if len(j.get("quote") or "") > 300:
            out.append("editorial judgment quote is over 300 characters")
    return out


def _validate_passages(registry: WorkRegistry, documents: dict) -> list[str]:
    rows = registry.passages
    out = []
    by_collection: dict[str, list[dict]] = {}
    for r in rows:
        w = documents.get(r["document_id"])
        if w is None:
            out.append(f"passage {r['passage_id']}: document {r['document_id']} is not in "
                       f"{WORKS_FILE}")
            continue
        by_collection.setdefault(w["collection"], []).append(r)
    for collection, members in by_collection.items():
        out += _sorted(members, lambda r: (r["document_id"], r["anchor"]),
                       f"{PASSAGES_DIR}/{collection}.jsonl")
    ids, anchors = set(), set()
    redirected = {r["old_passage_id"] for r in registry.redirects if not r.get("closed_by")}
    retired = {e.get("passage_id") for e in registry.removals
               if e.get("scope") == "passage" and not e.get("closed_by")}
    work_keys = {w["document_id"]: {x["work_key"] for x in w.get("works", [])}
                 for w in registry.works}
    used_keys: set[tuple[str, str]] = set()
    for r in rows:
        pid = r["passage_id"]
        if pid in ids:
            out.append(f"passage {pid} appears twice")
        ids.add(pid)
        if (r["document_id"], r["anchor"]) in anchors:
            out.append(f"anchor {r['anchor']} names two passages of {r['document_id']}")
        anchors.add((r["document_id"], r["anchor"]))
        status = r.get("status")
        if status not in PASSAGE_STATUSES:
            out.append(f"passage {pid}: status {status!r}")
        if status == "redirected" and pid not in redirected:
            out.append(f"passage {pid} is redirected but no open redirect names it")
        if status == "retired" and pid not in retired:
            out.append(f"passage {pid} is retired but no removal entry explains it")
        if r.get("voice") is not None and r["voice"] not in VOICES:
            out.append(f"passage {pid}: voice {r['voice']!r}")
        if r.get("work_key") is not None:
            if r["work_key"] not in work_keys.get(r["document_id"], set()):
                out.append(f"passage {pid}: work_key {r['work_key']!r} names no work of "
                           "its document")
            used_keys.add((r["document_id"], r["work_key"]))
    for w in registry.works:
        for x in w.get("works", []):
            if (w["document_id"], x["work_key"]) not in used_keys:
                out.append(f"{w['work_id']}: work {x['work_key']} has no passage")
    return out


def _validate_redirects(registry: WorkRegistry, documents: dict) -> list[str]:
    redirects = registry.redirects
    out = _sorted(redirects, lambda r: (r["document_id"], r["old_anchor"]), REDIRECTS_FILE)
    rows = {r["passage_id"]: r for r in registry.passages}
    open_from: set[str] = set()
    for r in redirects:
        old, new = rows.get(r.get("old_passage_id")), rows.get(r.get("new_passage_id"))
        if not r.get("closed_by"):
            if r.get("old_passage_id") in open_from:
                out.append(f"redirect {r.get('old_passage_id')}: two open redirects")
            open_from.add(r.get("old_passage_id"))
            if old is None or old["status"] != "redirected":
                out.append(f"redirect {r.get('old_passage_id')}: its row is not redirected")
            if new is None or new["status"] != "active" or new["anchor"] != r.get("new_anchor") \
                    or new["document_id"] != r.get("document_id"):
                out.append(f"redirect {r.get('old_passage_id')}: its target is not an active "
                           "row of the same document under new_anchor")
        if r.get("kind") not in REDIRECT_KINDS:
            out.append(f"redirect {r.get('old_passage_id')}: kind {r.get('kind')!r}")
        if r.get("document_id") not in documents:
            out.append(f"redirect {r.get('old_passage_id')}: unknown document")
        if bool(r.get("closed_by")) != bool(r.get("closed_on")):
            out.append(f"redirect {r.get('old_passage_id')}: closed_by and closed_on go "
                       "together")
        for k in ("old_passage_id", "old_anchor", "new_passage_id", "new_anchor", "reason",
                  "added_by"):
            if not r.get(k):
                out.append(f"redirect {r.get('old_passage_id')}: no {k}")
    return out


def _validate_removals(registry: WorkRegistry, documents: dict) -> list[str]:
    entries = registry.removals
    out = _sorted(entries, lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""),
                  REMOVALS_FILE)
    ids, retired = set(), set()
    rows = {r["passage_id"]: r for r in registry.passages}
    # By ID: a removal names the live anchor, a redirect the current one.
    targets = {r["new_passage_id"] for r in registry.redirects if not r.get("closed_by")}
    for e in entries:
        name = e.get("id")
        if name in ids:
            out.append(f"removal {name} appears twice")
        ids.add(name)
        if "position" in e:
            out.append(f"removal {name}: entries name an anchor, never a position")
        scope, reason = e.get("scope"), e.get("reason")
        if scope not in REMOVAL_SCOPES:
            out.append(f"removal {name}: scope {scope!r}")
        if reason == ROLLED_BACK:
            out.append(f"removal {name}: {ROLLED_BACK} is written only by rollback")
        elif reason not in REMOVAL_REASONS:
            out.append(f"removal {name}: reason {reason!r}")
        if e.get("document_id") not in documents:
            out.append(f"removal {name}: document {e.get('document_id')} is not in "
                       f"{WORKS_FILE}")
        tombstone = e.get("tombstone")
        if scope in ("document", "passage"):
            if not tombstone:
                out.append(f"removal {name}: a {scope} removal needs a tombstone")
            elif len(tombstone) >= TOMBSTONE_MAX:
                out.append(f"removal {name}: tombstone is {TOMBSTONE_MAX} characters or more")
        elif tombstone is not None:
            out.append(f"removal {name}: a {scope} entry has no tombstone")
        if scope == "document" and e.get("anchor") is not None:
            out.append(f"removal {name}: a document removal has no anchor")
        if scope in ("passage", "span") and not e.get("anchor"):
            out.append(f"removal {name}: a {scope} removal needs an anchor")
        if scope in ("span", "class") and not e.get("span"):
            out.append(f"removal {name}: a {scope} removal needs its span")
        if scope == "passage":
            row = rows.get(e.get("passage_id"))
            if row is None or row["live_anchor"] != e.get("anchor") \
                    or row["document_id"] != e.get("document_id"):
                out.append(f"removal {name}: passage_id and anchor do not name one "
                           "registry row")
            key = (e.get("document_id"), e.get("anchor"))
            if not e.get("closed_by"):
                if key in retired:
                    out.append(f"removal {name}: anchor {key[1]} is retired twice")
                retired.add(key)
                if e.get("passage_id") in targets:
                    out.append(f"removal {name}: anchor {key[1]} is also a redirect target")
        if reason in ("rule-a", "rule-b"):
            act = e.get("church_act")
            if not act:
                out.append(f"removal {name}: a {reason} removal cites its Church act")
            else:
                out += [f"removal {name}: {p}" for p in _act_problems(act, effect=False)]
        if bool(e.get("closed_by")) != bool(e.get("closed_on")):
            out.append(f"removal {name}: closed_by and closed_on go together")
    return out


_HISTORY = re.compile(r"/history-\d{4}$")


def history_problems(document: Document) -> list[str]:
    """Superseded text kept as history (rule F, D11): a passage that names a current one
    has the anchor `<current anchor>/history-<year>`, is not searchable, and names a
    passage of the same document; a `/history-` anchor always names its current one."""
    anchors = {p.anchor for p in document.passages}
    out = []
    for p in document.passages:
        is_history = bool(_HISTORY.search(p.anchor))
        if p.superseded_by_anchor is None:
            if is_history:
                out.append(f"{p.anchor}: a history passage names its current passage")
            continue
        if not is_history or _HISTORY.sub("", p.anchor) != p.superseded_by_anchor:
            out.append(f"{p.anchor}: a history anchor is "
                       f"{p.superseded_by_anchor}/history-<year>")
        if p.searchable:
            out.append(f"{p.anchor}: a history passage is not searchable")
        if p.superseded_by_anchor not in anchors:
            out.append(f"{p.anchor}: {p.superseded_by_anchor} is not in the document")
    return out


def open_removals(registry: WorkRegistry) -> list[dict]:
    """The entries the writer applies: closed ones are kept as the record, not applied."""
    return [e for e in registry.removals if not e.get("closed_by")]


def open_redirects(registry: WorkRegistry) -> list[dict]:
    return [r for r in registry.redirects if not r.get("closed_by")]


# --------------------------------------------------------------------------- reconcile

@dataclass
class Reconciled:
    """What a build changes in the passage registry: rows to write, redirects to add or
    close, and anything a person has to settle (a vanished unit nothing explains)."""
    rows: list[dict]
    redirects: list[dict]
    problems: list[str]


_CUT = re.compile(r"-\d+$")


def reconcile(registry: WorkRegistry, documents: list[Document], *, item: str,
              today: str, settle=None, moved=None) -> Reconciled:
    """Bring the passage rows of `documents` in line with a new build, by the split-piece
    rule (D1, C-10):

    - a built anchor with a row keeps that row's ID; a redirected row reappearing is
      reclaimed: active again, and its redirect closed by `item`;
    - a built anchor with no row is a new unit with a new row;
    - an active piece row whose anchor is not built, and whose opening unit another
      passage of the same unit now holds, becomes `redirected` with a `merged` redirect
      to that passage;
    - any other active row that is not built is a problem, until a removal entry or a
      redirect explains it.

    A vanished piece whose opening unit several pieces hold (the unit now spans them) is
    one a person settles. `settle(passage_id, candidates)`, when given, returns the one
    of `candidates` that holds it (by the vanished piece's text), or None. A redirect
    settled so stays put on a later run while its target still holds that unit.

    A piece whose anchor is still built can still have lost its text: a cut counted
    inside a long paragraph (`/from-p26-3`) lands elsewhere when the paragraph's length
    changes. `moved(passage_id, passage, document)`, when given, returns the passage of
    `document` that now holds that ID's text, or None when `passage` still does. The
    moved row is renamed `<anchor>#moved-<item>` and redirected (`moved`) to the holder,
    and the anchor takes a new ID, so a saved row follows its text (Carter, 31 Oct
    2026)."""
    rows = [dict(r) for r in registry.passages]
    redirects = [dict(r) for r in registry.redirects]
    problems: list[str] = []
    by_anchor = {(r["document_id"], r["anchor"]): r for r in rows}
    explained = {e.get("passage_id") for e in open_removals(registry)}
    fresh: set[str] = set()
    for d in documents:
        built = {p.anchor: p for p in d.passages}
        for p in d.passages:
            row = by_anchor.get((d.id, p.anchor))
            if row is None:
                row = {"passage_id": identity.passage_id(d.id, p.anchor),
                       "document_id": d.id, "anchor": p.anchor, "live_anchor": p.anchor,
                       "status": "active", "frozen_on": today, "work_key": None}
                if row["passage_id"] in registry.frozen_ids:
                    problems.append(f"new unit {p.anchor} computes a frozen ID")
                rows.append(row)
                by_anchor[(d.id, p.anchor)] = row
                fresh.add(row["passage_id"])
            elif row["status"] == "redirected":
                row["status"] = "active"
                for r in redirects:
                    if r["old_passage_id"] == row["passage_id"] and not r.get("closed_by"):
                        r["closed_by"], r["closed_on"] = item, today
        if moved is not None:
            problems += _move_lost_text(d, moved, rows, redirects, by_anchor, fresh,
                                        registry.frozen_ids, item, today)
        for row in rows:
            if row["document_id"] != d.id or row["status"] != "active" \
                    or row["anchor"] in built:
                continue
            successor = _holder(row["anchor"], d)
            if successor is None and settle is not None:
                successor = _settled(settle, row["passage_id"], row["anchor"], d)
            if successor is not None:
                row["status"] = "redirected"
                redirects.append({
                    "document_id": d.id, "old_passage_id": row["passage_id"],
                    "old_anchor": row["anchor"],
                    "new_passage_id": by_anchor[(d.id, successor.anchor)]["passage_id"],
                    "new_anchor": successor.anchor, "kind": "merged",
                    "reason": "its opening unit no longer opens a piece",
                    "added_by": item})
            elif row["passage_id"] not in explained:
                problems.append(f"{row['anchor']} ({row['passage_id']}) is not built and "
                                "no removal entry or redirect explains it")
    # Every open redirect into a rebuilt document is recomputed from this build, so it
    # names whichever piece now holds its opening unit (after recuts and reclaims too).
    built = {d.id: d for d in documents}
    row_of = {r["passage_id"]: r for r in rows}
    for r in redirects:
        d = built.get(r["document_id"])
        if r.get("closed_by") or d is None or PIECE_MARK not in r["old_anchor"]:
            continue
        if unit_anchor(r["old_anchor"]) != unit_anchor(r["new_anchor"]):
            continue                   # into another unit: its text was traced there (1.3a)
        if MOVED_MARK in row_of[r["old_passage_id"]]["anchor"]:
            continue                   # its anchor is built; it names a new ID now
        if unit_anchor(r["new_anchor"]) != unit_anchor(r["old_anchor"]):
            continue                   # a rebuilt source's unit, named by hand (1.2e)
        holder = _holder(r["old_anchor"], d)
        if holder is None:
            held = [p for p in piece_holders(r["old_anchor"], d) if p.anchor == r["new_anchor"]]
            holder = held[0] if held else None
        if holder is None and settle is not None:
            holder = _settled(settle, r["old_passage_id"], r["old_anchor"], d)
        if holder is None:
            problems.append(f"{r['old_anchor']} ({r['old_passage_id']}): no single piece "
                            "now holds its opening unit")
            continue
        r["new_passage_id"] = by_anchor[(d.id, holder.anchor)]["passage_id"]
        r["new_anchor"] = holder.anchor
    # A redirect the freeze wrote under a pre-2.1 piece name has no unit to look up; one
    # whose target was itself redirected follows it to the final holder (p4 -> p3 becomes
    # p4 -> p2 when p3 later merges into p2).
    onward = {r["old_passage_id"]: r for r in redirects if not r.get("closed_by")}
    for r in redirects:
        seen = {r["old_passage_id"]}
        while not r.get("closed_by") and r["new_passage_id"] in onward \
                and r["new_passage_id"] not in seen:
            seen.add(r["new_passage_id"])
            nxt = onward[r["new_passage_id"]]
            r["new_passage_id"], r["new_anchor"] = nxt["new_passage_id"], nxt["new_anchor"]
    rows.sort(key=lambda r: (r["document_id"], r["anchor"]))
    redirects.sort(key=lambda r: (r["document_id"], r["old_anchor"]))
    return Reconciled(rows, redirects, problems)


def _move_lost_text(d: Document, moved, rows: list[dict], redirects: list[dict],
                    by_anchor: dict, fresh: set[str], frozen: set[str], item: str,
                    today: str) -> list[str]:
    """Re-ID each built piece of `d` whose row's text now lies in another piece."""
    problems = []
    moves = []
    for p in d.passages:
        row = by_anchor[(d.id, p.anchor)]
        if row["passage_id"] in fresh or row["status"] != "active":
            continue
        holder = moved(row["passage_id"], p, d)
        if holder is not None and holder is not p:
            moves.append((p, row, holder))
    for p, row, _ in moves:
        new_id = identity.passage_id(d.id, f"{p.anchor}#{item}")
        if new_id in frozen:
            problems.append(f"{p.anchor}: its new ID {new_id} is already frozen")
            continue
        row["anchor"] = f"{p.anchor}{MOVED_MARK}{item}"
        row["status"] = "redirected"
        new_row = {"passage_id": new_id, "document_id": d.id, "anchor": p.anchor,
                   "live_anchor": p.anchor, "status": "active", "frozen_on": today,
                   "work_key": row.get("work_key")}
        rows.append(new_row)
        by_anchor[(d.id, p.anchor)] = new_row
        by_anchor[(d.id, row["anchor"])] = row
        fresh.add(new_id)
    for p, row, holder in moves:
        if row["status"] != "redirected":
            continue
        target = by_anchor[(d.id, holder.anchor)]
        redirects.append({
            "document_id": d.id, "old_passage_id": row["passage_id"], "old_anchor": p.anchor,
            "new_passage_id": target["passage_id"], "new_anchor": holder.anchor,
            "kind": "moved", "reason": "its text now lies in another piece of the unit",
            "added_by": item})
    return problems


def _holder(anchor: str, document: Document):
    """The passage of the same unit that holds a vanished piece's opening unit."""
    holders = piece_holders(anchor, document)
    return holders[0] if len(holders) == 1 else None


def piece_holders(anchor: str, document: Document) -> list:
    """The passages of the same unit that hold a vanished piece's opening unit: one, or
    several when that unit now spans them (a person, or `settle`, picks the one)."""
    if PIECE_MARK not in anchor:
        return []
    unit, locator = unit_anchor(anchor), anchor.split(PIECE_MARK, 1)[1]
    members = [p for p in document.passages if unit_anchor(p.anchor) == unit]
    if len(members) == 1:
        return members                 # the unit is whole again: it holds every unit
    # The locator itself first; then without a trailing cut (`p5-2` opened inside `p5`).
    # A Bible locator (`3-16`) is chapter and verse, so it is only matched whole first.
    for wanted in (locator, _CUT.sub("", locator)):
        holders = [p for p in members if any(loc == wanted for loc, _ in p.source_units)]
        if holders:
            return holders
    return []


def _settled(settle, passage_id: str, anchor: str, document: Document):
    candidates = piece_holders(anchor, document)
    if len(candidates) < 2:
        return None
    chosen = settle(passage_id, candidates)
    return chosen if chosen in candidates else None


# --------------------------------------------------------------------------- writing

PASSAGE_KEYS = ("passage_id", "document_id", "anchor", "live_anchor", "status", "frozen_on",
                "work_key") + OVERRIDES


def write_registry(registry: WorkRegistry, directory: str = REGISTRY_DIR) -> None:
    """Write every registry file, sorted, in a stable format (one passage row per line)."""
    collection_of = {w["document_id"]: w["collection"] for w in registry.works}

    def dump(name: str, items: list) -> None:
        with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
            f.write("\n")

    dump(WORKS_FILE, sorted(registry.works, key=lambda w: (w["collection"], w["work_id"])))
    dump(REDIRECTS_FILE, sorted(registry.redirects,
                                key=lambda r: (r["document_id"], r["old_anchor"])))
    dump(KEPT_TEXT_FILE, sorted(registry.kept_text,
                                key=lambda e: (e["document_id"], e["anchor"])))
    dump(REMOVALS_FILE, sorted(registry.removals,
                               key=lambda e: (e["collection"], e["document_id"],
                                              e.get("anchor") or "")))
    folder = os.path.join(directory, PASSAGES_DIR)
    os.makedirs(folder, exist_ok=True)
    by_collection: dict[str, list[dict]] = {}
    for r in registry.passages:
        by_collection.setdefault(collection_of[r["document_id"]], []).append(r)
    for name in os.listdir(folder):
        if name.endswith(".jsonl") and name[:-6] not in by_collection:
            os.remove(os.path.join(folder, name))
    for collection, members in by_collection.items():
        members.sort(key=lambda r: (r["document_id"], r["anchor"]))
        with open(os.path.join(folder, f"{collection}.jsonl"), "w", encoding="utf-8") as f:
            for r in members:
                row = {k: r[k] for k in PASSAGE_KEYS if k in r}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
