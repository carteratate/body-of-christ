"""Registry changes for the NPNF volumes 5.6a adds to the Church Fathers (corpus-cleanup
5.6a, #205), generated from a build.

    cd datapipeline
    python3 scripts/npnf_registry.py [--today YYYY-MM-DD] [--dry-run]

For each document `ingest.church_fathers.NPNF_WORKS` builds:

- registers its work in works.json under its source key (`npnf208.xml#ix`), so its
  document ID is frozen, with its rule A record (`RULE_A`);
- gives its volume's rights-inventory row one row per built work, each marked built
  (document ID filled in, `planned_for` cleared); the volume's row carries the shared
  facts, as 5.2 wrote it;
- adds passage rows for its passages (`registry.reconcile`, item 5.6a);
- writes, in place of the entries 5.6a wrote before, numbered from rm-11501 (5.6a's block):
  - rule A: a `passage` entry for each passage of the letters `EXCLUDED` lists, with the
    detail and tombstone given there (never shown: the letters were never published);
  - rule G, through `scripts/editorial_removals.py` (`item="5.6a"`): a `span` entry for
    each bracketed comparison with the English Bibles cut from the text, and a `class`
    entry counting each document's head lines (number and title lines the label carries);
  - rule E: a `span` entry for each paragraph `church_fathers.NOT_ENGLISH` cuts;
  - 1.10b's `class` entry counting each document's notes;
- copies the translator's authenticity judgments from his notes (`JUDGMENTS`) into each
  work's `attribution.editorial_judgments`, rule G's "judgments first".

Writes the registry only when it validates. Then, as for any adapter change:

    python3 scripts/document_facts_registry.py
    python3 scripts/source_sites.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
import rights_inventory  # noqa: E402
from ingest import church_fathers, editorial  # noqa: E402
from scripts import editorial_removals as er  # noqa: E402

ITEM = "5.6a"
IDS = (11501, 11999)
COLLECTION = "church-fathers"
NOTE_RULE = "common._p_text_without_notes"
NOTE_DETAIL = ("Translator and editor footnotes (ThML <note>) printed inline in the passages; "
               "only their count is kept, as editor_note_count.")
R1_ADDENDUM = "docs/research/R1-rule-a-dating.md, 5.6a addendum (Basil)"
QUASTEN = "Quasten, Patrología II (BAC 1978)"
FEDWICK_CHRONOLOGY = ("P. J. Fedwick, \"A Chronology of the Life and Works of Basil of "
                      "Caesarea\", in Basil of Caesarea: Christian, Humanist, Ascetic (1981)")

# Rule A, limit 1: Evagrius is condemned by name in the Second Council of Nicaea's
# definition ("the mythical speculations of Origen, Evagrius and Didymus").
NICAEA_II = {"issuer": "Second Council of Nicaea", "date": "0787-10-13",
             "act": "definition of faith", "effect": "condemn",
             "citation": "https://www.papalencyclicals.net/councils/ecum07.htm"}
T_EVAGRIUS = ("Removed because Evagrius Ponticus wrote this letter, which came down among "
              "Basil's, and the Church condemned Evagrius by name.")
T_NOT_CHRISTIAN = "Removed because its author was not a Christian."
T_JULIAN = ("Removed because this letter is in the name of the emperor Julian, who had "
            "abandoned the faith.")
T_BEFORE_BAPTISM = ("Removed because Basil may have written this before he was baptized, "
                    "and it cannot be shown to date from after.")

_LIBANIUS = ("Rule A: a letter of Libanius, the pagan sophist, to Basil; its author was not a "
             "Christian (Quasten, p. 245: \"un pagano declarado\").")
_BEFORE_BAPTISM = ("Rule A, limit 3: Basil's letter to Libanius; Quasten names the "
                   "correspondence's dates as 356 to 372 (after Seeck) and dates none of its "
                   "letters, so no chronology places it after Basil's baptism in 357 or 358; "
                   "errors fall toward exclusion (R1).")
# The letters rule A takes out, by div in NPNF2-08: (detail, tombstone, Church act).
EXCLUDED = {
    "npnf208.xml": {
        "ix.ii": ("Rule A, limit 3: Letter 1, to Eustathius the philosopher, written on Basil's "
                  "return from his journey to the monks. The named chronology places his "
                  f"baptism before that journey ({QUASTEN}, pp. 224-225), but {FEDWICK_CHRONOLOGY} "
                  "places it after the letter, so standard sources disagree and the letter "
                  "cannot be shown to date from after it (R1).",
                  T_BEFORE_BAPTISM, None),
        "ix.ix": ("Rule A, limit 1: Letter 8, to the Caesareans, is by Evagrius Ponticus "
                  f"(Bousset, Melcher; {QUASTEN}, p. 247; Fedwick 1981, Spuria), condemned by "
                  "name by the Second Council of Nicaea (787), confirming the fifth council.",
                  T_EVAGRIUS, NICAEA_II),
        **{div: ("Rule A: a letter in the name of the emperor Julian, who had abandoned the "
                 "faith, by the testimony of the Fathers; Quasten calls the correspondence "
                 f"spurious ({QUASTEN}, p. 248), and errors fall toward exclusion (R1).",
                 T_JULIAN, None)
           for div in ("ix.xl", "ix.xli")},
        **{div: (_LIBANIUS, T_NOT_CHRISTIAN, None)
           for div in ("ix.cccxxxi", "ix.cccxxxiii", "ix.cccxxxv", "ix.cccxxxvi",
                       "ix.cccxxxviii", "ix.cccxl", "ix.cccxli", "ix.cccxlii", "ix.cccxliv",
                       "ix.cccxlvii", "ix.cccxlix", "ix.cccl", "ix.ccclii", "ix.cccliii")},
        **{div: (_BEFORE_BAPTISM, T_BEFORE_BAPTISM, None)
           for div in ("ix.cccxxx", "ix.cccxxxii", "ix.cccxxxiv", "ix.cccxxxvii",
                       "ix.cccxxxix")},
    },
}

# Each document's rule A record (works.json `rule_a`), by works.json work_id. Dates are
# ISO with the day unknown, as 3.1's are: baptized in 357 or 358 (Fedwick), written about
# 375, preached before 370 (Quasten).
_BASIL_RULE_A = {
    "applies": True, "communion_start": "0357-01-01", "communion_end": None,
    "chronology_source": f"{QUASTEN}, pp. 224-249 (Quasten's vol. III in English); for the "
                         f"early letters also {FEDWICK_CHRONOLOGY}",
    "church_acts": [], "decision": "include"}
RULE_A = {
    "church-fathers/npnf208/vii": {**_BASIL_RULE_A, "work_date": "0375-01-01",
                                   "decision_basis": "Written about 375 (Quasten, p. 231), long "
                                                     f"after Basil's baptism ({R1_ADDENDUM})."},
    "church-fathers/npnf208/viii": {**_BASIL_RULE_A, "work_date": "0370-01-01",
                                    "decision_basis": "Preached as a presbyter, before 370 "
                                                      "(Quasten, pp. 238-239), after Basil's "
                                                      f"baptism ({R1_ADDENDUM})."},
    "church-fathers/npnf208/ix": {**_BASIL_RULE_A, "work_date": None,
                                  "decision_basis": "Basil's letters date from his retreat to "
                                                    "his death; the letters rule A takes out "
                                                    "(Letters 1 and 8, Julian's, and the "
                                                    "correspondence with Libanius) have removal "
                                                    f"entries ({R1_ADDENDUM})."},
}

# The translator's authenticity judgments in his notes (rule G: judgments first), by
# work_id: (the note's paragraph, the judgment, verdict, whether the plan's label overrides
# it). Read from the notes `ingest.editorial.judgments` flags; the rest of what it flags is
# not about authorship (a doubtful plant, a doubtful identification of a man).
JUDGMENTS = {
    "church-fathers/npnf208/vii": [
        ("vii.xxviii-p4", "The genuineness of this latter portion of the Treatise was objected "
                          "to by Erasmus on the ground that the style is unlike that of "
                          "Basil's soberer writings.", "genuine", False),
    ],
    "church-fathers/npnf208/ix": [
        ("ix.xl-p1", "To be placed probably in 362, if genuine.", "dubious", False),
        ("ix.xli-p1", "If genuine, which is exceedingly doubtful, this letter would be placed "
                      "in the June or July of 362.", "dubious", False),
        ("ix.xlii-p1", "If genuine, of the same date as xl.", "dubious", True),
        ("ix.xliii-p1", "Their genuineness has been contested, but apparently without much "
                        "reason.", "genuine", True),
        ("ix.xliv-p1", "Ranked with the preceding, and of dubious genuineness.", "dubious",
         True),
        ("ix.cxvi-p5", "If the letter is genuine it is wholly unworthy of the Archbishop of "
                       "Cæsarea.", "dubious", False),
        ("ix.clxvii-p3", "This letter is numbered lxv. among those of Gregory of Nazianzus, "
                         "to whom it is to be attributed.", "attributed", False),
        ("ix.cxc-p3", "This doctrinal statement is also found among the works of Gregory of "
                      "Nyssa; but is more probably to be attributed to Basil.", "genuine", True),
        ("ix.xxxix-p1", "This important letter is included as among the works of Gregory of "
                        "Nyssa, as addressed to Peter, bp. of Sebaste, brother of Basil and "
                        "Gregory.", "attributed", True),
        ("ix.xlviii-p3", "On this title Benedictine editors remark that no careful reader can "
                         "fail to note that the letter is written not by Basil but about "
                         "Basil.", "attributed", False),
        ("ix.ccclv-p1", "This letter is almost undoubtedly spurious, but it has a certain "
                        "interest, from the fact of its having been quoted at the so-called 7th "
                        "Council (2d of Nicæa) in 787.", "spurious", False),
        ("ix.ccclvi-p1", "Letters CCCLXI. and CCCLXIII., to Apollinarius, and Letters "
                         "CCCLXII. and CCCLXIV., from Apollinarius to Basil, are condemned as "
                         "indubitably spurious", "spurious", False),
    ],
}


def _entry(**kw) -> dict:
    e = {"id": None, "scope": None, "collection": COLLECTION, "document_id": None,
         "anchor": None, "passage_id": None, "reason": None, "detail": None,
         "tombstone": None, "church_act": None, "span": None, "judgment": None,
         "added_by": ITEM}
    e.update(kw)
    return e


def register(reg: registry.WorkRegistry, documents, today: str) -> list:
    """Register each document's work unless it is; the documents added."""
    added = []
    for d in documents:
        if (d.collection, d.metadata["source_key"]) not in reg.document_by_key:
            registry.register_new_work(reg, d, today)
            added.append(d)
    for w in reg.works:
        if w["work_id"] in RULE_A:
            w["rule_a"] = {**w["rule_a"], **RULE_A[w["work_id"]]}
    return added


def build(reg: registry.WorkRegistry):
    """The NPNF documents and the editor's record, built under `reg` without 5.6a's own
    removals, so every letter is built (and gets a row) whatever rule A decides."""
    bare = registry.WorkRegistry(reg.works, reg.passages, reg.redirects,
                                 [e for e in reg.removals if e.get("added_by") != ITEM],
                                 reg.kept_text, held_texts=reg.held_texts)
    previous = registry.activate(bare)
    try:
        with editorial.recording() as log:
            documents = [d for f in church_fathers.NPNF_WORKS for d in
                         church_fathers.build_documents(os.path.join(church_fathers._SRC_DIR, f))]
    finally:
        registry.activate(previous)
    return documents, log


def rule_a_entries(reg: registry.WorkRegistry, documents, today: str) -> list[dict]:
    out = []
    for d in documents:
        excluded = EXCLUDED.get(d.metadata["source_file"], {})
        for p in d.passages:
            div = p.chapter_key.split("/")[0]
            if div not in excluded:
                continue
            detail, tombstone, act = excluded[div]
            row = reg.row_by_anchor[(d.id, p.anchor)]
            out.append(_entry(scope="passage", document_id=d.id, anchor=row["live_anchor"],
                              passage_id=row["passage_id"], reason="rule-a", detail=detail,
                              tombstone=tombstone, church_act=act, added_on=today))
    built = {p.chapter_key.split("/")[0] for d in documents for p in d.passages}
    missing = {div for f in EXCLUDED.values() for div in f} - built
    if missing:
        raise ValueError(f"rule A names letters the build lacks: {sorted(missing)}")
    return out


def note_entries(documents, today: str) -> list[dict]:
    """1.10b's note count for each document, as the build that drops rule A's letters
    holds it."""
    out = []
    for d in documents:
        excluded = EXCLUDED.get(d.metadata["source_file"], {})
        n = sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages
                if p.chapter_key.split("/")[0] not in excluded)
        out.append(_entry(scope="class", document_id=d.id, reason="rule-g-editorial",
                          detail=NOTE_DETAIL, span={"rule": NOTE_RULE, "count": n},
                          added_on=today))
    return out


def judgments(works: list[dict]) -> None:
    for w in works:
        rows = JUDGMENTS.get(w["work_id"])
        if rows is None:
            continue
        file = w["source_key"].split("/", 1)[1].split("#")[0]
        w["attribution"] = {**w["attribution"], "editorial_judgments": [
            {"source_file": file, "element_id": element, "quote": quote, "verdict": verdict,
             "overridden_by_plan": overridden}
            for element, quote, verdict, overridden in rows]}


def plan(reg: registry.WorkRegistry, today: str):
    """The updated registry, 5.6a's entries, the rights rows and any problems."""
    reg = registry.WorkRegistry([dict(w) for w in reg.works], reg.passages, reg.redirects,
                                reg.removals, reg.kept_text, held_texts=reg.held_texts)
    documents, log = build(reg)
    register(reg, documents, today)
    documents, log = build(reg)
    rec = registry.reconcile(reg, documents, item=ITEM, today=today)
    problems = list(rec.problems)
    # A letter rule A takes out keeps its work (D6), as Cyprian's do: its retired rows
    # name it, since no built passage will.
    excluded = {d.id: EXCLUDED.get(d.metadata["source_file"], {}) for d in documents}
    for r in rec.rows:
        div = r["anchor"].split("/")[0]
        if div in excluded.get(r["document_id"], ()):
            r["work_key"] = div
    base = registry.WorkRegistry(reg.works, rec.rows, rec.redirects, reg.removals,
                                 reg.kept_text, held_texts=reg.held_texts)
    entries, found, more = er.generate(base, documents, log, {}, today, item=ITEM)
    problems += more
    for e in entries:
        if e["detail"] == er.DETAIL["not-english"]:
            e["reason"] = "translation-in-preparation"
    entries = ([e for e in entries if not (e["scope"] == "class" and
                                           (e.get("span") or {}).get("rule") == NOTE_RULE)]
               + rule_a_entries(base, documents, today) + note_entries(documents, today))
    staged, unreviewed = er.plan(base, entries, found, item=ITEM, id_block=IDS)
    if staged is None:
        return None, entries, [], [f"unreviewed judgment: {u}" for u in unreviewed]
    judgments(staged.works)
    problems += registry.validate(staged)
    return staged, entries, rights_rows(documents), problems


def rights_rows(documents) -> list[dict]:
    """The inventory with each NPNF volume's row replaced by one row per built work (R6:
    "The ingesting PR splits them into per-work rows"), each a copy of the volume's facts
    under the work's title, marked built."""
    rows = rights_inventory.load()
    volumes = {}
    for d in documents:
        path = f"church-fathers/{d.metadata['source_file']}"
        built = {"work": d.title, "author": d.author, "document_id": d.id,
                 "planned_for": None, "collection": d.collection}
        mine = next((r for r in rows if r["source_path"] == path and r["document_id"] == d.id),
                    None)
        if mine is not None:
            mine.update(built)
            continue
        volume = volumes.get(path) or next(
            r for r in rows if r["source_path"] == path and r["document_id"] is None)
        volumes[path] = volume
        rows.append({**volume, **built})
    rows = [r for r in rows if not any(r is v for v in volumes.values())]
    rows.sort(key=lambda r: tuple(x or "" for x in rights_inventory.key(r)))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    staged, entries, rows, problems = plan(registry.current(), args.today)
    print(Counter((e["scope"], e["reason"]) for e in entries))
    for p in problems:
        print(f"problem: {p}")
    if problems or staged is None:
        return 1
    if not args.dry_run:
        registry.write_registry(staged)
        rights_inventory.INVENTORY_PATH.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
