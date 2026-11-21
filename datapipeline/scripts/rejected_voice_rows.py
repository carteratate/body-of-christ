"""Passage-registry rows for the rejected-voice ranges (corpus-cleanup 3.4), generated
from a build.

    cd datapipeline
    python3 scripts/rejected_voice_rows.py [--dry-run]

Builds each collection `registry/rejected_voice_ranges.json` names, expands every range
in reading order, and sets `voice = "rejected"` and the range's label as `unit_label` on
the passage-registry row of each passage in it. Rows that already carry the role from an
earlier item (Exsurge Domine, 1.3d-6; Nestorius's letter, 1.2c) keep it and gain the
label. It refuses to write when a range does not resolve, when a passage in a range has
no row, or when a row of a listed document carries the role outside every range. Run it
again after a merge that changes these documents' anchors or rows; it rewrites the files
rather than leaving them to be merged by hand.
"""
from __future__ import annotations

import argparse
import os
import sys

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from checks.report import placeholder_credentials  # noqa: E402
from publication import build  # noqa: E402
from registry import rejected_voice as rv  # noqa: E402


def updated_rows(rows: list[dict], wanted: dict[tuple[str, str], str],
                 documents: set[str]) -> tuple[list[dict], int]:
    """`rows` with the role and label set on every wanted passage, and how many rows
    changed. ValueError for a wanted passage with no row, or a row of a listed document
    with the role outside every range."""
    by_key = {(r["document_id"], r["anchor"]): r for r in rows}
    missing = sorted(k for k in wanted if k not in by_key)
    if missing:
        raise ValueError(f"no registry row for {missing}; reconcile the registry first")
    stray = sorted((r["document_id"], r["anchor"]) for r in rows
                   if r["document_id"] in documents and r.get("voice") == rv.VOICE
                   and (r["document_id"], r["anchor"]) not in wanted)
    if stray:
        raise ValueError(f"rows carry the rejected voice outside every range: {stray}")
    out, changed = [], 0
    for r in rows:
        label = wanted.get((r["document_id"], r["anchor"]))
        if label is not None and (r.get("voice"), r.get("unit_label")) != (rv.VOICE, label):
            r = {**r, "voice": rv.VOICE, "unit_label": label}
            changed += 1
        out.append(r)
    return out, changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)

    placeholder_credentials()
    reg = registry.load_registry()
    ranges = rv.load_ranges()
    problems = rv.validate(ranges, reg.works)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    wanted: dict[tuple[str, str], str] = {}
    documents = {}
    for collection in sorted({r.collection for r in ranges}):
        built = build(collection, registry=reg)
        documents.update({d.id: d for d in built})
        wanted.update(rv.labels(built, [r for r in ranges if r.collection == collection]))
    rows, changed = updated_rows(reg.passages, wanted, {r.document_id for r in ranges})
    for r in ranges:
        print(f"{r.title}, {r.first_anchor} to {r.last_anchor}: "
              f"{len(rv.expand(documents[r.document_id], r))} passages")
    print(f"{len(wanted)} passages in {len(ranges)} ranges; {changed} rows changed")
    new = registry.WorkRegistry(reg.works, rows, reg.redirects, reg.removals, reg.kept_text, held_texts=reg.held_texts)
    problems = registry.validate(new)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if not args.dry_run and changed:
        registry.write_registry(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
