"""Register John of the Cross's treatises (corpus-cleanup 5.6c) in the work registry.

    cd datapipeline
    python3 scripts/john_of_the_cross_registry.py [--today YYYY-MM-DD]

For each treatise `ingest.john_of_the_cross.TREATISES` builds, adds the works.json entry
that freezes its document ID under its source key
(`theologians/<scan>/<slug>`), and marks its rights-inventory row built: the document ID
filled in, `planned_for` cleared and its collection set to the build's source key
(`medieval` until 5.1b.4). Idempotent. Then, as for any adapter change:

    python3 scripts/reconcile_registry.py --item 5.6c --collection medieval
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
from ingest import john_of_the_cross  # noqa: E402


def register(reg: registry.WorkRegistry, document, today: str) -> bool:
    """Register the document's work unless it is; True when the registry changed."""
    if (document.collection, document.metadata["source_key"]) in reg.document_by_key:
        return False
    registry.register_new_work(reg, document, today)
    return True


def mark_built(rows: list[dict], document, scan: str) -> bool:
    """Fill the document ID into its rights row (found by source path and title) and clear
    `planned_for`; True when the row changed. Raises when the row names another
    document."""
    path = f"theologians/{scan}/"
    row = next((r for r in rows if r["source_path"] == path and r["work"] == document.title), None)
    if row is None:
        raise ValueError(f"{path}: no rights-inventory row for {document.title!r}")
    if row["document_id"] not in (None, document.id):
        raise ValueError(f"{path}: its row names document {row['document_id']}")
    if (row["document_id"], row["planned_for"], row["collection"]) == (document.id, None,
                                                                    document.collection):
        return False
    # The row is filed under the source key the work is built and registered by.
    row["document_id"], row["planned_for"] = document.id, None
    row["collection"] = document.collection
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    reg = registry.load_registry()
    rows = rights_inventory.load()
    changed_reg = changed_rows = False
    for treatise in john_of_the_cross.TREATISES:
        document = john_of_the_cross.build_document(treatise)
        if register(reg, document, args.today):
            changed_reg = True
            print(f"registered {document.title} as {document.id}")
        if mark_built(rows, document, treatise.scan):
            changed_rows = True
            print(f"marked the rights-inventory row of {document.title} built")
    if changed_reg:
        problems = registry.validate(reg)
        if problems:
            print("\n".join(problems))
            return 1
        registry.write_registry(reg)
    if changed_rows:
        rows.sort(key=rights_inventory.key)   # a row's collection is part of its key
        rights_inventory.INVENTORY_PATH.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
