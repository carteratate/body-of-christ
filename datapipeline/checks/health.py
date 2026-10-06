"""Health report (0.1b).

    python3 -m checks.health --collection all|<name> [--out <dir>] [--from-snapshot <path>]

Runs the block rules (H1 to H5) and report rules (R1 to R8) of datapipeline/health.py on
the documents SOURCE_ADAPTERS builds, or with --from-snapshot on the live snapshot 0.1c
exports (its passages.jsonl.gz, or the directory holding it), and writes <out>/health.json
and <out>/health.md: counts per rule and collection, and the first anchors of each.

The build and the snapshot are kept apart in health.json. A run replaces only the rows of
the source and the collections it covered, and keeps everything else already in <out>, so
running once on the build and once with --from-snapshot into one --out puts live and build
side by side in health.md. Both files hold numbers, IDs and anchors only, no passage text.

Exits 1 when the build has a block violation that is not in checks/known_defects.json,
which is exactly what the publish gate would refuse. A snapshot's violations are reported,
never failed: the live publication is what the cleanup replaces.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import health  # noqa: E402
from checks import report  # noqa: E402
from model import Document, Passage  # noqa: E402

SNAPSHOT_FILE = "passages.jsonl.gz"
# Anchors listed per rule and collection in health.md.
ANCHORS_LISTED = 5
SOURCES = ("build", "snapshot")


# --------------------------------------------------------------------------- inputs

def load_snapshot(path: str, collections: list[str] | tuple[str, ...] | None = None
                  ) -> dict[str, list[Document]]:
    """The 0.1c snapshot's passages as Documents, per collection. Each row has id,
    document_id, collection, title, author, anchor, chapter_key, chapter_label,
    reference, position and content. Passages are put in position order, so H3 judges
    whether the positions are 0..n-1, not the export's row order. Every requested
    collection gets an entry, empty if the snapshot holds none of its rows, so a rerun
    replaces an earlier result for it."""
    if os.path.isdir(path):
        path = os.path.join(path, SNAPSHOT_FILE)
    documents: dict[str, Document] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if collections is not None and row["collection"] not in collections:
                continue
            doc = documents.get(row["document_id"])
            if doc is None:
                doc = documents[row["document_id"]] = Document(
                    id=row["document_id"], collection=row["collection"],
                    title=row.get("title") or "", author=row.get("author"))
            doc.passages.append(Passage(
                content=row.get("content") or "", reference=row.get("reference") or "",
                anchor=row.get("anchor") or "", chapter_key=row.get("chapter_key") or "",
                chapter_label=row.get("chapter_label") or "", position=row.get("position")))
    out: dict[str, list[Document]] = {c: [] for c in collections or ()}
    for doc in documents.values():
        # A NULL position sorts last and fails H3.
        doc.passages.sort(key=lambda p: (p.position is None, p.position or 0))
        out.setdefault(doc.collection, []).append(doc)
    return {c: sorted(docs, key=lambda d: d.id) for c, docs in sorted(out.items())}


def build(collections: list[str] | tuple[str, ...]) -> dict[str, list[Document]]:
    report.placeholder_credentials()
    return {c: report.SOURCE_ADAPTERS[c]() for c in collections}


# --------------------------------------------------------------------------- results

def collection_result(collection: str, documents: list[Document],
                      known: set[str]) -> dict:
    violations = health.check_documents(collection, documents)
    counts = Counter(v.rule for v in violations)
    return {
        "documents": len(documents),
        "passages": sum(len(d.passages) for d in documents),
        "counts": {rule: counts.get(rule, 0) for rule in health.RULES},
        "violations": [_violation_json(v, known) for v in violations],
    }


def _violation_json(v: health.Violation, known: set[str]) -> dict:
    row = {"rule": v.rule, "severity": v.severity, "document_id": v.document_id,
           "anchor": v.anchor, "detail": v.detail}
    if v.severity == "block":      # report rules are never known defects
        row["check_id"] = v.check_id
        row["known_defect"] = v.check_id in known
    return row


def merge(previous: dict, source: str, results: dict[str, dict], label: str) -> dict:
    """`previous` (an existing health.json) with `source`'s rows for the collections in
    `results` replaced; every other row is kept."""
    out = {s: dict(previous.get(s, {})) for s in SOURCES}
    measured = {s: dict(previous.get("measured_on", {}).get(s, {})) for s in SOURCES}
    for collection, result in results.items():
        out[source][collection] = result
        measured[source][collection] = label
    return {"measured_on": {s: dict(sorted(measured[s].items())) for s in SOURCES},
            **{s: dict(sorted(out[s].items())) for s in SOURCES}}


def unexpected_blocks(data: dict) -> list[dict]:
    """Build block violations not in known_defects.json: what the publish gate refuses."""
    return [v for c in data.get("build", {}).values() for v in c["violations"]
            if v["severity"] == "block" and not v.get("known_defect")]


# --------------------------------------------------------------------------- output

def health_md(data: dict) -> str:
    collections = sorted(set(data.get("build", {})) | set(data.get("snapshot", {})))
    have = [s for s in SOURCES if data.get(s)]
    heads = {"build": "Build", "snapshot": "Live snapshot"}
    lines = ["# Health summary (0.1b)", ""]
    for s in have:
        labels = sorted(set(data["measured_on"][s].values()))
        lines.append(f"{heads[s]}: {', '.join(labels)}.")
    blocked = unexpected_blocks(data)
    lines += ["", "Block rules refuse publication; report rules are counted only. A block "
              "violation listed in `checks/known_defects.json` is accepted until its fixing "
              "PR deletes the entry.", "",
              f"Build block violations not in known_defects.json: {len(blocked)}.", ""]
    for v in blocked[:20]:
        lines.append(f"- `{v['check_id']}`: {v['detail']}")
    if blocked:
        lines.append("")

    lines += ["## Counts", "", "| Collection | Rule | Severity | " +
              " | ".join(heads[s] for s in have) + " |",
              "|---|---|---|" + "---:|" * len(have)]
    for collection in collections:
        for rule in health.RULES:
            values = [data[s].get(collection, {}).get("counts", {}).get(rule) for s in have]
            if not any(values):
                continue
            severity = "block" if rule in health.BLOCK_RULES else "report"
            cells = " | ".join(
                "–" if v is None else f"{v:,}" + _known_note(data[s], collection, rule)
                for s, v in zip(have, values))
            lines.append(f"| {collection} | {rule} | {severity} | {cells} |")
    lines.append("")
    for s in have:
        totals = {c: (r["documents"], r["passages"]) for c, r in data[s].items()}
        counted = (f"{c} {p:,} in {d:,} document{'s' * (d != 1)}"
                   for c, (d, p) in sorted(totals.items()))
        lines.append(f"{heads[s]} passages: " + ", ".join(counted) + ".")
    lines.append("")

    lines += ["## First anchors", ""]
    for s in have:
        for collection, result in data[s].items():
            by_rule: dict[str, list[dict]] = {}
            for v in result["violations"]:
                by_rule.setdefault(v["rule"], []).append(v)
            for rule in health.RULES:
                found = by_rule.get(rule)
                if not found:
                    continue
                lines.append(f"{heads[s]}, {collection}, {rule} ({len(found):,}):")
                lines.append("")
                for v in found[:ANCHORS_LISTED]:
                    known = " (known defect)" if v.get("known_defect") else ""
                    lines.append(f"- `{v['anchor'] or v['document_id']}`: {v['detail']}{known}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _known_note(rows: dict, collection: str, rule: str) -> str:
    if rule not in health.BLOCK_RULES:
        return ""
    known = sum(1 for v in rows.get(collection, {}).get("violations", [])
                if v["rule"] == rule and v.get("known_defect"))
    return f" ({known} known)" if known else ""


def write_outputs(out_dir: str, data: dict) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "health.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(out_dir, "health.md"), "w", encoding="utf-8") as f:
        f.write(health_md(data))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--collection", default="all", choices=("all",) + report.COLLECTIONS)
    parser.add_argument("--out")
    parser.add_argument("--from-snapshot", metavar="PATH",
                        help=f"a 0.1c snapshot directory, or its {SNAPSHOT_FILE}")
    args = parser.parse_args(argv)

    collections = report.COLLECTIONS if args.collection == "all" else (args.collection,)
    if args.from_snapshot:
        source = "snapshot"
        documents = load_snapshot(args.from_snapshot, collections)
        label = os.path.abspath(args.from_snapshot)
    else:
        source = "build"
        documents = build(collections)
        label = report._git_head()
    label += f" at {datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}"

    known = health.known_block_defects()
    results = {c: collection_result(c, docs, known) for c, docs in documents.items()}
    out = args.out or os.path.join(DATAPIPELINE, "releases", "local",
                                   f"health-{datetime.now():%Y%m%d-%H%M%S}")
    previous = {}
    existing = os.path.join(out, "health.json")
    if os.path.exists(existing):
        with open(existing, encoding="utf-8") as f:
            previous = json.load(f)
    data = merge(previous, source, results, label)
    write_outputs(out, data)
    print(f"wrote {out}/health.md")
    blocked = unexpected_blocks({"build": {c: data["build"][c] for c in results}}) \
        if source == "build" else []
    for v in blocked[:health.REFUSAL_LISTED]:
        print(f"block: {v['check_id']}: {v['detail']}", file=sys.stderr)
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
