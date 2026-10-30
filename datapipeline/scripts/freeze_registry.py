"""Freeze the work registry (corpus-cleanup 2.1), run once.

    cd datapipeline
    python3 scripts/freeze_registry.py --snapshot releases/snapshots/<date>
                                       [--frozen-on YYYY-MM-DD] [--report <dir>] [--dry-run]

Builds every collection with the structural anchors and pairs each built passage with
the live passage it is, from the 0.1c snapshot (what users see), so every live passage
keeps its ID (D1) however its anchor changed:

1. same anchor, when the texts still agree (the anchors 2.1 leaves unchanged);
2. identical text, in reading order (anchors rebuilt from source structure: ThML, Summa);
3. a live unit's display pieces, in order, with the pieces of the built unit that holds
   it, when each keeps half its text (live was cut by an older splitter);
4. the same opening words, when the texts agree (a piece whose cuts moved, a Summa part
   live printed together with the next one), the one with the most text in common.

A live passage still unpaired gets a `merged` redirect to the built passage holding its
text; one with no text at all (an empty part live printed) to the passage paired with
the live passage after it. A built passage live never had is a new unit and takes its ID
from its structural anchor. Anything else stops the freeze.

Refuses to write unless the build yields exactly the snapshot's documents (421; the md5
of their sorted IDs joined by commas is printed). Writes works.json, passages/*.jsonl,
redirects.json and removals.json (empty: an anchor change removes no text). With
--report, writes pairings.json (IDs, anchors, methods and scores; no text) for the PR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict, deque
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import identity  # noqa: E402
import registry  # noqa: E402
from identity import unit_anchor  # noqa: E402
from checks import health as health_cli  # noqa: E402
from checks import report as checks_report  # noqa: E402
from release import remap as R  # noqa: E402
from release import report as release_report  # noqa: E402

ITEM = "2.1"
OPENING_WORDS = 8


def document_hash(ids) -> str:
    return hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()


def pair_document(live: list, built: list) -> tuple[dict, list[dict], list[str]]:
    """{built index: (live passage, method, score)}, the redirects for live passages left
    over, and problems. `live` and `built` are one document's passages in reading order."""
    words_live = [R.words(o.content) for o in live]
    words_built = [R.words(p.content) for p in built]
    pairs: dict[int, tuple] = {}
    taken: set[str] = set()

    def take(i: int, o, method: str, score: float) -> None:
        pairs[i] = (o, method, score)
        taken.add(o.id)

    by_anchor = {p.anchor: i for i, p in enumerate(built)}
    for o in live:
        i = by_anchor.get(o.anchor)
        if i is not None and i not in pairs:
            score = R.similarity(o.content, built[i].content)
            if score >= R.ANCHOR_STABILITY_THRESHOLD:
                take(i, o, "anchor", score)

    # A wordless passage (the Summa's lone ".") is matched on its content as printed.
    def text_key(w: list[str], content: str) -> str:
        return " ".join(w) if w else f"\0{content.strip()}"

    by_text: dict[str, deque] = defaultdict(deque)
    for i, w in enumerate(words_built):
        if i not in pairs and (w or built[i].content.strip()):
            by_text[text_key(w, built[i].content)].append(i)
    for k, o in enumerate(live):
        if o.id in taken or not (words_live[k] or o.content.strip()):
            continue
        queue = by_text.get(text_key(words_live[k], o.content))
        while queue and queue[0] in pairs:
            queue.popleft()
        if queue:
            take(queue.popleft(), o, "text", 1.0)

    # A live unit's display pieces pair, in order, with the pieces of the built unit
    # holding it (found through a member already paired, or by the same unit anchor),
    # as long as each keeps half its text: a live piece keeps its ID although the
    # splitter now cuts a little differently (2.1, as pairing by `live_anchor` would).
    build_units: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(built):
        build_units[unit_anchor(p.anchor)].append(i)
    unit_by_opening: dict[tuple, list[str]] = defaultdict(list)
    for name, members in build_units.items():
        unit_by_opening[tuple(words_built[members[0]][:OPENING_WORDS])].append(name)
    paired_at = {pairs[i][0].id: i for i in pairs}
    position = {o.id: k for k, o in enumerate(live)}
    for unit in R.units(live):
        target = next((unit_anchor(built[paired_at[o.id]].anchor) for o in unit
                       if o.id in paired_at), None)
        if target is None:
            # A unit opens where its first piece opens, however the rest is cut.
            found = unit_by_opening.get(
                tuple(words_live[position[unit[0].id]][:OPENING_WORDS]), [])
            target = found[0] if len(found) == 1 else None
        if target is None:
            base = R._PIECE.sub("", unit[0].anchor)
            target = base if base in build_units else None
        members = build_units.get(target, []) if target is not None else []
        for o, i in zip(unit, members):
            if o.id in taken or i in pairs:
                continue
            score = R.similarity(o.content, built[i].content)
            if score >= R.ANCHOR_STABILITY_THRESHOLD:
                take(i, o, "unit order", score)

    by_opening: dict[tuple, list[int]] = defaultdict(list)
    for i, w in enumerate(words_built):
        if i not in pairs and w:
            by_opening[tuple(w[:OPENING_WORDS])].append(i)
    for k, o in enumerate(live):
        if o.id in taken or not words_live[k]:
            continue
        scored = [(R.similarity(o.content, built[i].content), -i, i)
                  for i in by_opening.get(tuple(words_live[k][:OPENING_WORDS]), [])
                  if i not in pairs]
        scored = [x for x in scored if x[0] >= R.ANCHOR_STABILITY_THRESHOLD]
        if scored:
            score, _, i = max(scored)
            take(i, o, "opening", score)

    paired_index = {pairs[i][0].id: i for i in pairs}
    redirects, problems = [], []
    shingles: list[set] | None = None
    for k, o in enumerate(live):
        if o.id in taken:
            continue
        if not words_live[k]:
            after = next((paired_index[x.id] for x in live[k + 1:] if x.id in paired_index), None)
            before = next((paired_index[x.id] for x in reversed(live[:k])
                           if x.id in paired_index), None)
            target = after if after is not None else before
            method, score = "empty", None
        else:
            if shingles is None:
                shingles = [R.shingles(w) for w in words_built]
            scores = [(R.similarity(o.content, built[i].content), -i, i)
                      for i in _sharing(words_live[k], words_built, shingles)]
            score, _, target = max(scores) if scores else (0.0, 0, None)
            method = "containment"
            if score < R.ANCHOR_STABILITY_THRESHOLD:
                target = None
        if target is None:
            problems.append(f"{o.anchor} ({o.id}): no built passage holds its text")
            continue
        redirects.append({"live": o, "target": target, "method": method, "score": score})
    return pairs, redirects, problems


def _sharing(ws: list[str], built: list[list[str]], shingles: list[set]) -> list[int]:
    """Built passages sharing an 8-word shingle with `ws` (or, for a text under 8
    words, holding all of it)."""
    if len(ws) < R.SHINGLE_WORDS:
        needle = f" {' '.join(ws)} "
        return [i for i, w in enumerate(built) if needle in f" {' '.join(w)} "]
    wanted = R.shingles(ws)
    return [i for i, sh in enumerate(shingles) if wanted & sh]


def freeze(snapshot: str, frozen_on: str) -> tuple[registry.WorkRegistry, dict, list[str]]:
    previous = registry.activate(registry.WorkRegistry())
    try:
        checks_report.placeholder_credentials()
        collections = tuple(checks_report.SOURCE_ADAPTERS)
        build = {c: checks_report.SOURCE_ADAPTERS[c]() for c in collections}
    finally:
        registry.activate(previous)
    live_documents = health_cli.load_snapshot(snapshot, collections)
    documents = [d for c in collections for d in build[c]]
    built_ids = {d.id for d in documents}
    live_ids = {d.id for c in collections for d in live_documents.get(c, [])}
    problems: list[str] = []
    if len(documents) != len(built_ids) or built_ids != live_ids:
        problems.append(f"the build has {len(built_ids)} documents, the snapshot "
                        f"{len(live_ids)}; {len(built_ids ^ live_ids)} differ")
        return registry.WorkRegistry(), {}, problems

    old = release_report.old_passages(live_documents)
    old_by_document: dict[str, list] = defaultdict(list)
    for o in old:
        old_by_document[o.document_id].append(o)

    works, rows, redirects, pairings = [], [], [], []
    methods: Counter = Counter()
    for d in documents:
        key = (d.metadata or {}).get("source_key")
        if not key:
            problems.append(f"{d.collection}/{d.title}: no source_key")
            continue
        works.append(registry.work_entry(collection=d.collection, source_key=key,
                                         document_id=d.id, title=d.title, author=d.author,
                                         frozen_on=frozen_on))
        live = sorted(old_by_document.get(d.id, []), key=lambda o: (o.position, o.id))
        pairs, leftovers, trouble = pair_document(live, d.passages)
        problems += [f"{d.collection}/{d.title}: {t}" for t in trouble]
        ids = {}
        for i, p in enumerate(d.passages):
            if i in pairs:
                o, method, score = pairs[i]
                ids[i] = o.id
                rows.append(_row(o.id, d.id, p.anchor, o.anchor, "active", frozen_on))
                methods[(d.collection, method)] += 1
                if method == "opening":
                    pairings.append(_pairing(d, o, p, method, score))
            else:
                ids[i] = identity.passage_id(d.id, p.anchor)
                rows.append(_row(ids[i], d.id, p.anchor, None, "active", frozen_on))
                methods[(d.collection, "new")] += 1
        for r in leftovers:
            o, p = r["live"], d.passages[r["target"]]
            rows.append(_row(o.id, d.id, o.anchor, o.anchor, "redirected", frozen_on))
            redirects.append({
                "document_id": d.id, "old_passage_id": o.id, "old_anchor": o.anchor,
                "new_passage_id": ids[r["target"]], "new_anchor": p.anchor, "kind": "merged",
                "reason": ("an empty passage the live publication printed; its source "
                           "paragraph opens this passage") if r["method"] == "empty" else
                          "its text now lies inside this passage",
                "added_by": ITEM})
            methods[(d.collection, f"redirect:{r['method']}")] += 1
            pairings.append(_pairing(d, o, p, f"redirect:{r['method']}", r["score"]))

    frozen_ids = Counter(r["passage_id"] for r in rows)
    problems += [f"passage ID {pid} is frozen {n} times" for pid, n in frozen_ids.items() if n > 1]
    anchors = Counter((r["document_id"], r["anchor"]) for r in rows)
    problems += [f"anchor {a} names {n} rows of {doc}" for (doc, a), n in anchors.items() if n > 1]
    missing = {o.id for o in old} - set(frozen_ids)
    problems += [f"live passage {pid} has no row" for pid in sorted(missing)]
    works.sort(key=lambda w: (w["collection"], w["work_id"]))
    rows.sort(key=lambda r: (r["document_id"], r["anchor"]))
    redirects.sort(key=lambda r: (r["document_id"], r["old_anchor"]))
    built = registry.WorkRegistry(works, rows, redirects, [])
    problems += registry.validate(built)
    summary = {"document_md5": document_hash(built_ids), "documents": len(documents),
               "methods": {f"{c}:{m}": n for (c, m), n in sorted(methods.items())},
               "pairings": pairings}
    return built, summary, problems


def _row(passage_id: str, document_id: str, anchor: str, live_anchor: str | None,
         status: str, frozen_on: str) -> dict:
    return {"passage_id": passage_id, "document_id": document_id, "anchor": anchor,
            "live_anchor": live_anchor, "status": status, "frozen_on": frozen_on,
            "work_key": None}


def _pairing(d, o, p, method: str, score) -> dict:
    return {"collection": d.collection, "document": d.title, "passage_id": o.id,
            "live_anchor": o.anchor, "anchor": p.anchor, "method": method,
            "score": None if score is None else round(score, 4)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", required=True, help="releases/snapshots/<date>")
    parser.add_argument("--frozen-on", default=date.today().isoformat())
    parser.add_argument("--report", help="directory for pairings.json")
    parser.add_argument("--dry-run", action="store_true", help="check, write nothing")
    args = parser.parse_args(argv)
    meta, trouble = release_report.verify_snapshot(args.snapshot)
    if trouble:
        for t in trouble:
            print(f"snapshot: {t}", file=sys.stderr)
        return 1
    built, summary, problems = freeze(args.snapshot, args.frozen_on)
    for p in problems[:50]:
        print(f"PROBLEM: {p}", file=sys.stderr)
    if problems:
        print(f"REFUSING: {len(problems)} problems; nothing written", file=sys.stderr)
        return 1
    print(f"{summary['documents']} documents, md5 of sorted IDs {summary['document_md5']}")
    for k, n in summary["methods"].items():
        print(f"  {k}: {n}")
    if args.report:
        os.makedirs(args.report, exist_ok=True)
        with open(os.path.join(args.report, "pairings.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=1)
    if not args.dry_run:
        registry.write_registry(built)
        print(f"wrote {registry.REGISTRY_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
