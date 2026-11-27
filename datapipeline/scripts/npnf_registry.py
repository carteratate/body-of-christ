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
  - a `passage` entry for each passage of the letters `EXCLUDED` lists (rule A, or a
    duplicate of a letter built elsewhere), with the reason, detail and tombstone given
    there (never shown: the letters were never published); `RETIRED_IDS` are never given;
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
import dataclasses
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
# 5.6a's removal IDs: rm-11501 to rm-11999, then rm-13001 to rm-15999 once those ran out
# (Carter, 26 Nov 2026; rm-12001 to rm-12999 are 5.4's and 5.6c's).
IDS = ((11501, 11999), (13001, 15999))
COLLECTION = "church-fathers"
NOTE_RULE = "common._p_text_without_notes"
NOTE_DETAIL = ("Translator and editor footnotes (ThML <note>) printed inline in the passages; "
               "only their count is kept, as editor_note_count.")
R1_ADDENDUM = "docs/research/R1-rule-a-dating.md, 5.6a addendum (Basil)"
QUASTEN = "Quasten, Patrología II (BAC 1978)"

T_NOT_CHRISTIAN = "Removed because its author was not a Christian."
T_JULIAN = ("Removed because this letter is in the name of the emperor Julian, who had "
            "abandoned the faith.")
_LIBANIUS = ("Rule A: a letter of Libanius, the pagan sophist, to Basil; its author was not a "
             "Christian (Quasten, p. 245: \"un pagano declarado\").")
# Letter 8 ("To the Caesareans"), now given to Evagrius Ponticus, stays under Carter's
# decision of 24 Nov 2026 (Decision log "Basil's Letter 8 (5.6a)"), labelled as his. The
# removal IDs it had, rm-11522 to rm-11531, are retired, never given again.
RETIRED_IDS = frozenset(f"rm-{n}" for n in range(11522, 11532))
T_DUPLICATE = ("Removed because this letter is Gregory of Nazianzus's Letter 66, which "
               "TheoCorpus gives in his own Select Letters.")
T_EUTYCHES = ("Removed because the Church condemned Eutyches by name, and TheoCorpus leaves "
              "out every work of an author it has condemned by name.")
CONSTANTINOPLE_II = {"issuer": "Second Council of Constantinople", "date": "0553-06-02",
                     "act": "anathema 11", "citation": "https://www.newadvent.org/fathers/3812.htm"}
R1_LEO_GREGORY = R1_ADDENDUM.replace("(Basil)", "(Leo and Gregory the Great)")
# The letters 5.6a takes out, by div: (reason, detail, tombstone, Church act).
EXCLUDED = {
    # NPNF2-07: Cyril and Gregory of Nazianzus are Doctors, and the volume prints no
    # letter by another writer.
    "npnf207.xml": {},
    "npnf208.xml": {
        **{div: ("rule-a",
                 "Rule A: a letter in the name of the emperor Julian, who had abandoned the "
                 "faith, by the testimony of the Fathers; Quasten calls the correspondence "
                 f"spurious ({QUASTEN}, p. 248), and errors fall toward exclusion (R1).",
                 T_JULIAN, None)
           for div in ("ix.xl", "ix.xli")},
        **{div: ("rule-a", _LIBANIUS, T_NOT_CHRISTIAN, None)
           for div in ("ix.cccxxxi", "ix.cccxxxiii", "ix.cccxxxv", "ix.cccxxxvi",
                       "ix.cccxxxviii", "ix.cccxl", "ix.cccxli", "ix.cccxlii", "ix.cccxliv",
                       "ix.cccxlvii", "ix.cccxlix", "ix.cccl", "ix.ccclii", "ix.cccliii")},
        # Letter 167 is Gregory of Nazianzus's Letter 66 (Fedwick), which NPNF2-07 prints in
        # his Select Letters (iv.iv.iii.v): one copy only, Gregory's (Carter, 24 Nov 2026).
        "ix.clxviii": ("duplicate",
                       "Basil's Letter 167 is Gregory of Nazianzus's Letter 66 to Eusebius of "
                       "Samosata, given from his own Select Letters (NPNF2-07, Browne and "
                       "Swallow, document Select Letters, letter iv.iv.iii.v); this copy in "
                       "Jackson's translation is retired (Carter, 24 Nov 2026).",
                       T_DUPLICATE, None),
    },
    # NPNF2-12: Eutyches's letter to Leo (Letter XXI). The other letters to Leo are by
    # writers in communion when they wrote (R1, 5.6a addendum (Leo and Gregory the Great)).
    "npnf212.xml": {
        "ii.iv.xxi": ("rule-a",
                      "Rule A, limit 1: a letter of Eutyches, condemned by name, Second "
                      f"Council of Constantinople (553), anathema 11 ({R1_LEO_GREGORY}).",
                      T_EUTYCHES, CONSTANTINOPLE_II),
    },
    "npnf213.xml": {},
}

# Each document's rule A record (works.json `rule_a`), by works.json work_id. Basil is a
# Doctor of the Church, so limit 2 passes every work of his whatever its date: his letters
# from before his baptism (357 or 358) need no dating. Dates are ISO with the day unknown,
# as 3.1's are: written about 375, preached before 370 (Quasten).
_DOCTOR = "Basil is a Doctor of the Church: limit 2 passes his works whatever their date"
_BASIL_RULE_A = {
    "applies": True, "communion_start": "0357-01-01", "communion_end": None,
    "chronology_source": f"{QUASTEN}, pp. 224-249 (Quasten's vol. III in English)",
    "church_acts": [], "decision": "include"}
_DOCTOR_207 = ("{} is a Doctor of the Church: limit 2 passes his works whatever their date "
               f"({R1_ADDENDUM.replace('(Basil)', '(Cyril and Gregory of Nazianzus)')}).")
_DOCTOR_RULE_A = {"applies": True, "communion_start": None, "communion_end": None,
                  "work_date": None, "chronology_source": None, "church_acts": [],
                  "decision": "include"}
_DOCTOR_212 = ("{} is a Doctor of the Church: limit 2 passes his works whatever their date "
               f"({R1_LEO_GREGORY})")
RULE_A = {
    "church-fathers/npnf212/ii.iv": {
        **_DOCTOR_RULE_A,
        "decision_basis": _DOCTOR_212.format("Leo the Great") + ". The letters to him are by "
                          "writers in communion when they wrote, apart from Eutyches's, which "
                          "has a removal entry."},
    "church-fathers/npnf212/ii.v": {**_DOCTOR_RULE_A,
                                    "decision_basis": _DOCTOR_212.format("Leo the Great") + "."},
    **{key: {**_DOCTOR_RULE_A, "decision_basis": _DOCTOR_212.format("Gregory the Great") + "."}
       for key in ("church-fathers/npnf212/iii.iv", "church-fathers/npnf212/iii.v",
                   "church-fathers/npnf213/ii")},
    "church-fathers/npnf207/ii": {
        "applies": True, "communion_start": None, "communion_end": None,
        "work_date": "0347-01-01", "chronology_source": f"{QUASTEN}, pp. 404-407",
        "church_acts": [], "decision": "include",
        "decision_basis": _DOCTOR_207.format("Cyril of Jerusalem")},
    **{key: {"applies": True, "communion_start": None, "communion_end": None,
             "work_date": None, "chronology_source": None, "church_acts": [],
             "decision": "include",
             "decision_basis": _DOCTOR_207.format("Gregory of Nazianzus")}
       for key in ("church-fathers/npnf207/iii", "church-fathers/npnf207/iv")},
    "church-fathers/npnf208/vii": {**_BASIL_RULE_A, "work_date": "0375-01-01",
                                   "decision_basis": f"{_DOCTOR}; written about 375 "
                                                     f"(Quasten, p. 231) ({R1_ADDENDUM})."},
    "church-fathers/npnf208/viii": {**_BASIL_RULE_A, "work_date": "0370-01-01",
                                    "decision_basis": f"{_DOCTOR}; preached as a "
                                                      "presbyter, before 370 (Quasten, pp. "
                                                      f"238-239) ({R1_ADDENDUM})."},
    "church-fathers/npnf208/ix": {**_BASIL_RULE_A, "work_date": None,
                                  "decision_basis": f"{_DOCTOR}. The letters by "
                                                    "others rule A takes out (Julian's and "
                                                    "Libanius's) have removal entries; "
                                                    "Evagrius's Letter 8 stays by Carter's "
                                                    "decision of 24 Nov 2026 "
                                                    f"({R1_ADDENDUM})."},
}

# The translator's authenticity judgments in his notes (rule G: judgments first), by
# work_id: (the note's paragraph, the judgment, verdict, whether the plan's label overrides
# it). Read from the notes `ingest.editorial.judgments` flags; the rest of what it flags is
# not about authorship (a doubtful plant, a doubtful identification of a man).
JUDGMENTS = {
    "church-fathers/npnf212/ii.iv": [
        ("ii.iv.xvii-p1", "This letter is suspected by Quesnel as being, if not "
                          "spurious, at least the production of some later Leo than our"
                          " own: but he would seem to have hardly sufficient ground for"
                          " his conjecture and the document is interesting as showing "
                          "the existence of Church endowments at the time, and alas! of"
                          " their m",
         "genuine", False),
        ("ii.iv.xxi-p2", "This Letter (XXI.) bears the stamp of genuineness upon it, "
                         "though the Gk.",
         "genuine", False),
    ],
    "church-fathers/npnf212/ii.v": [
        ("ii.v.xviii-p24", "Both Quesnel and the Ballerinii condemn this passage "
                           "inclosed in brackets as spurious.",
         "spurious", False),
        ("ii.v.xxxiii-p4", "The epithet sanctus is of doubtful genuineness here.",
         "dubious", False),
        ("ii.v.xxxvi-p8", "The words in brackets are of doubtful genuineness, and seem "
                          "in themselves a mediæval imitation of Leo’s style.",
         "dubious", False),
        ("ii.v.xxxvi-p8", "The epithet spoils the argument, and is probably an "
                          "interpolation.",
         "dubious", False),
        ("ii.v.xxxvi-p19", "8: the words in brackets are of doubtful authority.",
         "dubious", False),
        ("ii.v.xlvi-p20", "consider as genuine as the one given by the other mss., and "
                          "translated above: in which case they are probably right in "
                          "inferring that Leo used the Sermon more than once, and wrote"
                          " these two endings for two different occasions.",
         "genuine", False),
    ],
    "church-fathers/npnf213/ii": [
        ("ii.v.xxx-p2", "The genuineness of this letter is considered doubtful.",
         "dubious", False),
        ("ii.v.xxx-p2", "It may have been a forgery founded on Epistle CXXII.",
         "dubious", False),
        ("ii.vii.xxx-p2", "Bede’s copy may be regarded as the most authentic, having "
                          "been brought to him from Rome by Nothelm, a.d.",
         "genuine", False),
        ("ii.vii.xxx-p2", "However, he does not give the Preface, which has internal "
                          "evidence of authenticity.",
         "genuine", False),
        ("ii.vii.xxx-p2", "Internal evidence, as well as historic probability, supports"
                          " the superior genuineness of Bede’s copy (Cf.",
         "genuine", False),
        # The scan splits the note at "Cod. ": it reads "This question, with the answer to
        # it, is absent from Bede, and Cod. Lucens, and may be regarded as an interpolation."
        ("ii.vii.xxx-p49", "Lucens , and may be regarded as an interpolation.",
         "dubious", False),
        ("ii.ix.vii-p4", "The genuineness, or at any rate the freedom from "
                         "interpolation, of all these three Epistles is disputed.",
         "dubious", False),
        ("ii.ix.vii-p4", "The Benedictine Editors of Gregory’s works defend their "
                         "authenticity.",
         "dubious", False),
        ("ii.x.viii-p3", "The genuineness of this epistle is, to say the least, open to"
                         " grave suspicion.",
         "spurious", False),
        ("ii.x.viii-p3", "Spur.) rejects it as spurious.",
         "spurious", False),
        ("ii.x.viii-p3", "Nor is it difficult to understand why such a letter may have "
                         "been forged.",
         "spurious", False),
        ("ii.x.viii-p3", "Such a letter, too, if forged, would be likely to attempt an "
                         "imitation of Gregory’s style, and to bring in (as this does) "
                         "extracts from his previous writings.",
         "spurious", False),
    ],
    "church-fathers/npnf207/ii": [
        ("ii.iv-p93", "It is doubtful whether this caution proceeded from Cyril himself when "
                      "issuing a written copy of his Lectures, or from some later editor.",
         "dubious", False),
        ("ii.xxiii-p4", "This general title of the five following Lectures is omitted in many "
                        "mss.", "dubious", False),
    ],
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


def seed_works(reg: registry.WorkRegistry, documents) -> None:
    """Give each document's entry a `works` row for every work the full build holds (rule
    A's letters included, which their retired rows still name), where it has none yet;
    `document_facts_registry.py` then adds the labels, as for any work."""
    by_id = {d.id: d for d in documents}
    for w in reg.works:
        d = by_id.get(w["document_id"])
        if d is None or not d.works:
            continue
        have = {x["work_key"] for x in w.get("works", [])}
        rows = list(w.get("works", []))
        rows += [{**dataclasses.asdict(x), "ordinal": len(rows) + k}
                 for k, x in enumerate((x for x in d.works if x.work_key not in have), 1)]
        w["works"] = rows


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
            reason, detail, tombstone, act = excluded[div]
            row = reg.row_by_anchor[(d.id, p.anchor)]
            out.append(_entry(scope="passage", document_id=d.id, anchor=row["live_anchor"],
                              passage_id=row["passage_id"], reason=reason, detail=detail,
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
    seed_works(reg, documents)
    rec = registry.reconcile(reg, documents, item=ITEM, today=today)
    problems = list(rec.problems)
    # Every row names its passage's work (D6), from the full build, so a letter rule A
    # takes out keeps its work, as Cyprian's do: its retired rows still name it.
    work_keys = {(d.id, p.anchor): p.work_key for d in documents for p in d.passages}
    for r in rec.rows:
        key = work_keys.get((r["document_id"], r["anchor"]))
        if key is not None:
            r["work_key"] = key
    base = registry.WorkRegistry(reg.works, rec.rows, rec.redirects, reg.removals,
                                 reg.kept_text, held_texts=reg.held_texts)
    entries, found, more = er.generate(base, documents, log, {}, today, item=ITEM)
    problems += more
    for e in entries:
        if e["detail"] == er.DETAIL["not-english"]:
            # By hash only, as 3.3's rule-E entries are: no excerpt of the text cut.
            e["reason"] = "translation-in-preparation"
            e["span"] = {"rule": "ingest.church_fathers.NOT_ENGLISH",
                         "sha1": e["span"]["sha1"]}
    entries = ([e for e in entries if not (e["scope"] == "class" and
                                           (e.get("span") or {}).get("rule") == NOTE_RULE)]
               + rule_a_entries(base, documents, today) + note_entries(documents, today))
    base = registry.WorkRegistry(base.works, base.passages, base.redirects,
                                 [e for e in base.removals if e["id"] not in RETIRED_IDS],
                                 base.kept_text, held_texts=base.held_texts)
    staged, unreviewed = er.plan(base, entries, found, item=ITEM, id_block=IDS)
    if staged is not None and {e["id"] for e in staged.removals} & RETIRED_IDS:
        raise ValueError("a retired removal ID was given again")
    if staged is None:
        return None, entries, [], [f"unreviewed judgment: {u}" for u in unreviewed]
    # A count (a `class` entry) is the same entry when only its count changes: it keeps
    # its ID.
    counts = {(e["document_id"], e["span"]["rule"]): e["id"] for e in reg.removals
              if e.get("added_by") == ITEM and e["scope"] == "class"}
    for e in staged.removals:
        if e.get("added_by") == ITEM and e["scope"] == "class":
            e["id"] = counts.get((e["document_id"], e["span"]["rule"]), e["id"])
    # An entry that keeps its ID keeps the date it was first added, so a rerun changes
    # only what it adds or closes.
    first_added = {e["id"]: e["added_on"] for e in reg.removals if e.get("added_by") == ITEM}
    for e in staged.removals:
        if e.get("added_by") == ITEM and e["id"] in first_added:
            e["added_on"] = first_added[e["id"]]
    staged = lifted(reg, staged, today)
    judgments(staged.works)
    problems += registry.validate(staged)
    return staged, entries, rights_rows(documents), problems


def lifted(before: registry.WorkRegistry, staged: registry.WorkRegistry,
           today: str) -> registry.WorkRegistry:
    """`staged` with each of 5.6a's earlier passage entries that this run no longer writes
    (an exclusion lifted, a letter back) kept, closed, as the record of the removal, and
    the passage rows nothing retires any more active again, under their frozen IDs. An
    entry under `RETIRED_IDS` is dropped, its rows active again."""
    written = {e["id"] for e in staged.removals}
    mine = [e for e in before.removals if e.get("added_by") == ITEM
            and e["scope"] == "passage" and e["id"] not in written]
    # Entries closed on an earlier run stay as they were; those this run drops close now.
    closed = [e if e.get("closed_by") else {**e, "closed_by": ITEM, "closed_on": today}
              for e in mine]
    # An entry under a retired ID is taken out, not kept closed: it never reached a
    # publish, and Carter withdrew it (Letter 8, 24 Nov 2026).
    removals = sorted(staged.removals + [e for e in closed if e["id"] not in RETIRED_IDS],
                      key=lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""))
    explained = {e["passage_id"] for e in removals
                 if e["scope"] == "passage" and not e.get("closed_by")}
    back = {e["passage_id"] for e in closed
            if e["closed_on"] == today or e["id"] in RETIRED_IDS} - explained
    rows = [{**r, "status": "active"} if r["passage_id"] in back else r
            for r in staged.passages]
    return registry.WorkRegistry(staged.works, rows, staged.redirects, removals,
                                 staged.kept_text, held_texts=staged.held_texts)


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
        # A volume of two authors has a row for each (NPNF2-07: Cyril, Gregory).
        key = (path, d.author)
        volume = volumes.get(key) or next(
            r for r in rows if r["source_path"] == path and r["document_id"] is None
            and r["author"] == d.author)
        volumes[key] = volume
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
