"""Registry changes for On the Incarnation's move from Lawson's translation to Robertson's
(corpus-cleanup 1.8d), generated from a build.

    cd datapipeline
    python3 scripts/incarnation_registry.py --snapshot releases/snapshots/<date>
                                            [--today YYYY-MM-DD] [--dry-run]

Builds the Church Fathers and writes, in place of what 1.8d wrote before:

- the work's works.json entry under its new source key, `npnf204.xml#vii.ii`, so the
  document keeps its frozen ID `cf235300…`;
- for each live passage of Lawson's text (47), a redirect to the Robertson section whose
  number is the first "(N)" marker in its text, or, for a passage that prints none, the
  section it continues (the last marker before it). `split` when its text runs over more
  than one section, `moved` when it lies in one. The redirects are the whole explanation
  for the old IDs: no removal entries (spec). The redirects earlier items wrote into
  Lawson's passages follow on to the same targets;
- rule G's removals in Robertson's text, through `scripts/editorial_removals.py`
  (`item="1.8d"`): a `span` entry for each section's analytical heading (Robertson's
  italic summary), and a `class` entry counting the heading lines (the work's title and
  rule line over §1, §5's number);
- 1.10b's note count for the document, in step with Robertson's notes;

then runs `registry.reconcile` (rows for the 59 new passages) and writes the registry
when it validates.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from collections import Counter
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import identity  # noqa: E402
import registry  # noqa: E402
from ingest import editorial  # noqa: E402
from publication import build  # noqa: E402
from scripts import editorial_removals as er  # noqa: E402

ITEM = "1.8d"
COLLECTION = "church-fathers"
DOCUMENT_ID = "cf235300-e37d-5a7a-a421-f50efff38355"
OLD_KEY = f"{COLLECTION}/incarnation.xml"
NEW_KEY = f"{COLLECTION}/npnf204.xml#vii.ii"
WORK_DIV = "vii.ii"
# Lawson prints the section numbers inline: "(1) In our former book…".
MARKER = re.compile(r"\((\d{1,2})\)")
SECTIONS = 57
REASON = ("Lawson's translation, which is under copyright, was replaced by Robertson's "
          "(1.8d): section {n} holds {what}")
# Pieces 1.10b cut from Lawson's text that were never published, so no snapshot holds
# their text: by passage ID, (section, kind, prints a marker). Read once, by
# `section_targets` over a build of incarnation.xml at master 047867d, since the file
# leaves the sources with this item.
UNPUBLISHED = {
    "6084a2cc-7d4b-52a4-98a3-d1e3a248080a": (18, "moved", False),    # iv/from-p16
    "02d2225e-62bd-5792-99ac-64025bba8efa": (28, "moved", True),     # vi/from-p5
    "d4c462e3-c0b1-5817-b322-4d9f44ba90ff": (39, "moved", True),     # vii/from-p10
    "1688d3b8-c03c-5fda-84bf-b2ed81eb842b": (34, "split", True),     # vii/from-p4
    "3e717629-be43-54e7-9f8e-03c331792c03": (36, "split", True),     # vii/from-p6
}


def pin(reg: registry.WorkRegistry) -> registry.WorkRegistry:
    """The registry with the work's entry under Robertson's source key."""
    works = [{**w, "source_key": NEW_KEY} if w["document_id"] == DOCUMENT_ID else w
             for w in reg.works]
    return registry.WorkRegistry(works, reg.passages, reg.redirects, reg.removals,
                                 reg.kept_text, held_texts=reg.held_texts)


def lawson_passages(snapshot_dir: str) -> list[dict]:
    """The live passages of the document, in reading order."""
    with gzip.open(os.path.join(snapshot_dir, "passages.jsonl.gz"), "rt",
                   encoding="utf-8") as f:
        rows = [r for r in map(json.loads, f) if r.get("document_id") == DOCUMENT_ID]
    return sorted(rows, key=lambda r: r["position"])


def _opens_section(content: str, marker: re.Match) -> bool:
    """True when nothing but Lawson's chapter title stands before `marker`."""
    before = [line for line in content[:marker.start()].splitlines() if line.strip()]
    return all(len(line) < 80 and not re.search(r"[.,;:?!]", line) for line in before)


def section_targets(passages: list[dict]) -> dict[str, tuple[int, str, bool]]:
    """Each live passage's target section, redirect kind, and whether it prints a marker,
    by passage ID: the first marker it prints, else the section it continues; `split`
    when it holds text of more than one section."""
    out = {}
    current = None
    for p in passages:
        markers = list(MARKER.finditer(p["content"]))
        numbers = [int(m.group(1)) for m in markers]
        if any(not 1 <= n <= SECTIONS for n in numbers) or numbers != sorted(set(numbers)) \
                or (current is not None and numbers and numbers[0] <= current):
            raise ValueError(f"{p['id']}: markers {numbers} out of order after ({current})")
        if not numbers and current is None:
            raise ValueError(f"{p['id']}: no marker and no section before it")
        spans = set(numbers)
        if current is not None and not (numbers and _opens_section(p["content"], markers[0])):
            spans.add(current)
        out[p["id"]] = (numbers[0] if numbers else current,
                        "split" if len(spans) > 1 else "moved", bool(numbers))
        current = numbers[-1] if numbers else current
    return out


def _roman(n: int) -> str:
    out = ""
    for value, numeral in ((50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"),
                           (4, "iv"), (1, "i")):
        while n >= value:
            out, n = out + numeral, n - value
    return out


def redirects(reg: registry.WorkRegistry, document, passages: list[dict], today: str):
    """The rows and redirects with every passage of Lawson's text redirected into
    Robertson's sections: the live ones by their live text, the unpublished ones by
    `UNPUBLISHED`. A redirect an earlier item wrote from a live passage (1.10b's merges,
    never applied) closes: the live text decides where its ID goes."""
    first = {}
    for p in document.passages:
        first.setdefault(p.chapter_key, p.anchor)
    targets = {**section_targets(passages), **UNPUBLISHED}
    rows = [dict(r) for r in reg.passages]
    out = [dict(r) for r in reg.redirects
           if not (r.get("added_by") == ITEM and r["document_id"] == DOCUMENT_ID)]
    for r in out:                    # reopen what a previous run closed
        if r.get("closed_by") == ITEM:
            del r["closed_by"], r["closed_on"]
    lawson = {r["passage_id"] for r in rows if r["document_id"] == DOCUMENT_ID
              and not r["anchor"].startswith(WORK_DIV + ".")}
    if lawson != set(targets):
        raise ValueError(f"Lawson rows without a target: {sorted(lawson - set(targets))}; "
                         f"targets without a row: {sorted(set(targets) - lawson)}")
    for r in out:
        if r["old_passage_id"] in lawson and not r.get("closed_by"):
            r["closed_by"], r["closed_on"] = ITEM, today
    for r in rows:
        if r["passage_id"] not in lawson:
            continue
        if r["status"] == "retired":
            raise ValueError(f"{r['passage_id']}: retired, not redirected")
        n, kind, marked = targets[r["passage_id"]]
        anchor = first[f"{WORK_DIV}.{_roman(n)}"]
        what = ("the text it continued" if not marked else
                "its text" if kind == "moved" else "the first section number it printed")
        r["status"] = "redirected"
        out.append({"document_id": DOCUMENT_ID, "old_passage_id": r["passage_id"],
                    "old_anchor": r["anchor"],
                    "new_passage_id": identity.passage_id(DOCUMENT_ID, anchor),
                    "new_anchor": anchor, "kind": kind,
                    "reason": REASON.format(n=n, what=what), "added_by": ITEM})
    return rows, out


def class_entries(removals: list[dict], document, today: str) -> list[dict]:
    """1.10b's note count for the document, in step with the build."""
    n = sum((p.metadata or {}).get("editor_note_count", 0) for p in document.passages)
    out = []
    for e in removals:
        if e["document_id"] == DOCUMENT_ID and e["scope"] == "class" \
                and (e.get("span") or {}).get("rule") == "common._p_text_without_notes":
            e = {**e, "span": {**e["span"], "count": n}}
        out.append(e)
    return out


def plan(reg: registry.WorkRegistry, snapshot_dir: str, today: str):
    """The updated registry, this item's removal entries and any problems."""
    reg = pin(reg)
    previous = registry.activate(reg)
    try:
        with editorial.recording() as log:
            documents = build(COLLECTION)
    finally:
        registry.activate(previous)
    document = next(d for d in documents if d.id == DOCUMENT_ID)
    if document.metadata["source_key"] != NEW_KEY:
        return None, [], [f"{DOCUMENT_ID} is built from {document.metadata['source_key']}"]
    passages = lawson_passages(snapshot_dir)
    rows, redirected = redirects(reg, document, passages, today)
    base = registry.WorkRegistry(reg.works, rows, redirected, reg.removals, reg.kept_text, held_texts=reg.held_texts)
    live = er.live_text(snapshot_dir)
    entries, found, problems = er.generate(base, documents, log, live, today, item=ITEM)
    staged, unreviewed = er.plan(base, entries, found, item=ITEM)
    if staged is None:
        return None, entries, [f"unreviewed judgment: {u}" for u in unreviewed]
    staged = registry.WorkRegistry(staged.works, staged.passages, staged.redirects,
                                   class_entries(staged.removals, document, today),
                                   staged.kept_text, held_texts=staged.held_texts)
    rec = registry.reconcile(staged, [document], item=ITEM, today=today)
    problems += rec.problems
    updated = registry.WorkRegistry(staged.works, rec.rows, rec.redirects, staged.removals,
                                    staged.kept_text, held_texts=staged.held_texts)
    problems += registry.validate(updated)
    return updated, entries, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    updated, entries, problems = plan(registry.current(), args.snapshot, args.today)
    print(Counter((e["scope"], e["reason"]) for e in entries))
    for p in problems:
        print(f"problem: {p}")
    if problems or updated is None:
        return 1
    print(Counter(r["kind"] for r in updated.redirects if r.get("added_by") == ITEM))
    if not args.dry_run:
        registry.write_registry(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
