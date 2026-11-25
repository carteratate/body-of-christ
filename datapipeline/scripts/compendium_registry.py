"""Register the Compendium of the Catechism (corpus-cleanup 5.5) in the work registry.

    cd datapipeline
    python3 scripts/compendium_registry.py [--today YYYY-MM-DD]

Adds the works.json entry that freezes the Compendium's document ID under its source key
(`catechism/compendium`), and marks its rights-inventory row built: the document ID filled
in and `planned_for` cleared. Idempotent: a registered work and a built row are left as
they are. Then, as for any adapter change:

    python3 scripts/reconcile_registry.py --item 5.5 --collection catechism
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
from ingest import catechism_compendium  # noqa: E402


def register(reg: registry.WorkRegistry, document, today: str) -> bool:
    """Register the document's work unless it is; True when the registry changed."""
    if (document.collection, document.metadata["source_key"]) in reg.document_by_key:
        return False
    registry.register_new_work(reg, document, today)
    return True


def mark_built(rows: list[dict], document) -> bool:
    """Fill the document ID into its rights row (found by source path and title) and clear
    `planned_for`; True when the row changed. Raises when the row names another
    document."""
    path = f"catechism/{catechism_compendium.SOURCE_FILE}"
    row = next(r for r in rows if r["source_path"] == path and r["work"] == document.title)
    if row["document_id"] not in (None, document.id):
        raise ValueError(f"{path}: its row names document {row['document_id']}")
    if row["document_id"] == document.id and row["planned_for"] is None:
        return False
    row["document_id"], row["planned_for"] = document.id, None
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    document = catechism_compendium.build_document()
    reg = registry.load_registry()
    if register(reg, document, args.today):
        problems = registry.validate(reg)
        if problems:
            print("\n".join(problems))
            return 1
        registry.write_registry(reg)
        print(f"registered {document.title} as {document.id}")
    rows = rights_inventory.load()
    if mark_built(rows, document):
        rights_inventory.INVENTORY_PATH.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("marked its rights-inventory row built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
