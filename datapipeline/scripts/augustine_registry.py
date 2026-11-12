"""Registry changes for the NPNF Augustine clean-up (corpus-cleanup 1.8b), generated from a
build.

    cd datapipeline
    python3 scripts/augustine_registry.py --snapshot releases/snapshots/<date>
                                          [--today YYYY-MM-DD] [--dry-run]

Builds the Church Fathers and writes, in place of what 1.8b wrote before:

- the treatise volume's split (Carter, 4 Nov 2026; the one exception to D6): "Doctrinal
  Treatises of St. Augustin" and "Moral Treatises of St. Augustin" become their 16
  works. On the Holy Trinity keeps the first volume's document ID and On Continence the
  second's (their works.json entries take the work's source key and title); the other 14
  works are registered as new documents. Every passage row of the two volumes moves to
  the work that holds its unit, keeping its passage ID (2.2w updates `document_id` in
  place, D11), and so do their redirects and kept_text.json entries;
- rule G's removals in the NPNF Augustine volumes, through `scripts/editorial_removals.py`
  (`item="1.8b"`): a `passage` entry for each live passage of an editor's div the build
  skips (Shedd's essay, the translators' prefaces, the Enchiridion's "Argument", the
  contents of On Christian Doctrine), of a book whose own text was the editors' heading
  and summary, and of a treatise's title page; `span` and `class` entries for what the
  passages that stay lose; the editors' authenticity judgments copied into works.json;
- a `class` entry for the Confessions' four plain-digit footnote callers;
- 1.10b's note counts for the NPNF Augustine documents, the split volume's works among
  them;

then runs `registry.reconcile` as `reconcile_registry.py` does (new rows for new units,
such as the kept quotations of Augustine, and `merged` redirects for recut pieces) and
writes the registry when it validates.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from ingest import editorial  # noqa: E402
from publication import build  # noqa: E402
from scripts import editorial_removals as er  # noqa: E402
from scripts.reconcile_registry import kept_entries, low_scores, lost_text, settle_by_text  # noqa: E402

ITEM = "1.8b"
COLLECTION = "church-fathers"
VOLUME_FILE = "on-the-holy-trinity.xml"
# Each volume's frozen document ID goes to the work holding most of its passages and
# retrievals (spec): source key of the volume -> source key of that work.
PINS = {
    f"{COLLECTION}/{VOLUME_FILE}#iv": f"{COLLECTION}/{VOLUME_FILE}#iv.i",   # On the Holy Trinity
    f"{COLLECTION}/{VOLUME_FILE}#v": f"{COLLECTION}/{VOLUME_FILE}#v.i",     # On Continence
}
NOTE_RULE = "common._p_text_without_notes"
NOTE_DETAIL = ("Translator and editor footnotes (ThML <note>) printed inline in the passages; "
               "only their count is kept, as editor_note_count.")
# Passages that keep their ID under the release report's stability threshold, read and
# found to open on their live opening words: by passage ID, why they score low.
KEPT_REASONS = {
    passage_id: ("Reviewed for 1.8b on 12 Nov 2026: it still opens on its live opening words. "
                 "It scores low because its long chapter title, the Benedictine editors', moved "
                 "into the chapter label (1.8b), and 1.10b removed the notes that were much of "
                 "the rest of its live text.")
    for passage_id in ("c6faca6e-192c-575e-a0ca-56a2883d03e7",     # On the Trinity III.11
                       "20cb5667-3379-52ca-b648-602f90a40953")     # On the Trinity XIII.1
}
CALLER_RULE = "ingest.editorial.PLAIN_CALLERS"
CALLER_DETAIL = ("Four footnote callers printed as plain digits after the sentence in Book VII, "
                 "chapter XI (div viii.xi: \"remains immutably.2 It is good\"), whose notes the "
                 "source does not print (C-17)")


def _source_key(collection: str, file: str, div: str) -> str:
    return f"{collection}/{file}#{div}"


def pin_volumes(reg: registry.WorkRegistry) -> registry.WorkRegistry:
    """The registry with each volume's works.json entry moved to the work it pins."""
    works = []
    for w in reg.works:
        if w["collection"] == COLLECTION and w["source_key"] in PINS:
            w = {**w, "source_key": PINS[w["source_key"]]}
        works.append(w)
    return registry.WorkRegistry(works, reg.passages, reg.redirects, reg.removals,
                                 reg.kept_text)


def volume_documents(documents: list) -> list:
    return [d for d in documents
            if d.metadata["source_key"].startswith(f"{COLLECTION}/{VOLUME_FILE}#")]


def register_works(reg: registry.WorkRegistry, documents: list, today: str
                   ) -> registry.WorkRegistry:
    """Each work of the split volume in works.json, under its title: the two pinned ones
    retitled, the 14 others registered as new."""
    reg = registry.WorkRegistry([dict(w) for w in reg.works], reg.passages, reg.redirects,
                                reg.removals, reg.kept_text)
    by_key = {w["source_key"]: w for w in reg.works if w["collection"] == COLLECTION}
    for d in volume_documents(documents):
        w = by_key.get(d.metadata["source_key"])
        if w is None:
            registry.register_new_work(reg, d, today)
        else:
            w["title"], w["author"] = d.title, d.author
    return reg


def move_rows(reg: registry.WorkRegistry, documents: list) -> registry.WorkRegistry:
    """Every passage row, redirect and kept_text entry of the two volumes, under the
    document of the work that holds its unit (`iv.iii.ii/from-p5` is in work `iv.iii`)."""
    work_doc = {d.metadata["source_key"]: d.id for d in volume_documents(documents)}
    volumes = {work_doc[k] for k in PINS.values()}

    def document_of(document_id: str, anchor: str) -> str:
        if document_id not in volumes:
            return document_id
        work = ".".join(anchor.split("/")[0].split("#")[0].split(".")[:2])
        return work_doc[_source_key(COLLECTION, VOLUME_FILE, work)]

    rows = [{**r, "document_id": document_of(r["document_id"], r["anchor"])}
            for r in reg.passages]
    redirects = []
    for r in reg.redirects:
        doc = document_of(r["document_id"], r["old_anchor"])
        if doc != document_of(r["document_id"], r["new_anchor"]):
            raise ValueError(f"redirect {r['old_passage_id']} crosses two works")
        redirects.append({**r, "document_id": doc})
    kept = [{**e, "document_id": document_of(e["document_id"], e["anchor"])}
            for e in reg.kept_text]
    return registry.WorkRegistry(reg.works, rows, redirects, reg.removals, kept)


def _without_mine(reg: registry.WorkRegistry) -> registry.WorkRegistry:
    """The registry as it was before this script's removal entries: theirs dropped, the
    entries and redirects they closed reopened, the rows they retired active again."""
    mine = {e.get("passage_id") for e in reg.removals if e.get("added_by") == ITEM}
    removals = []
    for e in reg.removals:             # its own entries stay, for er.plan to replace
        if e.get("closed_by") == ITEM:
            e = {k: v for k, v in e.items() if k not in ("closed_by", "closed_on")}
        removals.append(e)
    redirects = [dict(r) for r in reg.redirects if r.get("added_by") != ITEM]
    for r in redirects:
        if r.get("closed_by") == ITEM:
            del r["closed_by"], r["closed_on"]
    open_old = {r["old_passage_id"] for r in redirects if not r.get("closed_by")}
    # A row the last run renamed `<anchor>#moved-1.8b` takes its anchor back from the row
    # that run made for it (registry.reconcile's `moved`).
    mark = f"{registry.MOVED_MARK}{ITEM}"
    renamed = {(r["document_id"], r["anchor"][:-len(mark)]) for r in reg.passages
               if r["anchor"].endswith(mark)}
    rows = []
    for r in reg.passages:
        if (r["document_id"], r["anchor"]) in renamed:
            continue
        if r["anchor"].endswith(mark):
            r = {**r, "anchor": r["anchor"][:-len(mark)]}
        if r["passage_id"] in mine or (r["status"] == "redirected"
                                       and r["passage_id"] not in open_old):
            r = {**r, "status": "redirected" if r["passage_id"] in open_old else "active"}
        rows.append(r)
    return registry.WorkRegistry(reg.works, rows, redirects, removals, reg.kept_text)


def class_entries(reg: registry.WorkRegistry, documents: list, today: str,
                  before: list[dict]) -> list[dict]:
    """The removals with 1.10b's note counts in step with the NPNF Augustine documents (the
    split volume's works among them), and the Confessions' callers entry. Entries this script added before (`before`, the
    removals of the previous run) keep their IDs."""
    counts = {d.id: sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages)
              for d in documents
              if er.item_of(er._file_of(d.metadata["source_key"])) == ITEM}
    previous = {(e["document_id"], e["span"]["rule"]): e for e in before
                if e.get("added_by") == ITEM and e["scope"] == "class"
                and (e.get("span") or {}).get("rule") in (NOTE_RULE, CALLER_RULE)}
    out, seen = [], set()
    for e in reg.removals:
        if (e.get("document_id"), (e.get("span") or {}).get("rule")) in previous \
                and e.get("added_by") == ITEM:
            continue
        if e["scope"] == "class" and (e.get("span") or {}).get("rule") == NOTE_RULE \
                and e["document_id"] in counts and not e.get("closed_by"):
            seen.add(e["document_id"])
            n = counts[e["document_id"]]
            e = {**e, "span": {**e["span"], "count": n}} if n \
                else {**e, "closed_by": ITEM, "closed_on": today}
        out.append(e)

    def entry(document_id, rule, count, detail):
        prior = previous.get((document_id, rule))
        return {"id": prior["id"] if prior else None, "scope": "class",
                "collection": COLLECTION, "document_id": document_id, "anchor": None,
                "passage_id": None, "reason": "rule-g-editorial", "detail": detail,
                "tombstone": None, "church_act": None, "span": {"rule": rule, "count": count},
                "judgment": None, "added_by": ITEM,
                "added_on": prior["added_on"] if prior else today}

    for doc_id in sorted(d for d, n in counts.items() if n and d not in seen):
        out.append(entry(doc_id, NOTE_RULE, counts[doc_id], NOTE_DETAIL))
    confessions = next(d for d in documents
                       if d.metadata["source_key"] == f"{COLLECTION}/confessions.xml")
    out.append(entry(confessions.id, CALLER_RULE,
                     sum(len(v) for (f, _), v in editorial.PLAIN_CALLERS.items()
                         if f == "confessions.xml"), CALLER_DETAIL))
    number = max(int(e["id"].split("-")[1]) for e in reg.removals if e.get("id")) + 1
    for e in out:
        if e["id"] is None:
            e["id"], number = f"rm-{number:04d}", number + 1
    return sorted(out, key=lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""))


def plan(reg: registry.WorkRegistry, live: dict[str, str], today: str):
    """The updated registry, the removal entries, the judgments not yet reviewed and any
    problems."""
    reg = pin_volumes(reg)
    previous = registry.activate(reg)
    try:
        with editorial.recording() as log:
            documents = build(COLLECTION)
    finally:
        registry.activate(previous)
    reg = move_rows(register_works(reg, documents, today), documents)
    base = _without_mine(reg)
    entries, found, problems = er.generate(base, documents, log, live, today, item=ITEM)
    staged, unreviewed = er.plan(base, entries, found, item=ITEM)
    if staged is None:
        return None, entries, unreviewed, problems
    staged = registry.WorkRegistry(staged.works, staged.passages, staged.redirects,
                                   class_entries(staged, documents, today, base.removals),
                                   staged.kept_text)
    rec = registry.reconcile(staged, documents, item=ITEM, today=today,
                             settle=settle_by_text(live), moved=lost_text(live))
    problems += rec.problems
    rebuilt = {d.id for d in documents}
    kept = [e for e in staged.kept_text if e["document_id"] not in rebuilt]
    found_kept, unexplained = kept_entries(
        low_scores(rec.rows, documents, live), staged.kept_text, ITEM,
        reasons={**{e["passage_id"]: None for e in staged.kept_text}, **KEPT_REASONS})
    problems += unexplained
    updated = registry.WorkRegistry(staged.works, rec.rows, rec.redirects, staged.removals,
                                    sorted(kept + found_kept,
                                           key=lambda e: (e["document_id"], e["anchor"])))
    problems += registry.validate(updated)
    return updated, entries, [], problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    updated, entries, unreviewed, problems = plan(registry.current(),
                                                  er.live_text(args.snapshot), args.today)
    print(Counter((e["scope"], e["reason"]) for e in entries))
    for key, source_key, element, quote in unreviewed:
        print(f"UNREVIEWED {key} {source_key} {element}: {quote}")
    for p in problems:
        print(f"problem: {p}")
    if unreviewed or problems:
        return 1
    if not args.dry_run:
        registry.write_registry(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
