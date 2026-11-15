"""Removal registry entries for the works rules A to C exclude (corpus-cleanup 3.1).

    cd datapipeline
    python3 scripts/rule_removals.py [--today YYYY-MM-DD] [--dry-run]

Writes, in place of the entries 3.1 added before (`added_by`), the removals Carter approved
on 15 Nov 2026:

- rule A, read from `registry/rule_a_R1.json`: a `document` entry for each corpus work R1
  excludes (Origen, Tertullian's seven, Novatian's two, Tatian, Arnobius, Alexander of
  Lycopolis, the Refutation of All Heresies), and `passage` entries for each work R1
  excludes inside a container (Novatian's Treatises I and III among Cyprian's, Hippolytus's
  undatable works, Gregory's Panegyric to Origen, the Phoenix, and Epistles XXV, XXIX and
  XXX in Cyprian's Epistles);
- rule B: the Apostolic Constitutions (Books I to VII whole, Book VIII before its canons),
  the six forged Ignatius letters and the Sectional Confession;
- rule C: Pfaff's Irenaeus fragments XXXVI to XXXIX and the four medieval Latin Ignatius
  letters.

A partial target is every passage-registry row of the document whose anchor lies in one of
the target's ThML divs, by its live anchor (2.1, never a position), set `retired`. Where an
earlier recut redirected a piece into one of them, that redirect is closed and the piece
retired too, as 3.3 does; a row an earlier item already retired keeps its own entry. Rule G
adds nothing here: 1.8a to 1.9 recorded its whole list (Carter, 15 Nov 2026). The long
Ignatian recension stays 1.8c's `span` entries.

It keeps 1.10b's per-document note counts (`class` entries of rule
`common._p_text_without_notes`) in step with the build, as `language_removals.py` does:
a document that loses passages gets its count rebuilt, and a removed document's entry
closes, since none of its notes is built any more.

Each `document` and `passage` entry carries the tombstone Carter approved. A rule-A entry
cites its Church act where one exists (Origen, Novatian); otherwise its detail states the
basis, the named chronology, the testimony of the Fathers or that the author was not a
Christian (Carter, 15 Nov 2026). IDs run from rm-5001 (3.1's block), in the order planned.
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

ITEM = "3.1"
FIRST_ID = 5001
LAST_ID = 6999
NOTE_RULE = "common._p_text_without_notes"
R1_FILE = os.path.join(registry.REGISTRY_DIR, "rule_a_R1.json")

# --------------------------------------------------------------------------- Church acts

ORIGEN_ACT = {"issuer": "Second Council of Constantinople", "date": "0553-06-02",
              "act": "anathema 11", "citation": "https://www.newadvent.org/fathers/3812.htm"}
# The day is unknown; the year is 251 (R1).
NOVATIAN_ACT = {"issuer": "Roman synod under Pope Cornelius", "date": "0251-01-01",
                "act": "excommunication of Novatian",
                "citation": "https://www.newadvent.org/fathers/250106.htm"}
TRULLO_ACT = {"issuer": "Council in Trullo", "date": "0692-01-01",
              "act": "canon 2, confirmed by the Second Council of Nicaea, canon 1",
              "citation": "https://www.newadvent.org/fathers/3814.htm"}

# --------------------------------------------------------------------------- tombstones

def _condemned(name: str) -> str:
    return (f"Removed because the Church condemned {name} by name, and TheoCorpus leaves "
            "out every work of an author it has condemned by name.")


def _broke(name: str) -> str:
    return (f"Removed because {name} later left the Church, and this work cannot be shown "
            "to date from before the break.")


T_NOVATIAN_LETTER = ("Removed because Novatian wrote this letter in the name of the Roman "
                     "clergy, and the Church later condemned him by name.")
T_HIPPOLYTUS = ("Removed because Hippolytus led a rival group in Rome from about 217 to "
                "235, and this work cannot be shown to date from before that split.")
T_ARNOBIUS = "Removed because Arnobius wrote this before he was baptized."
T_NOT_CHRISTIAN = "Removed because its author was not a Christian."
T_PANEGYRIC = ("Removed because Gregory gave this speech around the time of his conversion, "
               "and it cannot be shown to date from after his baptism.")
T_PHOENIX = ("Removed because this poem cannot be shown to date from after Lactantius "
             "became a Christian, and it may not be his.")
T_CONSTITUTIONS = ("Removed because the Church set these books aside as altered by "
                   "heretics, although they claim to come from the Apostles.")
T_IGNATIUS_FORGED = ("Removed because this letter falsely claims to be by Ignatius, and "
                     "most scholars judge that its writer was a heretic.")
T_SECTIONAL = ("Removed because this creed falsely claims to be by Gregory the "
               "Wonder-Worker, and scholars identify its writer as the heretic Apollinaris.")
T_PFAFF = ("Removed because this fragment was forged under Irenaeus's name and first "
           "published in 1715.")
T_IGNATIUS_LATIN = ("Removed because this letter was written in the Middle Ages under "
                    "Ignatius's name.")

# --------------------------------------------------------------------------- rule A

QUASTEN = "Quasten, Patrology II"
_NOVATIAN_DETAIL = ("Rule A, limit 1: a work of Novatian, condemned by name by the Roman "
                    "synod under Pope Cornelius (251; Eusebius, Church History 6.43) (R1).")
_TERTULLIAN_DETAIL = ("Rule A, limit 3: written after Tertullian's break with the Church, or "
                      f"not datable before it, on the named chronology ({QUASTEN}, pp. "
                      "290-319); Benedict XVI's general audience of 30 May 2007 describes the "
                      "break (R1).")
_HIPPOLYTUS_DETAIL = ("Rule A, limit 3: Hippolytus led a rival group in Rome from 217 to about "
                      "235; on the named chronology "
                      f"({QUASTEN}, pp. 163-207) this work dates from the schism or cannot be "
                      "dated before it (R1; Decision log \"Hippolytus\").")

# The rule-A group of each document R1 excludes, whole or in part, by ID prefix. Every
# exclusion in R1's file must fall in one, and every one listed must be used (`targets`
# checks both ways).
_RULE_A_BY_PREFIX = {
    "4c96eac3": ("origen",), "9c052574": ("origen",), "5a05852b": ("origen",),
    "0f23bbcf": ("novatian",), "2f22d9b5": ("novatian",),
    "d2b71f9f": ("tertullian",), "e5d235f3": ("tertullian",), "89201a06": ("tertullian",),
    "6b70b67f": ("tertullian",), "01abb5ad": ("tertullian",), "d7f29587": ("tertullian",),
    "17b7747f": ("tertullian",),
    "356b9c9b": ("tatian",), "85e7153f": ("arnobius",), "0d274c4c": ("alexander",),
    "c7a1cced": ("hippolytus",),
    # Containers: R1 excludes works inside them.
    "5d75dc92": ("novatian",), "506ebe31": ("hippolytus",), "685b8763": ("panegyric",),
    "8b42a526": ("phoenix",), "aaf1a0e4": ("cyprian-letters",),
}

_GROUPS = {
    "origen": ("Rule A, limit 1: Origen condemned by name, Second Council of Constantinople "
               "(553), anathema 11 (R1).", _condemned("Origen"), ORIGEN_ACT),
    "novatian": (_NOVATIAN_DETAIL, _condemned("Novatian"), NOVATIAN_ACT),
    "tertullian": (_TERTULLIAN_DETAIL, _broke("Tertullian"), None),
    "tatian": ("Rule A, limit 3: Tatian left the Church after Justin's death, on the "
               "testimony of the Fathers (Irenaeus, Against Heresies 1.28.1; Eusebius, Church "
               "History 4.28-29); the Address's date relative to the break is disputed (R1).",
               _broke("Tatian"), None),
    "arnobius": ("Rule A, limit 3: written before Arnobius's baptism, on the named chronology "
                 f"(Jerome, Chronicle; {QUASTEN}, p. 384) (R1).", T_ARNOBIUS, None),
    "alexander": ("Rule A: its author was not a Christian but a pagan Platonist (van Oort "
                  "2012) (R1).", T_NOT_CHRISTIAN, None),
    "hippolytus": (_HIPPOLYTUS_DETAIL, T_HIPPOLYTUS, None),
    "panegyric": ("Rule A, limit 3: delivered in 238, around Gregory's conversion; no source "
                  "places it after his baptism, on the named chronology "
                  f"({QUASTEN}, pp. 123-124) (R1; Decision log \"Undatable convert works\").",
                  T_PANEGYRIC, None),
    "phoenix": ("Rule A, limit 3: not datable after Lactantius's conversion on the named "
                f"chronology ({QUASTEN}, pp. 403-404), and its attribution is questioned (R1; "
                "Decision log \"Undatable convert works\").", T_PHOENIX, None),
}

# Cyprian's Epistles (C-02): the letters by Novatian, each with its own evidence.
_CYPRIAN_LETTERS = {
    "iv.iv.xxx": ("Rule A, limit 1: Novatian wrote this letter for the Roman clergy, as "
                  "Cyprian says (Epistle LI to Antonianus, Oxford Ep. 55); condemned by name "
                  "by the Roman synod under Pope Cornelius (251) (C-02; Decision log "
                  "\"Letters in Cyprian's Epistles (C-02)\")."),
    "iv.iv.xxix": ("Rule A, limit 1: Oxford Ep. 36, composed by Novatian in the name of the "
                   "Roman presbyters and deacons, \"as contents and style prove\" "
                   f"({QUASTEN}, p. 213); condemned by name by the Roman synod under Pope "
                   "Cornelius (251) (C-02; Carter, 15 Nov 2026)."),
    "iv.iv.xxv": ("Rule A, limit 1: Oxford Ep. 31, sent by the Roman confessors and \"most "
                  "probably also of Novatian's pen\" (B. Melin, reported by "
                  f"{QUASTEN}, p. 226); errors fall toward exclusion; condemned by name by the "
                  "Roman synod under Pope Cornelius (251) (C-02; Carter, 15 Nov 2026)."),
}

# --------------------------------------------------------------------------- rules B and C

_CONSTITUTIONS_DETAIL = ("Rule B: the Apostolic Constitutions claim the Apostles as their "
                         "authors; the Council in Trullo (692), canon 2, confirmed by the "
                         "Second Council of Nicaea (787), canon 1, set them aside as falsified "
                         "by heretics. The Apostolic Canons at the end of Book VIII stay "
                         "(rule D).")
_IGNATIUS_DETAIL = ("Rule B: the letter claims Ignatius as its author and is one of the "
                    "spurious letters added by the compiler of the long recension, whom the "
                    "majority of standard scholarship judges heterodox; no Church act names "
                    "it (Decision log \"Rule B on scholarship alone\").")

# (reason, detail, tombstone, Church act, document prefix, divs or None for the whole
# document).
RULES_B_C = [
    *[("rule-b", _CONSTITUTIONS_DETAIL, T_CONSTITUTIONS, TRULLO_ACT, p, None)
      for p in ("d72938c6", "df17e279", "df6fd2f7", "aab0848e", "49437294", "f04e045b",
                "fd6550b9")],
    # Book VIII: Sections I to V; the canons (`ix.ix.vi`) stay.
    ("rule-b", _CONSTITUTIONS_DETAIL, T_CONSTITUTIONS, TRULLO_ACT, "10d8d7c6",
     ("ix.ix.i", "ix.ix.ii", "ix.ix.iii", "ix.ix.iv", "ix.ix.v")),
    *[("rule-b", _IGNATIUS_DETAIL, T_IGNATIUS_FORGED, None, p, None)
      for p in ("7073bae0", "4fe41814", "56add0dd", "567be8a5", "0311d705", "5553da19")],
    ("rule-b", "Rule B: the creed claims Gregory Thaumaturgus as its author; standard "
     "scholarship (Caspari 1879, Lietzmann 1904; CPG 3645) identifies its writer as "
     "Apollinaris of Laodicea; no Church act names it (Decision log \"Rule B on "
     "scholarship alone\").", T_SECTIONAL, None, "44fd52c3", ("iii.iv.i",)),
    ("rule-c", "Rule C: Pfaff's fragments XXXVI to XXXIX, first published by C. M. Pfaff in "
     "1715, are his forgeries (Harnack 1900).", T_PFAFF, None, "0066869a",
     ("ix.viii.xxxvi", "ix.viii.xxxvii", "ix.viii.xxxviii", "ix.viii.xxxix")),
    *[("rule-c", "Rule C: a medieval Latin letter under Ignatius's name (CPG 1028), written "
       "long after 750.", T_IGNATIUS_LATIN, None, p, None)
      for p in ("76b8b853", "63e7f0b7", "830a2c63", "1a0a016b")],
]


# --------------------------------------------------------------------------- planning

def _inside(anchor: str, divs) -> bool:
    """Whether a passage anchor lies in one of the ThML divs: the div itself, a div under
    it, or one of its pieces."""
    anchor = anchor.split("#")[0]
    return any(anchor == d or anchor.startswith(d + ".") or anchor.startswith(d + "/")
               for d in divs)


def _document(reg: registry.WorkRegistry, prefix: str) -> dict:
    hits = [w for w in reg.works if w["document_id"].startswith(prefix)]
    if len(hits) != 1:
        raise ValueError(f"document {prefix}: {len(hits)} works.json entries")
    return hits[0]


def targets(reg: registry.WorkRegistry, r1: list[dict]) -> list[tuple]:
    """Every target as (reason, detail, tombstone, Church act, document ID, divs or None),
    rule A's from R1's file in its order, then rules B and C."""
    out, seen = [], set()
    for e in r1:
        if "document_id" not in e or e["rule_a"]["decision"] != "exclude":
            continue
        doc = e["document_id"]
        group = _RULE_A_BY_PREFIX.get(doc[:8], (None,))[0]
        if group is None:
            raise ValueError(f"R1 excludes {e['title']} ({doc}); 3.1 does not place it")
        div = e.get("div_id")
        if group == "cyprian-letters":
            detail, tombstone, act = _CYPRIAN_LETTERS[div], T_NOVATIAN_LETTER, NOVATIAN_ACT
        else:
            detail, tombstone, act = _GROUPS[group]
        if _document(reg, doc[:8])["document_id"] != doc:
            raise ValueError(f"R1's {doc} is not the registered document")
        out.append(("rule-a", detail, tombstone, act, doc, (div,) if div else None))
        seen.add(doc[:8])
    unused = set(_RULE_A_BY_PREFIX) - seen
    if unused:
        raise ValueError(f"listed for rule A but not excluded by R1: {sorted(unused)}")
    for reason, detail, tombstone, act, prefix, divs in RULES_B_C:
        out.append((reason, detail, tombstone, act, _document(reg, prefix)["document_id"],
                    divs))
    return out


def plan(reg: registry.WorkRegistry, r1: list[dict], today: str) -> list[dict]:
    """3.1's entries, numbered from rm-5001."""
    collection_of = {w["document_id"]: w["collection"] for w in reg.works}
    rows_by_doc: dict[str, list[dict]] = {}
    for r in reg.passages:
        rows_by_doc.setdefault(r["document_id"], []).append(r)
    rows = {r["passage_id"]: r for r in reg.passages}
    # Rows other items retired keep their own entries.
    others = {e["passage_id"] for e in registry.open_removals(reg)
              if e["scope"] == "passage" and e.get("added_by") != ITEM}
    redirect_of = {r["old_passage_id"]: r for r in reg.redirects
                   if not r.get("closed_by") or r.get("closed_by") == ITEM}
    entries: list[dict] = []

    def add(**fields) -> None:
        n = FIRST_ID + len(entries)
        if n > LAST_ID:
            raise ValueError("3.1's removal IDs run out at rm-6999")
        entries.append({"id": f"rm-{n}", **fields, "span": None, "judgment": None,
                        "added_by": ITEM, "added_on": today})

    partial: list[tuple] = []
    for reason, detail, tombstone, act, doc, divs in targets(reg, r1):
        common = dict(collection=collection_of[doc], document_id=doc, reason=reason,
                      detail=detail, tombstone=tombstone, church_act=act)
        if divs is None:
            add(scope="document", anchor=None, passage_id=None, **common)
        else:
            partial.append((doc, divs, common))
    for doc, divs, common in partial:
        inside = [r for r in rows_by_doc[doc] if _inside(r["anchor"], divs)]
        if not inside:
            raise ValueError(f"{doc} {divs}: no passage rows")
        retiring = {r["passage_id"] for r in inside if r["passage_id"] not in others}
        # A piece redirected into a retired passage holds the same text: it goes too.
        for old, red in redirect_of.items():
            if red["new_passage_id"] in retiring and rows[old]["document_id"] == doc:
                retiring.add(old)
        for r in inside:
            red = redirect_of.get(r["passage_id"])
            if r["passage_id"] in retiring and red and red["new_passage_id"] not in retiring:
                raise ValueError(f"{r['anchor']} redirects out of the target to "
                                 f"{red['new_anchor']}: settle it by hand")
        for pid in sorted(retiring, key=lambda p: rows[p]["live_anchor"]):
            add(scope="passage", anchor=rows[pid]["live_anchor"], passage_id=pid, **common)
    return entries


def apply(reg: registry.WorkRegistry, entries: list[dict], today: str) -> None:
    """Replace 3.1's earlier entries with `entries`, set the rows they retire `retired`,
    close the redirects of the pieces they retire, and drop those passages' kept-text
    entries. Run once on a registry 3.1 has not touched, or again on its own output."""
    retiring = {e["passage_id"] for e in entries if e["scope"] == "passage"}
    # Among entries with the same key, 3.1's come first, where the other items'
    # generators leave them when they re-sort the file.
    reg.removals[:] = sorted(
        entries + [e for e in reg.removals if e.get("added_by") != ITEM],
        key=lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""))
    reg.kept_text[:] = [e for e in reg.kept_text if e["passage_id"] not in retiring]
    for r in reg.redirects:
        if r["old_passage_id"] in retiring and not r.get("closed_by"):
            r["closed_by"], r["closed_on"] = ITEM, today
    for r in reg.passages:
        if r["passage_id"] in retiring:
            if r["status"] not in ("active", "retired", "redirected"):
                raise ValueError(f"{r['anchor']}: status {r['status']}")
            r["status"] = "retired"


def sync_note_counts(reg: registry.WorkRegistry, entries: list[dict], documents,
                     today: str) -> None:
    """Keep 1.10b's note counts in step: a removed document's count closes (`closed_by`
    3.1), and a document that loses passages counts the notes its built passages still
    hold. `documents`: the Church Fathers build, with these entries applied."""
    removed = {e["document_id"] for e in entries if e["scope"] == "document"}
    touched = {e["document_id"] for e in entries if e["scope"] == "passage"}
    counts = {d.id: sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages)
              for d in documents if d.id in touched}
    for e in reg.removals:
        if e["scope"] != "class" or (e.get("span") or {}).get("rule") != NOTE_RULE:
            continue
        if e["document_id"] in removed and e.get("closed_by") in (None, ITEM):
            e["closed_by"], e["closed_on"] = ITEM, e.get("closed_on") or today
        elif e["document_id"] in counts and not e.get("closed_by"):
            e["span"]["count"] = counts[e["document_id"]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    reg = registry.current()
    with open(R1_FILE, encoding="utf-8") as f:
        r1 = json.load(f)
    # Keep the date of an unchanged entry, so a rerun changes nothing.
    added_on = {e["id"]: e["added_on"] for e in reg.removals if e.get("added_by") == ITEM}
    entries = plan(reg, r1, args.today)
    for e in entries:
        e["added_on"] = added_on.get(e["id"], e["added_on"])
    counts = {s: sum(e["scope"] == s for e in entries) for s in ("document", "passage")}
    print(f"{len(entries)} entries ({counts}), rm-{FIRST_ID} to "
          f"rm-{FIRST_ID + len(entries) - 1}")
    if args.dry_run:
        return
    apply(reg, entries, args.today)
    registry.activate(reg)        # the build drops what these entries retire
    from ingest.church_fathers import build_all
    sync_note_counts(reg, entries, build_all(), args.today)
    problems = registry.validate(reg)
    if problems:
        raise SystemExit("registry invalid:\n" + "\n".join(problems[:20]))
    registry.write_registry(reg)


if __name__ == "__main__":
    main()
