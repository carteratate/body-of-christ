"""Register corpus-cleanup 5.4's documents in the work registry (#203).

    cd datapipeline
    python3 scripts/universal_law_registry.py [--today YYYY-MM-DD]

Adds the works.json entries that freeze the five new documents' IDs under their source
keys: Ubicumque et Semper and Amoris Laetitia (papal), and Universi Dominici Gregis as
amended in 2013, its 1996 original and Normas Nonnullas (Church law). Marks each one's
rights-inventory row built (the document ID filled in, `planned_for` cleared) and drops
the rows of the two works 5.4 does not add (A New Hope for Lebanon and De aliquibus
mutationibus, both excluded by rule E as revised on 29 Oct 2026; Carter, 23 Nov 2026).

Once the entries carry their facts, a second run points each history document at the
current text (`superseded_by`, `superseded_note`; rule F, D5), which
`document_facts.derive` keeps. Idempotent. The order, as for any adapter change:

    python3 scripts/universal_law_registry.py
    python3 scripts/reconcile_registry.py --item 5.4 --collection apostolic-exhortations \
        --collection papal-documents --collection church-law
    python3 scripts/document_facts_registry.py
    python3 scripts/universal_law_registry.py    # the supersession
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
from ingest import universal_law  # noqa: E402
from publication import SOURCE_BUILDS  # noqa: E402

# The papal documents 5.4 adds, by source and manifest slug.
PAPAL = (("apostolic-exhortations", "amoris-laetitia"),
         ("papal-documents", "ubicumque-et-semper"))
# Rows of works 5.4 does not add (rule E): (source_path, work).
EXCLUDED = (("apostolic-exhortations/a-new-hope-for-lebanon.html", "A New Hope for Lebanon"),
            ("church-law/de-aliquibus-mutationibus.html",
             "De aliquibus mutationibus in normis de electione Romani Pontificis"))
# Each history document's label, shown with a link to the current text (D5).
SUPERSEDED_NOTES = {
    universal_law.ORIGINAL.slug: "Superseded text, kept as history: the constitution as "
                                 "promulgated in 1996, before its amendments of 2007 and "
                                 "2013.",
    universal_law.NORMAS.slug: "Superseded text, kept as history: the changes this motu "
                               "proprio made are in the current text of Universi Dominici "
                               "Gregis.",
}


def documents() -> list:
    papal = [d for source, slug in PAPAL for d in SOURCE_BUILDS[source]()
             if d.metadata["source_key"] == f"{source}/{slug}"]
    return papal + SOURCE_BUILDS[universal_law.COLLECTION]()


def register(reg: registry.WorkRegistry, docs: list, today: str) -> bool:
    """Register each document unless it is, and point the history documents at the
    current text; True when the registry changed."""
    changed = False
    for d in docs:
        if (d.collection, d.metadata["source_key"]) not in reg.document_by_key:
            registry.register_new_work(reg, d, today)
            changed = True
    entries = [reg.entry_by_document[reg.document_by_key[
        (universal_law.COLLECTION, f"{universal_law.COLLECTION}/{slug}")]]
        for slug in SUPERSEDED_NOTES]
    if not all(registry.has_facts(e) for e in entries):
        print("run scripts/document_facts_registry.py, then this again for the supersession")
        return changed
    current = reg.document_by_key[(universal_law.COLLECTION,
                                   f"{universal_law.COLLECTION}/{universal_law.CURRENT.slug}")]
    for entry, note in zip(entries, SUPERSEDED_NOTES.values()):
        if entry.get("superseded_by") != current or entry.get("superseded_note") != note:
            entry["superseded_by"], entry["superseded_note"] = current, note
            changed = True
    return changed


def mark_built(rows: list[dict], docs: list) -> bool:
    """Fill each document's ID into its rights row (found by source path) and clear
    `planned_for`, and drop the excluded works' rows; True when the rows changed. Raises
    when a row names another document."""
    changed = False
    for d in docs:
        path = f"{d.collection}/{d.metadata['source_file']}" \
            if d.collection == universal_law.COLLECTION else \
            f"{d.collection}/{_manifest_file(d)}"
        row = next(r for r in rows if r["source_path"] == path)
        if row["document_id"] not in (None, d.id):
            raise ValueError(f"{path}: its row names document {row['document_id']}")
        # A row is filed under the source its document is built from (5.2 filed the two
        # papal rows under the new key `papal`).
        if (row["document_id"], row["planned_for"], row["collection"]) != (d.id, None,
                                                                           d.collection):
            row["document_id"], row["planned_for"], row["collection"] = d.id, None, \
                d.collection
            changed = True
    for path, work in EXCLUDED:
        kept = [r for r in rows if not (r["source_path"] == path and r["work"] == work)]
        if len(kept) != len(rows):
            rows[:] = kept
            changed = True
    rows.sort(key=lambda r: (*rights_inventory.key(r)[:3], r["author"] or ""))
    return changed


def _manifest_file(d) -> str:
    source, slug = d.metadata["source_key"].split("/", 1)
    with open(os.path.join(DATAPIPELINE, "sources", source, "manifest.json"),
              encoding="utf-8") as f:
        return next(e["file"] for e in json.load(f) if e["slug"] == slug)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    docs = documents()
    reg = registry.load_registry()
    if register(reg, docs, args.today):
        problems = registry.validate(reg)
        if problems:
            print("\n".join(problems))
            return 1
        registry.write_registry(reg)
        print("registry updated")
    rows = rights_inventory.load()
    if mark_built(rows, docs):
        rights_inventory.INVENTORY_PATH.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("marked their rights-inventory rows built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
