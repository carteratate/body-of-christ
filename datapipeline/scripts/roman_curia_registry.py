"""Register the Roman Curia documents (corpus-cleanup 5.3a) in the work registry.

    cd datapipeline
    python3 scripts/roman_curia_registry.py [--today YYYY-MM-DD]

Adds a works.json entry for each of the 60 documents, freezing its document ID under its
source key (`roman-curia/<file>`), and marks each one's rights-inventory row built: the
document ID filled in, `planned_for` cleared, and the author the office the page prints. Rows are found by source path and title.
Idempotent. Then, as for any adapter change:

    python3 scripts/reconcile_registry.py --item 5.3a --collection roman-curia
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
from ingest import roman_curia  # noqa: E402


def register(reg: registry.WorkRegistry, documents, today: str) -> int:
    """Register each document's work unless it is; the number registered."""
    added = 0
    for document in documents:
        if (document.collection, document.metadata["source_key"]) in reg.document_by_key:
            continue
        registry.register_new_work(reg, document, today)
        added += 1
    return added


def mark_built(rows: list[dict], documents) -> int:
    """Fill each document's ID into its rights row and clear `planned_for`, and set the
    row's author to the office the page prints (5 rows named the Sacred Congregation for
    pages that print the Congregation); the number of rows changed. Raises when a row
    names another document or is missing."""
    changed = 0
    for document in documents:
        path = document.metadata["source_key"]
        matches = [r for r in rows if r["source_path"] == path and r["work"] == document.title]
        if len(matches) != 1:
            raise ValueError(f"{path}: {len(matches)} rights rows titled {document.title!r}")
        row = matches[0]
        if row["document_id"] not in (None, document.id):
            raise ValueError(f"{path}: its row names document {row['document_id']}")
        if (row["document_id"], row["planned_for"], row["author"]) == \
                (document.id, None, document.author):
            continue
        row["document_id"], row["planned_for"], row["author"] = document.id, None, document.author
        changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    documents = roman_curia.build_documents()
    reg = registry.load_registry()
    added = register(reg, documents, args.today)
    if added:
        problems = registry.validate(reg)
        if problems:
            print("\n".join(problems))
            return 1
        registry.write_registry(reg)
        print(f"registered {added} Roman Curia documents")
    rows = rights_inventory.load()
    changed = mark_built(rows, documents)
    if changed:
        rights_inventory.INVENTORY_PATH.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"marked {changed} rights-inventory rows built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
