"""What a stage retires and redirects, computed against live (2.2w stage step 5).

Pure functions over the live rows of the staged collections, the staged documents and
2.1's registry; `publication.StageRunner` reads the inputs and writes the results into
`staging.corpus_tombstones` and `staging.corpus_redirects`.

Every live passage the build does not emit must be explained (D4): by an open redirect
in `registry/redirects.json`, which becomes a passage redirect, or by an open removal
entry, which becomes a tombstone. Anything else stops the stage, naming the ID. A live
passage the build emits under another document is not a retirement: it keeps its ID and
moves at the apply. Two more kinds of redirect keep old links working: anchor redirects
for registry rows whose anchor or document changed, and chapter redirects for chapters
that moved (0.1c's chapter remap).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import registry as reg
from model import Document
from release import remap as R

# Removal reason → the tombstone's rule column (D11). Never stored in the registry.
_RULES = {"rule-a": "A", "rule-b": "B", "rule-c": "C", "rule-g-editorial": "G",
          "note-split-off": "G"}


@dataclass(frozen=True)
class LivePassage:
    id: str
    document_id: str
    collection: str
    anchor: str | None
    chapter_key: str | None
    chapter_label: str | None
    reference: str | None
    position: int
    title: str
    author: str | None


@dataclass(frozen=True)
class LiveDocument:
    id: str
    collection: str
    title: str
    author: str | None


@dataclass
class Retirements:
    tombstones: list[dict] = field(default_factory=list)
    redirects: list[dict] = field(default_factory=list)
    # Live passage IDs the build emits under another document (moved at the apply).
    moved: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def rule_for(reason: str) -> str:
    return _RULES.get(reason, "other")


def render_church_act(act: dict | None) -> str | None:
    """"Second Council of Constantinople, anathema 11, 553": the issuer, the act and the
    year of the registry entry's Church act."""
    if not act:
        return None
    year = str(act.get("date") or "")[:4].lstrip("0") or None
    return ", ".join(str(x) for x in (act.get("issuer"), act.get("act"), year) if x)


def _snapshot(collection: str, title: str, author: str | None, reference: str | None,
              chapter_label: str | None) -> dict:
    return {"collection": collection, "title": title, "author": author,
            "reference": reference, "chapter_label": chapter_label}


def tombstone(entry: dict, *, entity: str, id: str, document_id: str, snapshot: dict,
              release: str, at: datetime) -> dict:
    """The tombstone row a removal-registry entry yields (D11)."""
    return {"entity": entity, "id": id, "document_id": document_id, "retired_at": at,
            "publish_id": release, "removal_key": entry["id"],
            "rule": rule_for(entry["reason"]), "reason_code": entry["reason"],
            "public_reason": entry["tombstone"],
            "church_act": render_church_act(entry.get("church_act")), "snapshot": snapshot}


def _redirect(entity: str, *, old_id=None, old_document_id, old_anchor=None, new_id=None,
              new_document_id, new_anchor=None, kind: str, release: str) -> dict:
    return {"entity": entity, "old_id": old_id, "old_document_id": old_document_id,
            "old_anchor": old_anchor, "new_id": new_id, "new_document_id": new_document_id,
            "new_anchor": new_anchor, "kind": kind, "publish_id": release}


def compute(live_passages: list[LivePassage], live_documents: list[LiveDocument],
            staged: list[Document], registry: reg.WorkRegistry, *, release: str,
            at: datetime, tombstoned: list[LivePassage] = ()) -> Retirements:
    """Tombstones, redirects and problems for one stage. `staged` is every staged
    document of the staged collections, with `Passage.id` set. `tombstoned` are the
    retired live passages of those collections that show a tombstone: one whose
    registry redirect has opened since (a merged piece whose text came back in English,
    #399) gets its passage redirect, and the apply drops the tombstone."""
    out = Retirements()
    staged_by_id = {p.id: (d, p) for d in staged for p in d.passages}
    staged_documents = {d.id: d for d in staged}

    removals = reg.open_removals(registry)
    by_id = {e["passage_id"]: e for e in removals
             if e.get("scope") == "passage" and e.get("passage_id")}
    by_anchor = {(e["document_id"], e["anchor"]): e for e in removals
                 if e.get("scope") == "passage" and not e.get("passage_id") and e.get("anchor")}
    removed_documents = {e["document_id"]: e for e in removals if e.get("scope") == "document"}
    redirects: dict[str, list[dict]] = {}
    for r in reg.open_redirects(registry):
        redirects.setdefault(r["old_passage_id"], []).append(r)
    supersedes = {old: w["document_id"] for w in registry.works
                  for old in (w.get("supersedes") or [])}

    # Documents the build no longer emits.
    for d in live_documents:
        if d.id in staged_documents:
            continue
        entry = removed_documents.get(d.id)
        if entry is not None:
            out.tombstones.append(tombstone(
                entry, entity="document", id=d.id, document_id=d.id,
                snapshot=_snapshot(d.collection, d.title, d.author, None, None),
                release=release, at=at))
        elif supersedes.get(d.id) in staged_documents:
            out.redirects.append(_redirect("document", old_id=d.id, old_document_id=d.id,
                                           new_id=supersedes[d.id],
                                           new_document_id=supersedes[d.id], kind="moved",
                                           release=release))
        else:
            out.problems.append(f"document {d.id} ({d.collection}, {d.title!r}) is live, the "
                                "build does not emit it, and no removal entry or "
                                "supersedes explains it")

    def passage_redirect(p: LivePassage, declared: list[dict]) -> None:
        targets = [r["new_passage_id"] for r in declared]
        missing = [t for t in targets if t not in staged_by_id]
        kinds = {r["kind"] for r in declared}
        if missing or len(kinds) != 1:
            out.problems.append(f"passage {p.id}: redirect {sorted(kinds)} to "
                                f"{missing or targets} does not name staged passages "
                                "of one kind")
            return
        d, q = staged_by_id[primary_target(targets, p.document_id, staged_by_id)]
        out.redirects.append(_redirect("passage", old_id=p.id,
                                       old_document_id=p.document_id,
                                       old_anchor=p.anchor, new_id=q.id,
                                       new_document_id=d.id, new_anchor=q.anchor,
                                       kind=kinds.pop(), release=release))

    # Passages the build no longer emits.
    for p in live_passages:
        if p.id in staged_by_id:
            if staged_by_id[p.id][0].id != p.document_id:
                out.moved.append(p.id)
            continue
        # A held document's redirects stay open for its return (1.3d, ADR 0001); while it
        # is held, its removal explains every passage it had.
        declared = None if p.document_id in removed_documents else redirects.get(p.id)
        if declared:
            passage_redirect(p, declared)
            continue
        entry = by_id.get(p.id) or by_anchor.get((p.document_id, p.anchor)) \
            or removed_documents.get(p.document_id)
        if entry is not None:
            out.tombstones.append(tombstone(
                entry, entity="passage", id=p.id, document_id=p.document_id,
                snapshot=_snapshot(p.collection, p.title, p.author, p.reference,
                                   p.chapter_label),
                release=release, at=at))
            continue
        out.problems.append(f"passage {p.id} ({p.collection}, document {p.document_id}, "
                            f"anchor {p.anchor!r}) is live, the build does not emit it, and "
                            "no redirect or removal entry explains it")

    # Retired passages with a tombstone whose redirect has opened since; one the build
    # emits again is un-retired by the apply instead.
    for p in tombstoned:
        declared = None if p.document_id in removed_documents else redirects.get(p.id)
        if declared and p.id not in staged_by_id:
            passage_redirect(p, declared)

    out.redirects += anchor_redirects(live_passages, staged, registry, release)
    out.redirects += chapter_redirects(live_passages, staged, redirects, release)
    return out


def primary_target(targets: list[str], old_document: str,
                   staged_by_id: dict[str, tuple[Document, object]]) -> str:
    """The redirect target a passage or anchor redirect points at: one in the old
    passage's own document first, then the earliest by position (as 0.1c orders them)."""
    return min(targets, key=lambda t: (staged_by_id[t][0].id != old_document,
                                       staged_by_id[t][0].id, staged_by_id[t][1].position))


def anchor_redirects(live_passages: list[LivePassage], staged: list[Document],
                     registry: reg.WorkRegistry, release: str) -> list[dict]:
    """One `anchor` redirect per passage-registry row of the staged documents whose
    anchor or document changed since it was live. A redirected row points at its open
    passage redirect's new anchor, never its own (a piece name the build no longer
    emits, or `<anchor>#moved-<item>`). An old anchor a staged passage of the same
    document still carries resolves directly and gets none."""
    live = {p.id: p for p in live_passages}
    staged_by_id = {p.id: (d, p) for d in staged for p in d.passages}
    carried = {(d.id, p.anchor) for d in staged for p in d.passages}
    staged_documents = {d.id for d in staged}
    open_redirects: dict[str, list[str]] = {}
    for r in reg.open_redirects(registry):
        open_redirects.setdefault(r["old_passage_id"], []).append(r["new_passage_id"])

    out, seen = [], set()
    for row in registry.passages:
        if row["document_id"] not in staged_documents or not row.get("live_anchor"):
            continue
        if row.get("status") == "retired":
            continue
        old_document = live[row["passage_id"]].document_id if row["passage_id"] in live \
            else row["document_id"]
        target_id = row["passage_id"]
        if row.get("status") == "redirected" and row["passage_id"] in open_redirects:
            targets = [t for t in open_redirects[row["passage_id"]] if t in staged_by_id]
            if not targets:
                continue
            target_id = primary_target(targets, old_document, staged_by_id)
        if target_id not in staged_by_id:
            continue
        d, q = staged_by_id[target_id]
        key = (old_document, row["live_anchor"])
        if key == (d.id, q.anchor) or key in carried or key in seen:
            continue
        seen.add(key)
        out.append(_redirect("anchor", old_document_id=old_document,
                             old_anchor=row["live_anchor"], new_document_id=d.id,
                             new_anchor=q.anchor, kind="moved", release=release))
    return out


def chapter_redirects(live_passages: list[LivePassage], staged: list[Document],
                      redirects: dict[str, list[dict]], release: str) -> list[dict]:
    """One `chapter` redirect per live (document, chapter_key) whose passages now mostly
    sit in another document or chapter (0.1c's `chapter_remap`). A chapter key the
    staged document still has resolves directly and gets none."""
    staged_by_id = {p.id: (d, p) for d in staged for p in d.passages}
    staged_chapters = {(d.id, p.chapter_key) for d in staged for p in d.passages}
    old, rows = [], []
    for p in live_passages:
        if p.chapter_key is None:
            continue
        old.append(R.OldPassage(id=p.id, document_id=p.document_id, collection=p.collection,
                                anchor=p.anchor or "", chapter_key=p.chapter_key,
                                reference=p.reference or "", position=p.position, content=""))
        target = p.id
        if p.id not in staged_by_id:
            targets = [r["new_passage_id"] for r in redirects.get(p.id, [])
                       if r["new_passage_id"] in staged_by_id]
            target = primary_target(targets, p.document_id, staged_by_id) if targets else None
        if target in staged_by_id:
            d, q = staged_by_id[target]
            rows.append(R.RemapRow(p.id, "same" if target == p.id else "moved", None,
                                   (target,), None, p.document_id, d.id, p.anchor or "",
                                   q.anchor, p.chapter_key, q.chapter_key, p.collection))
        else:
            rows.append(R.RemapRow(p.id, "removed", None, (), None, p.document_id, None,
                                   p.anchor or "", None, p.chapter_key, None, p.collection))
    out = []
    for c in R.chapter_remap(old, rows):
        old_key = (c["old_document_id"], c["old_chapter_key"])
        new_key = (c["new_document_id"], c["new_chapter_key"])
        if c["new_document_id"] is None or new_key == old_key or old_key in staged_chapters:
            continue
        out.append(_redirect("chapter", old_document_id=old_key[0], old_anchor=old_key[1],
                             new_document_id=new_key[0], new_anchor=new_key[1], kind="moved",
                             release=release))
    return out
