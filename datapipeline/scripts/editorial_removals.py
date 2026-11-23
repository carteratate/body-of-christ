"""Removal registry entries for what rule G takes out of the ANF volumes (corpus-cleanup
1.8a) and the NPNF Augustine volumes (1.8b), generated from a build.

    cd datapipeline
    python3 scripts/editorial_removals.py --snapshot releases/snapshots/<date>
                                          [--today YYYY-MM-DD] [--dry-run]

Builds the Church Fathers with `ingest.editorial.recording()` on and writes, in place of
the entries the item added before (`added_by`; 1.8a's are the ANF volumes', 1.8b's the
NPNF Augustine volumes'):

- a `passage` entry for each live passage of an editorial div the build now skips
  (Elucidations, editors' notes, translators' notices and introductions), and of a
  chapter or title page whose text was all the editors' (1.8b: the books' summaries,
  the treatises' title pages), by its live anchor and frozen passage ID, with a tombstone;
- a `span` entry for each translator credit, "Argument" summary, letter title line,
  edition source line and bracketed comment cut from a passage that survives, anchored
  on the built passage that held it, with the sha1 of the removed text and an excerpt;
- one `class` entry per document for its heading lines (rule, number and title lines
  that repeat what the chapter label says), with their count; R4's heading lines above
  the Refutation's book contents are `span` entries instead;
- and it keeps 1.10b's per-document note counts in step with the build.

Every entry's `judgment` is the sentence of the removed text that holds an authenticity
word (`ingest.editorial.judgment`), unless `NOT_JUDGMENTS` records that the sentence was
read and is not one. Each judgment is copied into its work's
`attribution.editorial_judgments` in works.json with the verdict `VERDICTS` gives it
(rule G: judgments first). `--dry-run` prints the counts and the judgments found.
Run so, it writes 1.8a's entries; 1.8b's script, `scripts/augustine_registry.py`, calls
`generate` and `plan` for the NPNF files with the volumes split into their works.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402
from ingest import editorial, editorial_keep  # noqa: E402
from publication import build  # noqa: E402

ITEM = "1.8a"
COLLECTION = "church-fathers"
# The files each item's entries cover: 1.8b's are the NPNF Augustine volumes that carry
# rule G's editor (the Confessions has none), 1.8d's Robertson's On the Incarnation in
# NPNF2-04, 1.8a's every other.
NPNF_FILES = frozenset({"city-of-god.xml", "on-the-holy-trinity.xml"})
ITEM_FILES = {"npnf204.xml": "1.8d", "npnf208.xml": "5.6a"}
ITEMS = ("1.8a", "1.8b", "1.8d", "5.6a")
REASON = "rule-g-editorial"
TOMBSTONE = ("This passage was an editor's note and was removed because TheoCorpus shows "
             "only the authors' own words.")
# A passage that held a quotation of Augustine kept as a passage of its own (1.8b).
TOMBSTONE_QUOTED = ("This passage was an editor's note and was removed because TheoCorpus "
                    "shows only the authors' own words. The words of Augustine it quoted are "
                    "kept as their own passage, {labels}.")
DETAIL = {
    "credit": "The translator's credit line",
    "argument": "The editor's \"Argument\" summary at the head of the chapter (C-12)",
    "letter-title": "The editor's title line of the letter (C-02); the sender it names is "
                    "recorded by 1.8c",
    "provenance": "The editor's source line for the fragment (C-22)",
    "bracket": "A bracketed comment by the editor inside the text",
    "section": "The editor's note under its own heading at the end of the chapter",
    "r4-heading": "A heading line above the book's contents (\"Book N.\", \"Contents.\", a "
                  "rule line), as R4 lists; the chapter label keeps the same information",
    "summary": "The editors' summary of the book",
    "section-summary": "The translator's analytical heading of the section (Robertson's italic "
                       "summary, printed after its number), not the author's text",
    "not-english": "Rule E: a paragraph the translator left in Greek, cut from a chapter "
                   "whose English stays (5.6a)",
}
# A chapter whose text was all the editors', by what it held (1.8b).
WHOLE_DETAIL = {
    "argument": "The book's heading lines and the editor's \"Argument\" summary of it (C-12), "
                "not the author's text",
    "summary": "The book's heading lines and the Benedictine editors' summary of it, not the "
               "author's text",
}

EXCERPT = 120

# Sentences the judgment scan flags that were read and are not about who wrote a work
# (sha1 of the sentence -> why). Filled from the review of the flagged list.
NOT_JUDGMENTS: dict[str, str] = {
    "015f2991ff63": "a letter's Argument: a faction is blamed",
    "0c03db0441f3": "an Octavius Argument: things are doubtful",
    "ced306be9204": "an Octavius Argument: doubtful matters",
    "742c3747d0d7": "forget",
    "78aa9f4784e1": "forgetting",
    "149154446fac": "forgetful",
    "21f3df0da4fb": "forgiveness",
    "55ae03873527": "forgive",
    "59fa667d80aa": "forgive",
    "80c42720ef29": "forgive",
    "f9d26ac4ec97": "forgive",
    "853dfcbcfc93": "an Argument: attributed to fate",
    "10f3eb68db1b": "not doubtful what Hippolytus would have said",
    "3b16726c63e2": "the editor will not interpolate his own theory",
    "5127de8a2f20": "Tertullian ascribing jurisdiction to Rome",
    "16eb7bdb2e71": "a sermon of pseudo-Bernard, not a work in the corpus",
    "1e58b4c4c68f": "the forged Decretals, not a work in the corpus",
    "87f0a87e9314": "the forged Decretals",
    "a6892a36170d": "the Isidorian forgeries",
    "d572c648f67b": "the Creed of Pius IV, not a work in the corpus",
    "e9553016630d": "a doctrine, not a text",
    "2f877f31771e": "errors attributed to Origen, not authorship",
    "8f748f9544e9": "a quotation attributed to Tertullian, not a work",
    "411a38409f95": "the Book of Enoch, which Tertullian cites",
    "42248afc6942": "the Book of Enoch",
    "4e67d924c3b0": "the Book of Enoch",
    "7fa3a801be39": "1 John 5:7, which Cyprian cites",
    "78fad364ee67": "an edition by Baluzius",
    "a6cd339b4e47": "an editor's competence",
    "83fe88ad3ad5": "a table of population figures",
    "e656eb57651c": "the date of a manuscript",
    "fb86b33b01ef": "the translator of the Latin version, not the author",
    # The same judgment as another sentence, kept once.
    "2c75a5da61ef": "continues 28526e2edec4",
    "a30509e329d3": "the column heading of bae15dfd4178's comparison",
    "84461337cb27": "same judgment as bae15dfd4178",
    "bc1c621cfa88": "same judgment as bae15dfd4178",
    "7e2fdedf0b99": "same judgment as c5361de18c1a",
    "e032a47489dc": "same judgment as aa76ee1ac016",
    "f3d6d5cae4c3": "same judgment as 2b445c86951f",
    "853c2cbfb962": "a cross-reference to 2b445c86951f's note",
    # 1.8b, the NPNF Augustine volumes.
    "9bf899ad3d37": "forget",
    "440c1c17a604": "forgotten",
    "981ecf335847": "forgiveness",
    "2d744fbd1449": "a doctrine ascribed to the Father, not authorship",
    "bf60422b19dd": "a spurious trinitarianism, not a text",
    "4be31de4e7d0": "genuine devotional feeling",
    "7f2de6eff96a": "Rome's disgrace ascribed to her citizens",
    "45e3cb69942a": "an Argument: the empire ascribed to God",
    "74a39b0132bc": "an Argument: the empire attributed to false gods",
    "79ebee362a30": "an Argument: calamities attributed to the Christian religion",
    "b02e664a0a01": "an Argument: doubtful signification of words",
    # 1.8d, Robertson's analytical headings in On the Incarnation.
    "2deb663e8643": "forgetfulness",
}
# The verdict for each flagged sentence that is an authenticity judgment (sha1 of the
# sentence -> (verdict, overridden_by_plan)). The plan's "Labels for works that stay"
# overrides the editors where it labels the work otherwise.
VERDICTS: dict[str, tuple[str, bool]] = {
    # Treatises Attributed to Cyprian: the plan labels On the Glory of Martyrdom and the
    # Exhortation to Repentance anonymous.
    "40e04bbdbe7d": ("dubious", False),
    "f8e9465f103b": ("dubious", False),
    "28526e2edec4": ("genuine", True),
    "492d81a39075": ("dubious", False),
    "fd14758edd7b": ("dubious", False),
    "797507ea4fb6": ("genuine", True),
    "624b9ea30785": ("attributed", True),
    # Cyprian's On the Unity of the Church: the papal passages of chapter 4.
    "bae15dfd4178": ("interpolated", False),
    # Gregory Thaumaturgus: the Declaration of Faith, the Canonical Epistle, the homilies
    # (the plan: not his).
    "c5361de18c1a": ("dubious", False),
    "aa76ee1ac016": ("spurious", False),
    "4001d1cc8879": ("genuine", False),
    "2d29a9d883f2": ("interpolated", True),
    # Hippolytus: the appendix (the plan: pseudonymous) and the Pentateuch fragments.
    "8630d7530f7f": ("spurious", False),
    "3ca9aea7d5ef": ("dubious", False),
    # Origen's letter to Gregory.
    "c6cb9577ab20": ("genuine", False),
    # Lactantius: the doubtful passages of the Divine Institutes, and the poems (the plan:
    # the Poem on the Passion doubtful).
    "2b445c86951f": ("dubious", False),
    "9b5023b375b2": ("spurious", True),
    "b8e7d865d0cb": ("dubious", False),
    # Victorinus's Commentary on the Apocalypse, Methodius's Oration on the Palms,
    # Pamphilus's Exposition of Acts, Caius's Dialogue, Asterius Urbanus.
    "59ce3f54560c": ("interpolated", False),
    "0f68d2d7101d": ("dubious", False),
    "f32599e6da24": ("dubious", False),
    "373d5afdec04": ("attributed", False),
    "1db1965fd779": ("attributed", False),
    # 1.8b: the Benedictine editors' and translators' notices of three of Augustine's
    # short works, each defending it as his: Concerning Faith of Things Not Seen, On
    # Continence, On Patience.
    "e8927593402c": ("genuine", False),
    "e0b99fa9854e": ("genuine", False),
    "8e71e6c7e4ed": ("genuine", False),
}


def sentence_key(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def live_text(snapshot_dir: str) -> dict[str, str]:
    out = {}
    with gzip.open(os.path.join(snapshot_dir, "passages.jsonl.gz"), "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("collection") == COLLECTION:
                out[row["id"]] = row["content"]
    return out


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1].rstrip() + "…"


_roots: dict[str, dict] = {}


def div_text(file: str, div: str, source_dir: str | None = None) -> str:
    """A div's text as the adapter reads it, notes left out."""
    from ingest.church_fathers import _SRC_DIR, _read_root
    from ingest.common import _extract_p_text
    path = os.path.join(source_dir or _SRC_DIR, file)
    if path not in _roots:
        _roots[path] = {el.get("id"): el for el in _read_root(path).iter() if el.get("id")}
    return _extract_p_text(_roots[path][div])


def _under(unit: str, divs: set[str]) -> str | None:
    parts = unit.split(".")
    for n in range(len(parts), 0, -1):
        d = ".".join(parts[:n])
        if d in divs:
            return d
    return None


def holder(document, chapter_key: str, order: list[str], locator: str) -> str | None:
    """The anchor of the built passage of `chapter_key` that held `locator`, or, for a
    paragraph the build dropped, the one holding the next paragraph it kept, or at a
    chapter's end the one holding the last paragraph before it."""
    pieces = [p for p in document.passages if p.chapter_key == chapter_key]
    if not pieces:
        return None
    if len(pieces) == 1:
        return pieces[0].anchor

    def holding(loc: str):
        return next((p.anchor for p in pieces if any(u == loc for u, _ in p.source_units)),
                    None)

    start = order.index(locator) if locator in order else 0
    for loc in order[start:]:
        if (anchor := holding(loc)) is not None:
            return anchor
    for loc in reversed(order[:start]):
        if (anchor := holding(loc)) is not None:
            return anchor
    return pieces[0].anchor


def item_of(file: str) -> str:
    """The item whose entries cover a source file's removals."""
    if file in ITEM_FILES:
        return ITEM_FILES[file]
    return "1.8b" if file in NPNF_FILES else "1.8a"


def _file_of(source_key: str) -> str:
    return source_key.split("/", 1)[1].split("#")[0]


def generate(reg: registry.WorkRegistry, documents: list, log: list, live: dict[str, str],
             today: str, source_dir: str | None = None, item: str = ITEM):
    """The entries for a build (`documents`, built with `log` recording), the judgments
    found as (entry, work source key, element id, sentence), and any problems. `live`
    holds the live text of the collection's passages by ID. Only the files `item` covers
    (`item_of`) are read."""
    by_key = {d.metadata["source_key"]: d for d in documents}
    # A document an open `document` removal retires (rules A to C, 3.1) is not built; its
    # span and class entries are kept as they stand, below.
    held = registry.removed_document_ids(reg)
    # Likewise a passage another item's `passage` entry retires (a work rule A to C
    # removes from a container, 3.1): its chapter is not built, and the span entries
    # anchored on it are kept as they stand.
    others = {e["passage_id"] for e in registry.open_removals(reg)
              if e["scope"] == "passage" and e.get("added_by") != item}
    retired_anchors = {(r["document_id"], r["anchor"]) for r in reg.passages
                       if r["passage_id"] in others}

    skipped: dict[str, set[str]] = defaultdict(set)      # source file -> skipped div ids
    titles: dict[tuple[str, str], str] = {}              # (file, div) -> its title
    # (file, div) -> the text a chapter or title page whose text was all the editors'
    # held, and the entry's detail (1.8b).
    whole: dict[tuple[str, str], tuple[str, str]] = {}
    chapters = []
    for source_key, div, edit in log:
        file = _file_of(source_key)
        if item_of(file) != item:
            continue
        if isinstance(edit, str):
            skipped[file].add(div)
            titles[(file, div)] = edit.rstrip(".")
        elif isinstance(edit, editorial.TitlePage):
            whole[(file, div)] = ("\n\n".join(edit.paragraphs),
                                  f"The title page of {edit.title.rstrip('.')}, by its "
                                  f"editors, not the author (div {div})")
        else:
            chapters.append((source_key, div, edit))

    entries: list[dict] = []
    problems: list[str] = []
    judgments: list[tuple[dict, str, str]] = []           # (entry, work source_key, element)
    div_entries: dict[tuple[str, str], tuple[str, list[dict], str]] = {}

    def entry(**kw) -> dict:
        e = {"id": None, "scope": None, "collection": COLLECTION, "document_id": None,
             "anchor": None, "passage_id": None, "reason": REASON, "detail": None,
             "tombstone": None, "church_act": None, "span": None, "judgment": None,
             "added_by": item, "added_on": today}
        e.update(kw)
        return e

    # Chapters whose text was all the editors': no built passage holds them.
    kept_chapters = []
    # Chapters another item retires whole: their heading lines still count, as before.
    retired_chapters: set[tuple[str, str]] = set()
    for source_key, div, edit in chapters:
        d = by_key.get(source_key)
        if d is not None and not any(p.chapter_key == div for p in d.passages) \
                and any(doc == d.id and (a == div or a.startswith(div + "/"))
                        for doc, a in retired_anchors):
            retired_chapters.add((source_key, div))
            kept_chapters.append((source_key, div, edit))
        elif d is not None and not any(p.chapter_key == div for p in d.passages) \
                and edit.removed:
            kinds = {r.kind for r in edit.removed}
            kind = "argument" if "argument" in kinds else "summary" if "summary" in kinds \
                else None
            if kind is None:
                problems.append(f"{source_key}#{div}: a chapter left with no text that held "
                                "neither an argument nor a summary")
                continue
            whole[(_file_of(source_key), div)] = (
                "\n\n".join(r.text for r in edit.removed),
                f"{WHOLE_DETAIL[kind]} (div {div})")
        else:
            kept_chapters.append((source_key, div, edit))

    # Passages of the skipped editorial divs, and of the chapters and title pages above.
    # Active rows, and on a rerun the rows this script retired before.
    mine = {e["passage_id"] for e in reg.removals if e.get("added_by") == item}
    rows = [r for r in reg.passages
            if r["status"] == "active" or (r["status"] == "retired" and r["passage_id"] in mine)]
    redirected_by_me = {r["old_passage_id"] for r in reg.redirects if r.get("closed_by") == item}
    rows = [r for r in rows if r["passage_id"] not in redirected_by_me]
    doc_files = {w["document_id"]: (w["source_key"], _file_of(w["source_key"]))
                 for w in reg.works if w["collection"] == COLLECTION
                 and item_of(_file_of(w["source_key"])) == item}
    built = {(d.id, p.anchor) for d in documents for p in d.passages}
    for r in rows:
        if r["document_id"] not in doc_files or (r["document_id"], r["anchor"]) in built:
            continue
        source_key, file = doc_files[r["document_id"]]
        unit = r["anchor"].split("/")[0]
        div = _under(unit, skipped.get(file, set()))
        tombstone = TOMBSTONE
        if div is not None:
            detail = f"{titles[(file, div)]}, by an editor or translator, not the author " \
                     f"(div {div})"
            quoted = [q.label for q in editorial_keep.kept_quotes(file) if q.div == div]
            if quoted:
                tombstone = TOMBSTONE_QUOTED.format(labels=" and ".join(
                    f"\u201c{label}\u201d" for label in quoted))
        elif (file, unit) in whole:
            div, detail = unit, whole[(file, unit)][1]
        else:
            continue                  # a recut piece: registry.reconcile redirects it
        # The div's judgments are read once, from its whole text, and each entry names
        # the first that its own live text holds (a piece cut after the snapshot was
        # never live and names none).
        text = live.get(r["passage_id"]) or ""
        e = entry(scope="passage", document_id=r["document_id"], anchor=r["live_anchor"],
                  passage_id=r["passage_id"], tombstone=tombstone, detail=detail)
        e["_text"] = text
        entries.append(e)
        if (file, div) not in div_entries:
            div_entries[(file, div)] = (
                source_key, [], whole[(file, div)][0] if (file, div) in whole
                else div_text(file, div, source_dir))
        div_entries[(file, div)][1].append(e)

    # Lines and brackets cut from passages that stay, and heading counts.
    headings: Counter = Counter()
    heading_text: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for source_key, div, edit in kept_chapters:
        d = by_key.get(source_key)
        removed = [r for r in edit.removed if r.kind != "label"]
        if not removed or d is None:
            if removed and d is None and reg.document_by_key.get(
                    (COLLECTION, source_key)) not in held:
                problems.append(f"{source_key}#{div}: removals in a document not built")
            continue
        r4 = (_file_of(source_key), div) in editorial.AUTHORIAL_CONTENTS
        for r in removed:
            if r.kind == "heading" and not r4:
                headings[d.id] += 1
                heading_text[d.id].append((source_key, f"{div}-{r.block}", r.text))
                continue
            if (source_key, div) in retired_chapters:
                continue              # its span entries are kept as they stand, below
            anchor = holder(d, div, edit.order, r.block)
            if anchor is None:
                problems.append(f"{source_key}#{div}: {r.kind} {r.block} in no built passage")
                continue
            text = " ".join(r.text.split())
            # R4 (section 4, rule 2) asks for each heading paragraph of the Refutation's
            # book contents as a span entry of its own.
            e = entry(scope="span", document_id=d.id, anchor=anchor,
                      detail=DETAIL["r4-heading" if r.kind == "heading" else r.kind],
                      span={"sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
                            "excerpt": _excerpt(text)})
            e["_text"] = text
            entries.append(e)
            judgments.append((e, source_key, f"{div}-{r.block}"))
    heading_entries = {}
    for doc_id, n in sorted(headings.items()):
        heading_entries[doc_id] = entry(
            scope="class", document_id=doc_id,
            detail="Heading lines above the text that repeat the chapter label: rule lines, "
                   "number lines and title lines",
            span={"rule": "ingest.editorial.classify_lines (heading)", "count": n})
        entries.append(heading_entries[doc_id])
    entries += [json.loads(json.dumps(e)) for e in reg.removals
                if e.get("added_by") == item and e["collection"] == COLLECTION
                and (e["document_id"] in held and e["scope"] in ("span", "class")
                     or e["scope"] == "span"
                     and (e["document_id"], e["anchor"]) in retired_anchors)]

    # Judgments first.
    found = []
    for (file, div), (source_key, members, div_text_) in sorted(div_entries.items()):
        quotes = [q for q in editorial.judgments(div_text_)
                  if sentence_key(q) not in NOT_JUDGMENTS]
        for e in members:
            own = " ".join(e.pop("_text").split())
            e["judgment"] = next((q for q in quotes if q[:60] in own), None)
        found += [(members[0], source_key, div, q) for q in quotes]
    for e, source_key, element in judgments:
        quotes = [q for q in editorial.judgments(e.pop("_text", ""))
                  if sentence_key(q) not in NOT_JUDGMENTS]
        if quotes:
            e["judgment"] = quotes[0]
        found += [(e, source_key, element, q) for q in quotes]
    for doc_id, lines in heading_text.items():
        e = heading_entries[doc_id]
        for source_key, element, text in lines:
            for q in editorial.judgments(text):
                if sentence_key(q) in NOT_JUDGMENTS:
                    continue
                e["judgment"] = e["judgment"] or q
                found.append((e, source_key, element, q))
    for e in entries:
        e.pop("_text", None)
    return entries, found, problems


def sync_note_counts(removals: list[dict], documents: list, today: str,
                     item: str = ITEM) -> None:
    """1.10b's per-document note counts (`class` entries) follow the build: a note inside
    editor matter 1.8a removes is no longer one the passages lost. An entry whose
    document keeps no note closes (entries are never deleted). Only the documents of the
    files `item` covers are synced."""
    counts = {d.id: sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages)
              for d in documents if item_of(_file_of(d.metadata["source_key"])) == item}
    for e in removals:
        if e["scope"] != "class" or (e.get("span") or {}).get("rule") != \
                "common._p_text_without_notes" or e.get("closed_by") \
                or e["collection"] != COLLECTION or e["document_id"] not in counts:
            continue
        n = counts.get(e["document_id"], 0)
        if n:
            e["span"] = {**e["span"], "count": n}
        else:
            e["closed_by"], e["closed_on"] = item, today


def _entry_key(e: dict) -> tuple:
    return (e["scope"], e["document_id"], e.get("anchor"),
            json.dumps(e.get("span"), sort_keys=True))


def plan(reg: registry.WorkRegistry, entries: list[dict], found: list, item: str = ITEM,
         id_block: tuple[int, int] | None = None):
    """The registry with `entries` in place of the item's earlier ones and the judgments
    copied into works.json, and the judgments not yet reviewed (nothing is planned while
    any are). `id_block`, when given, is the (first, last) the item's new IDs come from,
    so items working at once never take the same one."""
    kept = [e for e in reg.removals if e.get("added_by") != item
            or e.get("collection") != COLLECTION]
    numbers = [int(e["id"].split("-")[1]) for e in reg.removals]
    if id_block is None:
        number = max(numbers) + 1
    else:
        first, last = id_block
        number = max((n for n in numbers if first <= n <= last), default=first - 1) + 1
    # An entry keeps its ID across runs: the same scope, anchor and span, counted in
    # order, since one passage can lose the same text twice (two rule lines).
    previous: dict[tuple, list[str]] = defaultdict(list)
    for e in reg.removals:
        if e.get("added_by") == item:
            previous[_entry_key(e)].append(e["id"])
    for e in entries:
        ids = previous.get(_entry_key(e))
        if ids:
            e["id"] = ids.pop(0)
        else:
            e["id"] = f"rm-{number:04d}"
            number += 1
    # A retired piece may be where an earlier recut redirected another piece of the same
    # editorial div (1.10's merges). That redirect closes, and its old ID is retired too.
    retiring = {e["passage_id"] for e in entries if e["scope"] == "passage"}
    rows = {r["passage_id"]: r for r in reg.passages}
    redirects = [dict(r) for r in reg.redirects]
    for r in redirects:
        if (r.get("closed_by") or item) != item or r["new_passage_id"] not in retiring:
            continue
        r["closed_by"], r["closed_on"] = item, entries[0]["added_on"]
        old = rows[r["old_passage_id"]]
        if old["passage_id"] not in retiring:
            e = {**next(x for x in entries if x.get("passage_id") == r["new_passage_id"]),
                 "anchor": old["live_anchor"], "passage_id": old["passage_id"],
                 "judgment": None}
            ids = previous.get(_entry_key(e))
            if ids:
                e["id"] = ids.pop(0)
            else:
                e["id"] = f"rm-{number:04d}"
                number += 1
            entries.append(e)
            retiring.add(old["passage_id"])
    if id_block is not None and number - 1 > id_block[1]:
        raise ValueError(f"{item}: removal IDs run past rm-{id_block[1]}")
    passages = [dict(r) for r in reg.passages]
    for r in passages:
        if r["passage_id"] in retiring:
            r["status"] = "retired"
    removals = sorted(kept + entries,
                      key=lambda e: (e["collection"], e["document_id"], e.get("anchor") or ""))

    works = [dict(w) for w in reg.works]
    index = {w["source_key"]: w for w in works}
    for w in works:
        w["attribution"] = dict(w["attribution"])
        w["attribution"]["editorial_judgments"] = list(
            w["attribution"].get("editorial_judgments") or [])
    unreviewed = []
    for e, source_key, element, quote in found:
        verdict = VERDICTS.get(sentence_key(quote))
        if verdict is None:
            unreviewed.append((sentence_key(quote), source_key, element, quote))
            continue
        w = index.get(source_key)
        if w is None:
            unreviewed.append((sentence_key(quote), source_key, element, "NO WORK ROW"))
            continue
        row = {"source_file": source_key.split("/", 1)[1].split("#")[0],
               "element_id": element, "quote": quote, "verdict": verdict[0],
               "overridden_by_plan": verdict[1]}
        listed = w["attribution"]["editorial_judgments"]
        listed[:] = [j for j in listed if (j["element_id"], j["quote"]) != (element, quote)]
        listed.append(row)
    if unreviewed:
        return None, unreviewed
    return registry.WorkRegistry(works, passages, redirects, removals, reg.kept_text, held_texts=reg.held_texts), []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    reg = registry.current()
    with editorial.recording() as log:
        documents = build(COLLECTION)
    entries, found, problems = generate(reg, documents, log, live_text(args.snapshot),
                                        args.today)
    if problems:
        print("\n".join(problems))
        return 1
    updated, unreviewed = plan(reg, entries, found)
    if updated is not None:
        sync_note_counts(updated.removals, documents, args.today)
    for key, source_key, element, quote in unreviewed:
        print(f"UNREVIEWED {key} {source_key} {element}: {quote}")
    print(Counter(e["scope"] for e in entries), f"{len(found)} judgments")
    if unreviewed:
        print("judgments to review: add each to VERDICTS or NOT_JUDGMENTS; nothing written")
        return 1
    problems = registry.validate(updated)
    if problems:
        print("\n".join(problems[:20]))
        return 1
    if not args.dry_run:
        registry.write_registry(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
