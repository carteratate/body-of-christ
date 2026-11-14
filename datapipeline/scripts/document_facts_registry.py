"""Document facts in the work registry (corpus-cleanup 2.3), generated from a build.

    cd datapipeline
    python3 scripts/document_facts_registry.py [--check]

Builds every collection with its adapter (needs the vendored sources), derives each
document's facts (`document_facts.derive`) from the build, its rights-inventory row and
its works.json entry, and writes them onto the entry (`registry.FACT_FIELDS`). Only
works.json changes. A document an open `document` removal holds builds nothing and keeps
no facts. Rerun it after a change to an adapter's year, notes or genre, to a rights
row's credit line, or to a rule in `document_facts.py`; it is idempotent.

`--check` writes nothing and exits 1 when works.json differs from what it would write.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import document_facts  # noqa: E402
import registry  # noqa: E402
import rights_inventory  # noqa: E402
from publication import SOURCE_ADAPTERS  # noqa: E402


def build_all(reg: registry.WorkRegistry) -> list:
    """Every document the adapters build, before the registry's facts are applied."""
    held = registry.removed_document_ids(reg)
    return [registry.drop_removed(d, reg) for c in SOURCE_ADAPTERS
            for d in SOURCE_ADAPTERS[c]() if d.id not in held]


def generate(reg: registry.WorkRegistry, documents: list, rows: list[dict]) -> list[dict]:
    """The works.json entries with each built document's facts, in file order. An entry
    for a document the build does not emit loses any facts it had."""
    by_document = rights_inventory.by_document_id(rows)
    built = {d.id: d for d in documents}
    works = []
    for w in reg.works:
        entry = {k: v for k, v in w.items() if k not in registry.FACT_FIELDS}
        d = built.get(w["document_id"])
        if d is not None:
            entry.update(document_facts.derive(d, by_document.get(d.id), w))
        works.append(entry)
    return works


def dump(works: list[dict]) -> str:
    return json.dumps(works, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 if works.json would change")
    args = parser.parse_args(argv)

    reg = registry.load_registry()
    works = generate(reg, build_all(reg), rights_inventory.load())
    path = os.path.join(registry.REGISTRY_DIR, registry.WORKS_FILE)
    with open(path, encoding="utf-8") as f:
        current = f.read()
    text = dump(works)
    if args.check:
        if text != current:
            print("works.json differs from the build's document facts; run "
                  "scripts/document_facts_registry.py")
            return 1
        print("works.json document facts match the build")
        return 0
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    filled = sum(registry.has_facts(w) for w in works)
    print(f"document facts written for {filled} of {len(works)} works.json entries")
    problems = registry.validate(registry.load_registry())
    for p in problems:
        print(f"  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
