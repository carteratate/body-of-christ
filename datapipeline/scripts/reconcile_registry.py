"""Bring the passage registry in line with the current build (corpus-cleanup 2.1, C-10).

    cd datapipeline
    python3 scripts/reconcile_registry.py --item <item id> --collection <name> [...]
                                          [--snapshot releases/snapshots/<date>
                                           [--kept-reason TEXT | --kept-reasons FILE]]
                                          [--today YYYY-MM-DD] [--dry-run]

Builds each named collection through SOURCE_BUILDS and runs `registry.reconcile` on it:
a built anchor with no row gets a new row, a piece whose opening unit no longer opens a
piece gets a `merged` redirect to the piece that now holds it, and a redirected piece
that is built again is reclaimed (`added_by` and `closed_by` name `--item`).

A vanished piece whose opening paragraph now spans several pieces needs a person to say
which one holds it. With --snapshot, each is settled by its live text: the piece holding
its opening words, or failing that the one holding most of its text, when exactly one
does.

With --snapshot, a built piece that keeps its ID but no longer holds its live text (under
the release report's stability threshold) is checked the same way: when another piece of
its unit now holds its live opening words, the ID redirects there and the piece takes a
new ID (a cut counted inside a long paragraph, `/from-p26-3`, that moved). When it still
holds its own opening words, the low score has another cause (live text that was mostly
removed notes), which a person states with --kept-reason; the passage is then recorded in
kept_text.json. Without --kept-reason such passages are problems. --kept-reasons names a
JSON file of `{passage_id: reason}` instead, one reviewed reason per passage; a `null`
reason keeps that passage's existing kept_text.json entry as it stands (its text has not
changed since that review), and a passage the file does not name is a problem.

A passage that declares `text_replaced` (a new translation, 1.3c; an amended canon) is
exempt from that check, as from the release report's.

Writes the registry files only when nothing is left unexplained and the result
validates; otherwise prints the problems and exits 1. A Phase 1 item runs it once its
adapter change is done, and commits the registry with that change.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from checks import health as health_cli  # noqa: E402
from publication import SOURCE_BUILDS  # noqa: E402
from identity import unit_anchor  # noqa: E402
from release import remap as R  # noqa: E402

OPENING_WORDS = 8


def settle_by_text(live: dict[str, str]):
    """A `registry.reconcile` settle: the candidate holding the vanished piece's live
    text (`holder_by_text`)."""
    def settle(passage_id: str, candidates: list):
        text = live.get(passage_id)
        return holder_by_text(text, candidates) if text else None
    return settle


def holder_by_text(text: str, candidates: list):
    """The candidate holding `text`'s opening words, else the one holding most of its
    8-word shingles; None on a tie."""
    words = R.words(text)
    opening = " " + " ".join(words[:OPENING_WORDS]) + " "
    found = [c for c in candidates if opening in " " + " ".join(R.words(c.content)) + " "]
    if len(found) == 1:
        return found[0]
    mine = R.shingles(words)
    scores = [len(mine & R.shingles(R.words(c.content))) for c in candidates]
    best = max(scores, default=0)
    return candidates[scores.index(best)] if best and scores.count(best) == 1 else None


def _replaced(passage) -> bool:
    """A passage whose unit's text was replaced on purpose (`text_replaced`: a new
    translation, an amended canon) is not held to its live text, as in the release report."""
    return bool((passage.metadata or {}).get("text_replaced"))


def lost_text(live: dict[str, str]):
    """A `registry.reconcile` moved: for a piece under the stability threshold, the piece
    of its unit that now holds its live text, when that is another piece."""
    def moved(passage_id: str, passage, document):
        text = live.get(passage_id)
        if not text or _replaced(passage) \
                or R.similarity(text, passage.content) >= R.ANCHOR_STABILITY_THRESHOLD:
            return None
        unit = unit_anchor(passage.anchor)
        return holder_by_text(text, [p for p in document.passages
                                     if unit_anchor(p.anchor) == unit])
    return moved


def low_scores(rows: list[dict], documents: list, live: dict[str, str]) -> list[dict]:
    """Built passages that keep a live ID and score under the stability threshold."""
    by_anchor = {(r["document_id"], r["anchor"]): r for r in rows if r["status"] == "active"}
    out = []
    for d in documents:
        for p in d.passages:
            row = by_anchor.get((d.id, p.anchor))
            text = live.get(row["passage_id"]) if row else None
            if text and not _replaced(p) \
                    and R.similarity(text, p.content) < R.ANCHOR_STABILITY_THRESHOLD:
                out.append({"passage_id": row["passage_id"], "document_id": d.id,
                            "anchor": p.anchor})
    return out


def kept_entries(low: list[dict], existing: list[dict], item: str,
                 reason: str | None = None, reasons: dict[str, str | None] | None = None
                 ) -> tuple[list[dict], list[str]]:
    """kept_text.json entries for the low-scoring passages `low`, and the problems left:
    `reason` for every one, or `reasons[passage_id]` for each, where None keeps its
    `existing` entry."""
    prior = {e["passage_id"]: e for e in existing}
    kept, problems = [], []
    for e in low:
        if reasons is not None and e["passage_id"] in reasons:
            why = reasons[e["passage_id"]]
            if why is None and e["passage_id"] in prior:
                kept.append(prior[e["passage_id"]])
            elif why is None:
                problems.append(f"{e['anchor']} ({e['passage_id']}) has no kept_text entry "
                                "to keep; give it a reason")
            else:
                kept.append({**e, "reason": why, "added_by": item})
        elif reason:
            kept.append({**e, "reason": reason, "added_by": item})
        else:
            problems.append(f"{e['anchor']} ({e['passage_id']}) keeps its ID under the "
                            "stability threshold and still holds its opening words; "
                            "give --kept-reason once a person has checked why")
    return kept, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--item", required=True, help="the item making the change, e.g. 1.10b")
    parser.add_argument("--collection", required=True, action="append",
                        choices=sorted(SOURCE_BUILDS))
    parser.add_argument("--snapshot", help="settle ambiguous pieces by their live text")
    reason = parser.add_mutually_exclusive_group()
    reason.add_argument("--kept-reason",
                        help="why passages that still hold their live text score low")
    reason.add_argument("--kept-reasons", metavar="FILE",
                        help="a JSON file of {passage_id: reason}, reviewed one by one")
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    reg = registry.load_registry()
    documents = [d for c in args.collection for d in SOURCE_BUILDS[c]()]
    settle = moved = None
    live: dict[str, str] = {}
    if args.snapshot:
        snapshot = health_cli.load_snapshot(args.snapshot, args.collection)
        live = {p.metadata["passage_id"]: p.content
                for docs in snapshot.values() for d in docs for p in d.passages}
        settle, moved = settle_by_text(live), lost_text(live)
    rec = registry.reconcile(reg, documents, item=args.item, today=args.today,
                             settle=settle, moved=moved)
    problems = list(rec.problems)
    # With live text, the rebuilt documents' entries are found again; without it they
    # stand as recorded.
    rebuilt = {d.id for d in documents} if live else set()
    kept = [e for e in reg.kept_text if e["document_id"] not in rebuilt]
    reasons = None
    if args.kept_reasons:
        with open(args.kept_reasons, encoding="utf-8") as f:
            reasons = json.load(f)
    found, unexplained = kept_entries(low_scores(rec.rows, documents, live), reg.kept_text,
                                      args.item, args.kept_reason, reasons)
    kept += found
    problems += unexplained
    kept.sort(key=lambda e: (e["document_id"], e["anchor"]))
    updated = registry.WorkRegistry(reg.works, rec.rows, rec.redirects, reg.removals, kept, held_texts=reg.held_texts)
    problems += registry.validate(updated)

    before = {r["passage_id"]: r["status"] for r in reg.passages}
    changes = Counter()
    for r in rec.rows:
        old = before.get(r["passage_id"])
        if old is None:
            changes["new rows"] += 1
        elif old != r["status"]:
            changes[f"{old} -> {r['status']}"] += 1
    opened = sum(1 for r in rec.redirects if r.get("added_by") == args.item
                 and not r.get("closed_by"))
    closed = sum(1 for r in rec.redirects if r.get("closed_by") == args.item)
    moves = sum(1 for r in rec.redirects if r.get("added_by") == args.item
                and r["kind"] == "moved" and not r.get("closed_by"))
    print(f"{args.item}: {dict(changes) or 'no row changes'}; open redirects it added "
          f"{opened} ({moves} for text that moved), closed {closed}; kept text "
          f"{len(kept)}")
    for p in problems:
        print(f"problem: {p}")
    if problems:
        return 1
    if not args.dry_run:
        registry.write_registry(updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
