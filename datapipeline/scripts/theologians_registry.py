"""Register 5.6b's theologians and spiritual writers (corpus-cleanup 5.6b, #207) in the
work registry.

    cd datapipeline
    python3 scripts/theologians_registry.py [--today YYYY-MM-DD]

For each work in `ingest.theologians.WORKS`, adds the works.json entry that freezes its
document ID under its source key (`theologians/<file>`), and marks its rights-inventory
row built: the document ID filled in, `planned_for` cleared, and the collection set to the
one it is built under (`ingest.theologians.COLLECTION`). The row is found by its source
path and title. Idempotent: a registered work and a built row are left as they are. Then,
as for any adapter change:

    python3 scripts/reconcile_registry.py --item 5.6b --collection medieval
    python3 scripts/document_facts_registry.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
import rights_inventory  # noqa: E402
from ingest import theologians  # noqa: E402


def register(reg: registry.WorkRegistry, document, today: str) -> bool:
    """Register the document's work unless it is; True when the registry changed."""
    if (document.collection, document.metadata["source_key"]) in reg.document_by_key:
        return False
    registry.register_new_work(reg, document, today)
    return True


def mark_built(rows: list[dict], document) -> bool:
    """Fill the document ID and collection into its rights row and clear `planned_for`;
    True when the row changed. Raises when the row names another document."""
    path = document.metadata["source_key"]
    row = next(r for r in rows if r["source_path"] == path and r["work"] == document.title)
    if row["document_id"] not in (None, document.id):
        raise ValueError(f"{path}: its row names document {row['document_id']}")
    built = {"document_id": document.id, "planned_for": None,
             "collection": document.collection}
    if all(row[k] == v for k, v in built.items()):
        return False
    row.update(built)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    documents = theologians.build_documents()
    reg = registry.load_registry()
    added = [d for d in documents if register(reg, d, args.today)]
    if added:
        problems = registry.validate(reg)
        if problems:
            print("\n".join(problems))
            return 1
        registry.write_registry(reg)
        for d in added:
            print(f"registered {d.title} as {d.id}")
    rows = rights_inventory.load()
    marked = [d for d in documents if mark_built(rows, d)]
    if marked:
        rows.sort(key=lambda r: tuple(x or "" for x in rights_inventory.key(r)))
        rights_inventory.INVENTORY_PATH.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"marked {len(marked)} rights-inventory rows built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
