"""Removal registry entries for the non-English passages rule E retires (corpus-cleanup 3.3).

    cd datapipeline
    python3 scripts/language_removals.py [--today YYYY-MM-DD] [--dry-run]

Writes, in place of the entries 3.3 added before (`added_by`), the list Carter approved on
14 Nov 2026:

- a `document` entry for Ubi Lutetiam, which is wholly Italian;
- a `passage` entry for each passage the ANF translators left wholly in Latin (Clement's
  Stromata III and Instructor II.10, Lactantius's Divine Institutes VI.23 and On the
  Workmanship of God 12), with its passage-registry row set `retired`;
- where 1.10b or 1.10c redirected an earlier live piece into one of those passages, the
  redirect is closed and that piece is retired too, since its text is the same Latin;
- a `span` entry for each Latin paragraph cut from a passage that is otherwise English
  (`ingest.church_fathers.NON_ENGLISH_PARAGRAPHS`), by its sha1;
- and it keeps 1.10b's per-document note counts (`class` entries of rule
  `common._p_text_without_notes`) in step with the build for the four works that lose
  passages, as `scripts/editorial_removals.py` does, since a retired passage's notes
  leave with it.

Every entry has reason `translation-in-preparation`; the `document` and `passage` entries
carry rule E's tombstone, and a passage entry names the row's live anchor (2.1). No entry
holds the original text. IDs run from rm-4001 (3.3's
block), in the order listed here.
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
from ingest.church_fathers import (NON_ENGLISH_OMITTED,  # noqa: E402
                                   NON_ENGLISH_PARAGRAPHS)
NOTE_RULE = "common._p_text_without_notes"

ITEM = "3.3"
FIRST_ID = 4001
REASON = "translation-in-preparation"
TOMBSTONE = "No public-domain English translation is available."

UBI_LUTETIAM = "ba74d920-a179-5c9e-a1a5-5d677116c82a"
STROMATA = "3a68ef3f-b829-5e95-9eeb-f1ef299c4a38"
INSTRUCTOR = "96584290-90c2-50bc-9d3d-c353b8969e1f"
DIVINE_INSTITUTES = "9e03c96d-8295-5e5e-a4d3-3570ddcf0415"
WORKMANSHIP = "f913305f-b259-578b-a5ca-532fac927aab"

DOCUMENTS = [
    (UBI_LUTETIAM, "encyclicals",
     "Rule E: the letter is in Italian, and no English translation was found (3.3)."),
]

_STROMATA_III = ["vi.iv.iii"] + [f"vi.iv.iii/from-p{n}" for n in (
    "9", "9-2", "17", "27", "27-2", "36", "36-2", "36-3", "36-4", "63", "67", "72", "81",
    "81-2", "102", "117", "124", "131", "131-2", "143", "143-2", "162", "162-2", "162-3",
    "162-4", "199", "202", "209", "225", "236", "246", "246-2")]

# (document, anchors, what the passages are), by document.
PASSAGES = [
    (STROMATA, _STROMATA_III,
     "Rule E: Book III, chapter 3 on, which ANF's translator left in Latin; no "
     "public-domain English translation exists (3.3)."),
    (INSTRUCTOR, ["vi.iii.ii.x/from-p8", "vi.iii.ii.x/from-p8-2", "vi.iii.ii.x/from-p8-3",
                  "vi.iii.ii.x/from-p17", "vi.iii.ii.x/from-p17-2"],
     "Rule E: part of Book II, chapter 10, which ANF's translator left in Latin; no "
     "public-domain English translation exists (3.3)."),
    (DIVINE_INSTITUTES, ["iii.ii.vi.xxiii", "iii.ii.vi.xxiii/from-p4",
                         "iii.ii.vi.xxiii/from-p7"],
     "Rule E: Book VI, chapter 23, which ANF's translator left in Latin; no "
     "public-domain English translation exists (3.3)."),
    (WORKMANSHIP, ["iii.iv.xii", "iii.iv.xii/from-p6"],
     "Rule E: chapter 12, which ANF's translator left in Latin; no public-domain "
     "English translation exists (3.3)."),
]

SPAN_DETAIL = ("Rule E: a paragraph ANF's translator left in Latin, cut from a passage "
               "that is otherwise English (3.3).")


def plan(reg: registry.WorkRegistry, today: str) -> list[dict]:
    """3.3's entries, numbered from rm-4001."""
    collection_of = {w["document_id"]: w["collection"] for w in reg.works}
    entries: list[dict] = []

    def add(**fields) -> None:
        entries.append({"id": f"rm-{FIRST_ID + len(entries)}", **fields,
                        "church_act": None, "judgment": None,
                        "added_by": ITEM, "added_on": today})

    for doc, collection, detail in DOCUMENTS:
        add(scope="document", collection=collection, document_id=doc, anchor=None,
            passage_id=None, reason=REASON, detail=detail, tombstone=TOMBSTONE, span=None)
    rows = {r["passage_id"]: r for r in reg.passages}
    redirected_into: dict[str, list[str]] = {}
    for r in reg.redirects:
        if not r.get("closed_by") or r.get("closed_by") == ITEM:
            redirected_into.setdefault(r["new_passage_id"], []).append(r["old_passage_id"])
    for doc, anchors, detail in PASSAGES:
        for anchor in anchors:
            pid = registry.resolve_passage_id(doc, anchor, reg)
            for p in [pid] + redirected_into.get(pid, []):
                add(scope="passage", collection=collection_of[doc], document_id=doc,
                    anchor=rows[p]["live_anchor"], passage_id=p, reason=REASON,
                    detail=detail, tombstone=TOMBSTONE, span=None)
    for (doc, anchor), sha1s in sorted(NON_ENGLISH_PARAGRAPHS.items()):
        for sha1 in sorted(sha1s):
            add(scope="span", collection=collection_of[doc], document_id=doc,
                anchor=anchor, passage_id=None, reason=REASON, detail=SPAN_DETAIL,
                tombstone=None,
                span={"rule": "ingest.church_fathers.NON_ENGLISH_PARAGRAPHS", "sha1": sha1})
    return entries


def apply(reg: registry.WorkRegistry, entries: list[dict], today: str) -> None:
    """Replace 3.3's earlier entries with `entries`, set the passage rows they retire
    `retired`, close the redirects whose old piece they retire, and drop the kept-text
    entries of the passages they retire. Run once on a
    registry 3.3 has not touched, or again on its own output."""
    retiring = {e["passage_id"] for e in entries if e["scope"] == "passage"}
    reg.removals[:] = sorted(
        [e for e in reg.removals if e.get("added_by") != ITEM] + entries,
        key=lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""))
    # A kept-text entry says a passage still holds its live text; a retired one holds none.
    reg.kept_text[:] = [e for e in reg.kept_text if e["passage_id"] not in retiring]
    for r in reg.redirects:
        if r["old_passage_id"] in retiring and not r.get("closed_by"):
            r["closed_by"], r["closed_on"] = ITEM, today
    for r in reg.passages:
        if r["passage_id"] in retiring:
            if r["status"] not in ("active", "retired", "redirected"):
                raise ValueError(f"{r['anchor']}: status {r['status']}")
            r["status"] = "retired"


def sync_note_counts(reg: registry.WorkRegistry, documents) -> None:
    """Set each noted work's note-count entry to the notes its built passages still
    count (`editor_note_count`). `documents`: the Church Fathers build, retired
    passages dropped."""
    counts = {d.id: sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages)
              for d in documents if d.id in NON_ENGLISH_OMITTED}
    for e in reg.removals:
        if e["scope"] == "class" and (e.get("span") or {}).get("rule") == NOTE_RULE \
                and e["document_id"] in counts and not e.get("closed_by"):
            e["span"]["count"] = counts[e["document_id"]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    reg = registry.current()
    # Keep the date of an unchanged entry, so a rerun changes nothing.
    added_on = {e["id"]: e["added_on"] for e in reg.removals if e.get("added_by") == ITEM}
    entries = plan(reg, args.today)
    for e in entries:
        e["added_on"] = added_on.get(e["id"], e["added_on"])
    counts = {s: sum(e["scope"] == s for e in entries) for s in ("document", "passage", "span")}
    print(f"{len(entries)} entries ({counts}), rm-{FIRST_ID} to rm-{FIRST_ID + len(entries) - 1}")
    if args.dry_run:
        return
    apply(reg, entries, args.today)
    registry.activate(reg)        # the build drops what these entries retire
    from ingest.church_fathers import build_all
    sync_note_counts(reg, build_all())
    problems = registry.validate(reg)
    if problems:
        raise SystemExit("registry invalid:\n" + "\n".join(problems[:20]))
    registry.write_registry(reg)


if __name__ == "__main__":
    main()
