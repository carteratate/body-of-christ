"""Registry changes for the Church Fathers' 1.8c adapter fixes, generated from a build.

    cd datapipeline
    python3 scripts/fathers_registry.py --snapshot releases/snapshots/<date>
                                        [--today YYYY-MM-DD] [--dry-run]

Builds the Church Fathers and writes, in place of what 1.8c wrote before:

- the Ignatian recension split (D1, D11): a `split` redirect from each live passage of
  the seven genuine letters to the shorter-recension passage of its chapter, and a
  `span` entry, reason `rule-b`, for the longer recension of each unit (the greeting and
  each chapter), anchored on the passage that keeps the shorter. No Church act names the
  longer recension; the entry states its scholarly basis (Carter, 11 Nov 2026);
- Balsamon's and Zonaras's commentary in Peter of Alexandria's canons (reason
  `other-author`): a `passage` entry, with a tombstone, for each live passage that held
  only commentary, and a `span` entry for each commentary paragraph, the audit record
  the coverage check reads; and a `rule-g-editorial` span for the editor's heading over
  the canons;
- the works of the container documents (D6): each document's `works` in works.json, and
  each built passage's `work_key` in the passage registry;

then runs `registry.reconcile` as `reconcile_registry.py` does (new rows for new units,
`merged` redirects for recut pieces), keeping every kept_text.json entry, and writes the
registry when it validates.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from checks import source_text  # noqa: E402

from identity import PIECE_MARK, unit_anchor  # noqa: E402
from ingest import church_fathers as cf  # noqa: E402
from ingest.common import _block_text, iter_chapters  # noqa: E402
from publication import build  # noqa: E402
from scripts.editorial_removals import live_text  # noqa: E402
from scripts.reconcile_registry import kept_entries, low_scores, lost_text, settle_by_text  # noqa: E402

ITEM = "1.8c"
COLLECTION = "church-fathers"
EXCERPT = 120

RECENSION_DETAIL = (
    "The longer recension of the letter, printed beside the shorter. Removed under rule B "
    "on the majority of standard scholarship, which judges its compiler heterodox; no "
    "Church act names it. The shorter recension stays (Decision log \"Genuine Ignatius "
    "letters\", \"Rule B on scholarship alone\")")
# The one unit printing only the longer recension: Ephesians prints chapter XX twice, and
# the shorter is the unit before it.
LONG_ONLY = {"v.ii.xxi": "v.ii.xx"}

COMMENTARY_DETAIL = ("Commentary by Theodore Balsamon and John Zonaras, 12th-century "
                     "Byzantine canonists, printed by the editor")
COMMENTARY_TOMBSTONE = ("This passage was a later commentary by other writers, not "
                        "Peter's text.")
HEADING_DETAIL = "The editor's heading over the canons"
# 1.10b's per-document count of the notes taken out of the passages.
NOTE_RULE = "common._p_text_without_notes"
NOTE_DETAIL = ("Translator and editor footnotes (ThML <note>) printed inline in the passages; "
               "only their count is kept, as editor_note_count.")
_CUT = re.compile(r"-\d+$")          # a cut inside a paragraph: `p2-2` opens inside `p2`


def _excerpt(text: str) -> str:
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1].rstrip() + "…"


def _norm(text: str) -> str:
    return " ".join(text.split())


def _span(block) -> dict:
    """A removed source paragraph, keyed as the coverage check reads it
    (`checks.source_text.removed_paragraphs`): its text without notes."""
    text = source_text._thml_text(block, skip_notes=True)
    return {"sha1": source_text._paragraph_sha1(text),
            "excerpt": _excerpt(_norm(text.replace(source_text.SEGMENT_BREAK, " ")))}


def _works(filename: str):
    """{work div id: work div} of a vendored Fathers file."""
    root = cf._read_root(os.path.join(cf._SRC_DIR, filename))
    return {e.get("id"): e for e in root.iter() if e.get("id")}, cf._build_parent_map(root)


def generate(reg: registry.WorkRegistry, documents: list, live: dict[str, str], today: str):
    """(removal entries, redirects, passage IDs retired, problems) for a build."""
    by_key = {d.metadata["source_key"]: d for d in documents}
    rows_of: dict[str, list[dict]] = defaultdict(list)
    for r in reg.passages:
        rows_of[r["document_id"]].append(r)
    entries, redirects, retired, problems = [], [], set(), []

    def entry(**kw) -> dict:
        e = {"id": None, "scope": None, "collection": COLLECTION, "document_id": None,
             "anchor": None, "passage_id": None, "reason": None, "detail": None,
             "tombstone": None, "church_act": None, "span": None, "judgment": None,
             "added_by": ITEM, "added_on": today}
        e.update(kw)
        return e

    # Ignatius: the shorter recension stays, the longer goes.
    for filename, work_id in sorted(cf._RECENSIONS):
        divs, parent_map = _works(filename)
        work = divs[work_id]
        d = by_key[cf._source_key(filename, work)]
        built = {p.anchor: p for p in d.passages}
        units = [work] + [elem for _, elem in iter_chapters(work, parent_map)]
        for unit in units:
            uid = unit.get("id")
            anchor = (f"{uid}/salutation" if unit is work
                      else f"{LONG_ONLY.get(uid, uid)}/short")
            if not cf.recension_blocks(unit)[1]:
                continue
            if anchor not in built:
                problems.append(f"{d.title}: the longer recension of {uid} has no built "
                                f"passage {anchor}")
                continue
            entries += [entry(scope="span", document_id=d.id, anchor=anchor,
                              reason="rule-b", detail=RECENSION_DETAIL, span=_span(b))
                        for b in cf.recension_blocks(unit)[1]]
        for r in rows_of[d.id]:
            if r["status"] != "active" or r["anchor"] in built:
                continue
            unit = unit_anchor(r["anchor"])
            target = f"{LONG_ONLY.get(unit, unit)}/short"
            if target not in built:
                problems.append(f"{d.title}: {r['anchor']} has no shorter passage {target}")
                continue
            redirects.append({
                "document_id": d.id, "old_passage_id": r["passage_id"],
                "old_anchor": r["anchor"],
                "new_passage_id": registry.resolve_passage_id(d.id, target, reg),
                "new_anchor": target, "kind": "split",
                "reason": "the passage held both Ignatian recensions; the shorter stays",
                "added_by": ITEM})

    # Peter of Alexandria: his canons without the commentators.
    for filename, work_id in sorted(cf._COMMENTARY):
        divs, _ = _works(filename)
        work = divs[work_id]
        d = by_key[cf._source_key(filename, work)]
        built = {p.anchor for p in d.passages}
        pieces: dict[str, list[str]] = defaultdict(list)     # canon div -> its passages
        for p in d.passages:
            pieces[p.chapter_key].append(p.anchor)
        canons = [c for c in work if isinstance(c.tag, str) and c.tag.startswith("div")]
        commentary = {canon.get("id"): cf.commentary_blocks(canon)[1] for canon in canons}
        opening_ids = {b.get("id") for blocks in commentary.values() for b in blocks}
        # A passage that opens on a commentator's paragraph holds commentary alone, since
        # the commentary closes each canon: its anchor's locator names that paragraph.
        for r in rows_of[d.id]:
            if r["status"] == "retired" or r["anchor"] in built \
                    or PIECE_MARK not in r["anchor"]:
                continue
            canon_id, locator = r["anchor"].split(PIECE_MARK, 1)
            if f"{canon_id}-{_CUT.sub('', locator)}" in opening_ids:
                retired.add(r["passage_id"])
                entries.append(entry(scope="passage", document_id=d.id,
                                     anchor=r["live_anchor"], passage_id=r["passage_id"],
                                     reason="other-author", detail=COMMENTARY_DETAIL,
                                     tombstone=COMMENTARY_TOMBSTONE))
        # Each commentary paragraph is cut from its canon, whose last passage now ends
        # where it did: a span entry records it, held by a passage that keeps Peter's
        # text or by one retired above, so the coverage check counts it as removed.
        texts = {r["passage_id"]: _norm(live[r["passage_id"]]) for r in rows_of[d.id]
                 if r["status"] != "retired" and live.get(r["passage_id"])}
        for canon in canons:
            for k, block in enumerate(commentary[canon.get("id")]):
                text = _norm(_block_text(block))
                holders = [pid for pid, t in texts.items() if text[:80] in t]
                if len(holders) != 1:
                    problems.append(f"{canon.get('id')}: commentary paragraph {k + 1} is in "
                                    f"{len(holders)} live passages")
                else:
                    entries.append(entry(scope="span", document_id=d.id,
                                         anchor=pieces[canon.get("id")][-1],
                                         reason="other-author", detail=COMMENTARY_DETAIL,
                                         span=_span(block)))
            for block in cf.canons_heading(canon):
                entries.append(entry(scope="span", document_id=d.id,
                                     anchor=pieces[canon.get("id")][0],
                                     reason="rule-g-editorial", detail=HEADING_DETAIL,
                                     span=_span(block)))
        for e in entries:
            if e["document_id"] == d.id and e["scope"] == "span" and e["anchor"] not in built:
                problems.append(f"{d.title}: span entry anchored on {e['anchor']}, not built")
    return entries, redirects, retired, problems


def sync_works(reg: registry.WorkRegistry, rows: list[dict], documents: list) -> tuple:
    """works.json with each built document's `works`, and the passage rows with each built
    passage's `work_key` (D6, D11); a retired row keeps its own."""
    built = {d.id: d for d in documents}
    works = []
    for w in reg.works:
        d = built.get(w["document_id"])
        if d is not None:
            w = {**w, "works": [dataclasses.asdict(x) for x in d.works]}
        works.append(w)
    keys = {(d.id, p.anchor): p.work_key for d in documents for p in d.passages}
    out = []
    for r in rows:
        if r["document_id"] in built:
            # A retired passage keeps the work it belonged to (3.1 retires whole works).
            kept = r["work_key"] if r["status"] == "retired" else None
            r = {**r, "work_key": keys.get((r["document_id"], r["anchor"]), kept)}
        out.append(r)
    return works, out


def sync_note_counts(removals: list[dict], documents: list, today: str) -> list[dict]:
    """1.10b's per-document note counts (`class` entries) follow the build: the longer
    recension's and the commentators' notes are no longer ones the passages lost. A
    document that now has notes and no entry gets one (Asterius Urbanus); an entry whose
    document keeps no note closes (entries are never deleted)."""
    counts = {d.id: sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages)
              for d in documents}
    out, seen = [], set()
    for e in removals:
        if e["scope"] == "class" and (e.get("span") or {}).get("rule") == NOTE_RULE \
                and e["collection"] == COLLECTION and not e.get("closed_by"):
            seen.add(e["document_id"])
            n = counts.get(e["document_id"], 0)
            e = {**e, "span": {**e["span"], "count": n}} if n \
                else {**e, "closed_by": ITEM, "closed_on": today}
        out.append(e)
    for doc_id in sorted(d for d, n in counts.items() if n and d not in seen):
        out.append({"id": None, "scope": "class", "collection": COLLECTION,
                    "document_id": doc_id, "anchor": None, "passage_id": None,
                    "reason": "rule-g-editorial", "detail": NOTE_DETAIL, "tombstone": None,
                    "church_act": None, "span": {"rule": NOTE_RULE, "count": counts[doc_id]},
                    "judgment": None, "added_by": ITEM, "added_on": today})
    return out


def _key(e: dict) -> tuple:
    return (e["scope"], e["document_id"], e.get("anchor"), e.get("passage_id"),
            (e.get("span") or {}).get("sha1"))


def plan(reg: registry.WorkRegistry, documents: list, live: dict[str, str], today: str):
    """The updated registry and any problems. A rerun replaces what 1.8c wrote before,
    keeping each entry's ID and date where it is unchanged."""
    previous = {_key(e): e for e in reg.removals if e.get("added_by") == ITEM}
    retired_before = {e.get("passage_id") for e in previous.values()}
    redirects = [dict(r) for r in reg.redirects if r.get("added_by") != ITEM]
    for r in redirects:
        if r.get("closed_by") == ITEM:
            del r["closed_by"], r["closed_on"]
    open_old = {r["old_passage_id"] for r in redirects if not r.get("closed_by")}
    rows = [dict(r) for r in reg.passages]
    for r in rows:
        if r["passage_id"] in retired_before:
            r["status"] = "redirected" if r["passage_id"] in open_old else "active"
        elif r["status"] == "redirected" and r["passage_id"] not in open_old:
            r["status"] = "active"
    removals = []
    for e in reg.removals:
        if e.get("added_by") == ITEM:
            continue
        if e.get("closed_by") == ITEM:
            e = {k: v for k, v in e.items() if k not in ("closed_by", "closed_on")}
        removals.append(e)
    base = registry.WorkRegistry(reg.works, rows, redirects, removals, reg.kept_text, held_texts=reg.held_texts)
    entries, split, retired, problems = generate(base, documents, live, today)
    notes = sync_note_counts(base.removals, documents, today)
    entries += [e for e in notes if e["id"] is None]
    number = max(int(e["id"].split("-")[1]) for e in reg.removals) + 1
    for e in entries:
        prior = previous.get(_key(e))
        if prior:
            e["id"], e["added_on"] = prior["id"], prior["added_on"]
        else:
            e["id"], number = f"rm-{number:04d}", number + 1
    # Earlier items' redirects: one from a passage now retired closes; one into a letter
    # whose pieces now redirect to its shorter recension follows them there.
    onward = {r["old_passage_id"]: r for r in split}
    for r in redirects:
        if r.get("closed_by"):
            continue
        if r["old_passage_id"] in retired:
            r["closed_by"], r["closed_on"] = ITEM, today
        elif r["new_passage_id"] in onward:
            nxt = onward[r["new_passage_id"]]
            r["new_passage_id"], r["new_anchor"] = nxt["new_passage_id"], nxt["new_anchor"]
    redirected = {r["old_passage_id"] for r in split}
    for r in rows:
        if r["passage_id"] in retired:
            r["status"] = "retired"
        elif r["passage_id"] in redirected:
            r["status"] = "redirected"
    mine = {id(e) for e in entries}
    removals = [e for e in notes if id(e) not in mine]
    staged = registry.WorkRegistry(reg.works, rows, redirects + split,
                                   sorted(removals + entries,
                                          key=lambda e: (e["collection"], e["document_id"],
                                                         e.get("anchor") or "")),
                                   reg.kept_text, held_texts=reg.held_texts)
    rec = registry.reconcile(staged, documents, item=ITEM, today=today,
                             settle=settle_by_text(live), moved=lost_text(live))
    problems += rec.problems
    rebuilt = {d.id for d in documents}
    kept = [e for e in reg.kept_text if e["document_id"] not in rebuilt]
    found, unexplained = kept_entries(low_scores(rec.rows, documents, live), reg.kept_text,
                                      ITEM, reasons={e["passage_id"]: None
                                                     for e in reg.kept_text})
    problems += unexplained
    works, passages = sync_works(reg, rec.rows, documents)
    updated = registry.WorkRegistry(works, passages, rec.redirects, staged.removals,
                                    sorted(kept + found,
                                           key=lambda e: (e["document_id"], e["anchor"])), held_texts=reg.held_texts)
    problems += registry.validate(updated)
    return updated, entries, split, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    reg = registry.current()
    documents = build(COLLECTION)
    updated, entries, redirects, problems = plan(reg, documents, live_text(args.snapshot),
                                                 args.today)
    print(Counter((e["scope"], e["reason"]) for e in entries),
          f"{len(redirects)} split redirects")
    for p in problems:
        print(f"problem: {p}")
    if problems:
        return 1
    if not args.dry_run:
        registry.write_registry(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
