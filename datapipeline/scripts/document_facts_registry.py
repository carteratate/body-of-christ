"""Document facts in the work registry (corpus-cleanup 2.3), generated from a build.

    cd datapipeline
    python3 scripts/document_facts_registry.py [--check]

Builds every collection with its adapter (needs the vendored sources), derives each
document's facts (`document_facts.derive`) from the build, its rights-inventory row and
its works.json entry, and writes them onto the entry (`registry.FACT_FIELDS`). It also
writes 3.2's labels (`attributions.py`): the entry's `attribution` (`credited_as`,
`certainty`, `clavis`, `basis`), its `works` rows (the build's works, labelled), and the
passage rows' `work_key` and chapter notes. A document an open `document` removal holds,
or one the build no longer emits, keeps no facts and no labels, and a work the build no
longer emits keeps its row (retired passages still name it) without labels. Rerun it
after a change to an adapter's year, notes, genre or works, to a rights row's credit
line, or to a rule in `document_facts.py` or `attributions.py`; it is idempotent.

`--check` writes nothing and exits 1 when works.json differs from what it would write.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import attributions  # noqa: E402
import document_facts  # noqa: E402
import registry  # noqa: E402
import rights_inventory  # noqa: E402
from publication import SOURCE_BUILDS  # noqa: E402


def build_all(reg: registry.WorkRegistry) -> list:
    """Every document the adapters build, before the registry's facts are applied."""
    held = registry.removed_document_ids(reg)
    return [registry.drop_removed(d, reg) for c in SOURCE_BUILDS
            for d in SOURCE_BUILDS[c]() if d.id not in held]


def _attribution(w: dict, built: bool) -> dict:
    labels = attributions.DOCUMENTS.get(w["work_id"], {}) if built else {}
    return {**w["attribution"], **{k: labels.get(k) for k in attributions.ATTRIBUTION_KEYS}}


def _works(w: dict, d) -> list[dict]:
    """The entry's `works` rows: the build's works, each with 3.2's labels; a row the build
    no longer emits stays, unlabelled, keeping its ordinal."""
    rows = {x["work_key"]: x for x in w.get("works", [])}
    built = {x.work_key: x for x in (d.works if d is not None else [])}
    # A work new to the entry follows the ones it already holds, in the build's order.
    last = max((x["ordinal"] for x in rows.values()), default=0)
    new = {k: last + i for i, k in enumerate((k for k in built if k not in rows), 1)}
    out = []
    for key in list(rows) + list(new):
        if key in built:
            row = dataclasses.asdict(built[key])
            row["ordinal"] = rows[key]["ordinal"] if key in rows else new[key]
            row.update(document_facts.work_facts(w["work_id"], key))
            row.update(attributions.WORKS.get((w["work_id"], key), {}))
        else:
            row = {**rows[key], **{k: None for k in registry.WORK_LABELS}}
            row.pop("basis", None)
        out.append(row)
    out.sort(key=lambda x: x["ordinal"])
    ordinals = [x["ordinal"] for x in out]
    if len(ordinals) != len(set(ordinals)):
        raise ValueError(f"{w['work_id']}: two works share an ordinal")
    return out


def generate(reg: registry.WorkRegistry, documents: list, rows: list[dict]) -> list[dict]:
    """The works.json entries with each built document's facts and labels, in file order.
    An entry for a document the build does not emit loses any facts and labels it had."""
    by_document = rights_inventory.by_document_id(rows)
    built = {d.id: d for d in documents}
    works = []
    for w in reg.works:
        entry = {k: v for k, v in w.items() if k not in registry.FACT_FIELDS}
        d = built.get(w["document_id"])
        entry["attribution"] = _attribution(w, d is not None)
        entry["works"] = _works(w, d)
        entry.pop("card_translator", None)
        if d is not None:
            entry.update(document_facts.derive(d, by_document.get(d.id), w))
            entry["card_translator"] = document_facts.card_translator(entry)
        works.append(entry)
    return works


def generate_passages(reg: registry.WorkRegistry, documents: list) -> list[dict]:
    """The passage rows with each built passage's `work_key`, and 3.2's chapter notes
    (`attributions.PASSAGE_NOTES`) on the rows of the chapters they name."""
    work_id = {w["document_id"]: w["work_id"] for w in reg.works}
    built = {(d.id, p.anchor): p for d in documents for p in d.passages}
    ours = set(attributions.PASSAGE_NOTES.values())
    out = []
    for r in reg.passages:
        p = built.get((r["document_id"], r["anchor"]))
        if p is not None:
            r = {**r, "work_key": p.work_key}
            note = attributions.PASSAGE_NOTES.get((work_id[r["document_id"]], p.chapter_key))
            if note:
                if r.get("note") not in (None, note):
                    raise ValueError(f"{r['passage_id']}: already has another note")
                r["note"] = note
            elif r.get("note") in ours:
                r = {k: v for k, v in r.items() if k != "note"}
        out.append(r)
    return out


def dump(works: list[dict]) -> str:
    return json.dumps(works, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 if works.json would change")
    args = parser.parse_args(argv)

    reg = registry.load_registry()
    unknown = ({k for k in attributions.DOCUMENTS}
               | {k for k, _ in attributions.WORKS}) - {w["work_id"] for w in reg.works}
    if unknown:
        raise ValueError(f"3.2 labels for unregistered works: {sorted(unknown)}")
    documents = build_all(reg)
    works = generate(reg, documents, rights_inventory.load())
    passages = generate_passages(reg, documents)
    # Before anything is written: a published document whose card can name no
    # translator (4.4) is a rule to add to card_notes.card_translator, not a null.
    nameless = [w["work_id"] for w in works if "card_translator" in w
                and w["card_translator"] is None]
    if nameless:
        raise ValueError(f"no card translator for {', '.join(nameless)}: add a rule to "
                         "card_notes.card_translator")
    updated = registry.WorkRegistry(works, passages, reg.redirects, reg.removals,
                                    reg.kept_text, held_texts=reg.held_texts)
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            registry.write_registry(updated, tmp)
            changed = [name for name in _registry_files(tmp)
                       if _read(os.path.join(tmp, name))
                       != _read(os.path.join(registry.REGISTRY_DIR, name))]
        if changed:
            print(f"{', '.join(changed)} differ from the build's document facts and labels; "
                  "run scripts/document_facts_registry.py")
            return 1
        print("works.json document facts and labels match the build")
        return 0
    registry.write_registry(updated)
    filled = sum(registry.has_facts(w) for w in works)
    print(f"document facts written for {filled} of {len(works)} works.json entries")
    problems = registry.validate(registry.load_registry())
    for p in problems:
        print(f"  {p}")
    return 1 if problems else 0


def _registry_files(directory: str) -> list[str]:
    names = [registry.WORKS_FILE]
    passages = os.path.join(directory, registry.PASSAGES_DIR)
    names += sorted(os.path.join(registry.PASSAGES_DIR, n) for n in os.listdir(passages))
    return names


def _read(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    raise SystemExit(main())
