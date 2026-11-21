"""Registry changes for the medieval adapter fixes (corpus-cleanup 1.9), generated from a
build.

    cd datapipeline
    python3 scripts/medieval_registry.py [--dry-run]

Builds the medieval collection with `ingest.editorial.recording()` on and writes, in place
of the entries 1.9 added before:

- a `passage` entry (`rule-g-editorial`) for each live passage of an editorial div the
  build now skips: Boethius's "A Note on the Translation", "Editorial Note" and
  "Chronological Table" (whose body is the live "Section" passage), and the Imitation's
  "Foreword", by its live anchor and frozen passage ID, with a tombstone; the rows
  retire;
- the editors' authenticity judgments found in that text (`JUDGMENTS`), copied into the
  work's `attribution.editorial_judgments` (rule G: judgments first);
- the works.json title of Cur Deus Homo, which the source titles "Anselm's Cur Deus Homo".

It is idempotent: a rerun on its own output changes nothing.
"""
from __future__ import annotations

import argparse
import os
import sys

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from ingest import editorial  # noqa: E402
from publication import SOURCE_ADAPTERS  # noqa: E402

ITEM = "1.9"
TODAY = "2026-11-13"
COLLECTION = "medieval"
REASON = "rule-g-editorial"
TOMBSTONE = ("This passage was an editor's note and was removed because TheoCorpus shows "
             "only the authors' own words.")
TITLES = {"medieval/proslogium-monologium-and-cur-deus-homo.xml#vi": "Cur Deus Homo"}

# The sentences of the removed text that judge who wrote a work, by (source key, div),
# with the verdict, read by hand. The Editorial Note's sentences on authenticity are
# about Boethius's theological tractates and Alfred's sayings, works not in the corpus.
JUDGMENTS = {
    ("medieval/imitation-of-christ.xml", "ii"): (
        "Theories most popular at the moment ascribe the Imitation to two or three men, "
        "members of the Brethren of the Common Life, an association of priests organized in "
        "the Netherlands in the latter half of the fourteenth century.", "dubious"),
}


def generate(reg: registry.WorkRegistry, documents: list, log: list) -> list[dict]:
    """The passage entries for a build (`documents`, built with `log` recording)."""
    skipped = {(k, div): title.rstrip(".") for k, div, title in log if isinstance(title, str)}
    keys = {d.id: d.metadata["source_key"] for d in documents}
    built = {(d.id, p.anchor) for d in documents for p in d.passages}
    mine = {e["passage_id"] for e in reg.removals if e.get("added_by") == ITEM}
    entries = []
    for r in reg.passages:
        if r["document_id"] not in keys or (r["document_id"], r["anchor"]) in built:
            continue
        if not (r["status"] == "active" or (r["status"] == "retired"
                                            and r["passage_id"] in mine)):
            continue
        key = keys[r["document_id"]]
        div = r["anchor"].split("/")[0].split("-p")[0]
        if (key, div) not in skipped:
            continue
        judgment = JUDGMENTS.get((key, div))
        entries.append({
            "id": None, "scope": "passage", "collection": COLLECTION,
            "document_id": r["document_id"], "anchor": r["live_anchor"],
            "passage_id": r["passage_id"], "reason": REASON,
            "detail": f"{skipped[(key, div)]}, by an editor or translator, not the author "
                      f"(div {div})",
            "tombstone": TOMBSTONE, "church_act": None, "span": None,
            "judgment": judgment[0] if judgment else None,
            "added_by": ITEM, "added_on": TODAY})
    return entries


def plan(reg: registry.WorkRegistry, entries: list[dict]) -> registry.WorkRegistry:
    previous = {(e["document_id"], e["anchor"]): e["id"] for e in reg.removals
                if e.get("added_by") == ITEM}
    number = max(int(e["id"].split("-")[1]) for e in reg.removals) + 1
    for e in entries:
        e["id"] = previous.get((e["document_id"], e["anchor"]))
        if e["id"] is None:
            e["id"] = f"rm-{number:04d}"
            number += 1
    kept = [e for e in reg.removals if e.get("added_by") != ITEM]
    removals = sorted(kept + entries,
                      key=lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""))
    retiring = {e["passage_id"] for e in entries}
    passages = [dict(r, status="retired") if r["passage_id"] in retiring else r
                for r in reg.passages]
    works = []
    for w in reg.works:
        key = w["source_key"]
        if key in TITLES:
            w = {**w, "title": TITLES[key]}
        found = [(div, q) for (k, div), q in JUDGMENTS.items() if k == key]
        if found:
            listed = [j for j in w["attribution"].get("editorial_judgments") or []
                      if (j["element_id"], j["quote"]) not in {(d, q[0]) for d, q in found}]
            listed += [{"source_file": key.split("/", 1)[1], "element_id": div,
                        "quote": quote, "verdict": verdict, "overridden_by_plan": False}
                       for div, (quote, verdict) in found]
            w = {**w, "attribution": {**w["attribution"], "editorial_judgments": listed}}
        works.append(w)
    return registry.WorkRegistry(works, passages, reg.redirects, removals, reg.kept_text, held_texts=reg.held_texts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    reg = registry.current()
    with editorial.recording() as log:
        documents = SOURCE_ADAPTERS[COLLECTION]()
    entries = generate(reg, documents, log)
    for e in entries:
        print(e["anchor"], e["passage_id"], e["detail"])
    updated = plan(reg, entries)
    problems = registry.validate(updated)
    if problems:
        print("\n".join(problems[:20]))
        return 1
    if not args.dry_run:
        registry.write_registry(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
