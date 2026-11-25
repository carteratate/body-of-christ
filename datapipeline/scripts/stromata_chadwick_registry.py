"""Registry changes for Stromata III's return in Henry Chadwick's English (#399).

    cd datapipeline
    python3 scripts/stromata_chadwick_registry.py [--today YYYY-MM-DD] [--dry-run]

3.3 retired Book III's 33 passages under rule E (rm-4002 to rm-4035, 34 entries: one
more for the earlier live piece 1.10c had merged into one of them). With the passages
built again from Chadwick's translation (`ingest/stromata_chadwick.py`), this:

- closes those 34 entries (`closed_by` "#399"), kept as the record;
- sets the 33 built passages' rows `active` again, with their IDs;
- sets the merged piece (`…/introduction/p12`, anchor `vi.iv.iii/from-p67-2`) back to
  `redirected`, with a new `merged` redirect to the passage that holds its opening,
  `vi.iv.iii/from-p67`, as 1.10c had it before 3.3 closed that redirect;

then checks that the build agrees and writes the registry when it validates. A rerun
changes nothing.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from ingest.stromata_chadwick import PIECES, STROMATA  # noqa: E402

ITEM = "#399"
REMOVALS = tuple(f"rm-{n}" for n in range(4002, 4036))
MERGED = "6ecf68f1-eb0d-5976-9b43-8fe77b7edd50"     # …/introduction/p12
MERGED_INTO = "vi.iv.iii/from-p67"


def plan_check(reg: registry.WorkRegistry) -> None:
    """The entries and rows this item changes are the ones it expects."""
    entries = {e["id"]: e for e in reg.removals}
    for name in REMOVALS:
        e = entries.get(name)
        if e is None or e["document_id"] != STROMATA or e["scope"] != "passage" \
                or e["added_by"] != "3.3":
            raise ValueError(f"{name}: not 3.3's entry for a Stromata passage")
        if e.get("closed_by") not in (None, ITEM):
            raise ValueError(f"{name}: closed by {e['closed_by']}")
    built = {registry.resolve_passage_id(STROMATA, a, reg) for a, _, _ in PIECES}
    retired = {entries[n]["passage_id"] for n in REMOVALS}
    if retired != built | {MERGED}:
        raise ValueError("rm-4002 to rm-4035 do not name the 33 built passages and the "
                         "merged piece")


def apply(reg: registry.WorkRegistry, today: str) -> None:
    plan_check(reg)
    closing = set(REMOVALS)
    for e in reg.removals:
        if e["id"] in closing and not e.get("closed_by"):
            e["closed_by"], e["closed_on"] = ITEM, today
    built = {registry.resolve_passage_id(STROMATA, a, reg) for a, _, _ in PIECES}
    into = registry.resolve_passage_id(STROMATA, MERGED_INTO, reg)
    for r in reg.passages:
        if r["passage_id"] in built:
            r["status"] = "active"
        elif r["passage_id"] == MERGED:
            r["status"] = "redirected"
            row = r
    if not any(x["old_passage_id"] == MERGED and not x.get("closed_by")
               for x in reg.redirects):
        reg.redirects.append({
            "document_id": STROMATA, "old_passage_id": MERGED, "old_anchor": row["anchor"],
            "new_passage_id": into, "new_anchor": MERGED_INTO, "kind": "merged",
            "reason": "its opening unit no longer opens a piece", "added_by": ITEM})
        reg.redirects.sort(key=lambda x: (x["document_id"], x["old_anchor"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    reg = registry.current()
    apply(reg, args.today)
    problems = registry.validate(reg)
    if problems:
        raise SystemExit("registry invalid:\n" + "\n".join(problems[:20]))
    registry.activate(reg)
    from ingest.church_fathers import build_all
    stromata = next(d for d in build_all() if d.id == STROMATA)
    anchors = {p.anchor for p in stromata.passages}
    missing = [a for a, _, _ in PIECES if a not in anchors]
    if missing:
        raise SystemExit(f"not built: {missing}")
    print(f"closed {len(REMOVALS)} removal entries, {len(PIECES)} passages active, "
          f"{MERGED} redirected to {MERGED_INTO}")
    if not args.dry_run:
        registry.write_registry(reg)


if __name__ == "__main__":
    main()
