"""Release report (corpus-cleanup item 0.1c).

    cd datapipeline
    python3 -m release.report --snapshot releases/snapshots/<date> --collection all|<name>
                              [--out <dir>] [--public | --no-public]

Tells a reviewer what a build would change against what users see today. Builds the
collections through SOURCE_ADAPTERS, maps every live passage in the snapshot to one remap
outcome (release/remap.py), checks D1, counts the saved user rows each outcome touches,
and runs 0.1b's health rules on the build and on the snapshot and, when the vendored
sources are present, 0.1a's coverage and sequence checks. Writes to <out> (default
releases/local/report-<collection>-<timestamp>/, gitignored):

- remap.jsonl: one row per live passage (release.remap.RemapRow).
- chapter_remap.jsonl: one row per live (document_id, chapter_key).
- report.json and report.md: the summary. With --public (the default) report.md holds no
  passage text, so it can be pasted into a public PR; --no-public adds excerpts to its
  samples, for local reading only.
- health.json and health.md (checks.health), with a build and a live column.

A run replaces only the rows of the collections it covered in files already in <out>.

Exits 1 when a release check fails that checks/known_defects.json does not list, when a
listed release check now passes (delete the entry), or when the snapshot's files do not
match their recorded hashes; nothing is written in that last case.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import health  # noqa: E402
from checks import health as health_cli  # noqa: E402
from checks import report as checks_report  # noqa: E402
from model import Document  # noqa: E402
from release import remap as R  # noqa: E402

REGISTRY_DIR = os.path.join(DATAPIPELINE, "registry")
SNAPSHOT_INDEX = os.path.join(DATAPIPELINE, "releases", "snapshots.json")
SAMPLES = 30
EXCERPT_CHARS = 160
SAMPLED = ("moved", "split", "merged", "renumbered", "removed", R.NEW)


# --------------------------------------------------------------------------- inputs

def verify_snapshot(directory: str, index_path: str = SNAPSHOT_INDEX) -> tuple[dict, list[str]]:
    """snapshot.json and the problems found: a file whose sha256 differs from snapshot.json,
    or a snapshot.json that differs from the tracked index's entry for its date."""
    with open(os.path.join(directory, "snapshot.json"), encoding="utf-8") as f:
        meta = json.load(f)
    problems = []
    for name, digest in meta.get("files", {}).items():
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            problems.append(f"{name} is missing")
            continue
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() != digest:
            problems.append(f"{name} sha256 {h.hexdigest()[:12]}… differs from snapshot.json")
    meta["indexed"] = False
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            entries = [e for e in json.load(f).get("snapshots", [])
                       if e.get("date") == meta.get("date")]
        if entries:
            meta["indexed"] = True
            if entries[0].get("files") != meta.get("files"):
                problems.append(f"snapshot.json differs from the {os.path.basename(index_path)} "
                                f"entry for {meta.get('date')}")
    return meta, problems


def old_passages(snapshot: dict[str, list[Document]]) -> list[R.OldPassage]:
    """The snapshot's passages, read with checks.health's snapshot reader."""
    out = []
    for documents in snapshot.values():
        for d in documents:
            for p in d.passages:
                out.append(R.OldPassage(
                    id=p.metadata["passage_id"], document_id=d.id, collection=d.collection,
                    anchor=p.anchor, chapter_key=p.chapter_key, reference=p.reference,
                    position=p.position, content=p.content, unit_label=p.unit_label,
                    chapter_label=p.chapter_label))
    return out


def load_registry(directory: str = REGISTRY_DIR) -> R.Registry:
    """2.1's redirects.json, removals.json and works.json. A missing file counts as empty;
    once redirects.json exists (2.1 has landed), outcomes other than `same` must be
    declared."""
    def read(name: str, default):
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    supersedes = {}
    for work in read("works.json", []):
        for old in work.get("supersedes") or []:
            supersedes[old] = work["document_id"]
    return R.Registry(redirects=read("redirects.json", []), removals=read("removals.json", []),
                      supersedes=supersedes,
                      enforce_redirects=os.path.exists(os.path.join(directory, "redirects.json")))


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --------------------------------------------------------------------------- summary

def _totals(documents: list[Document]) -> dict:
    return {"documents": len(documents),
            "passages": sum(len(d.passages) for d in documents),
            "characters": sum(len(p.content) for d in documents for p in d.passages)}


def _spread(items: list, n: int = SAMPLES) -> list:
    """Up to n items spread evenly over the list, so samples are not all from one document."""
    if len(items) <= n:
        return list(items)
    return [items[(i * len(items)) // n] for i in range(n)]


def samples(result: R.RemapResult, old: dict[str, R.OldPassage],
            new: dict[str, R.NewPassage], collection: str, excerpts: bool) -> dict:
    out: dict[str, list[dict]] = {}
    for outcome in SAMPLED:
        if outcome == R.NEW:
            chosen = [p for p in result.new if p.collection == collection]
        else:
            chosen = [r for r in result.rows if r.collection == collection
                      and r.outcome == outcome]
        rows = []
        for item in _spread(chosen):
            if outcome == R.NEW:
                row = {"new_id": item.id, "document_id": item.document_id,
                       "new_anchor": item.anchor, "new_reference": item.reference}
                if excerpts:
                    row["new_excerpt"] = item.content[:EXCERPT_CHARS]
            else:
                o = old[item.old_id]
                primary = new.get(item.new_ids[0]) if item.new_ids else None
                row = {"old_id": item.old_id, "document_id": item.old_document_id,
                       "method": item.method,
                       "score": None if item.score is None else round(item.score, 3),
                       "old_anchor": item.old_anchor, "old_reference": o.reference,
                       "new_ids": list(item.new_ids), "new_anchor": item.new_anchor,
                       "new_reference": primary.reference if primary else None}
                if excerpts:
                    row["old_excerpt"] = o.content[:EXCERPT_CHARS]
                    if primary:
                        row["new_excerpt"] = primary.content[:EXCERPT_CHARS]
            rows.append(row)
        if rows:
            out[outcome] = rows
    return out


def checks_summary(run: checks_report.RunResult, known: dict[str, dict]) -> dict:
    """0.1a numbers per collection: coverage, sequence gaps and known-defect bookkeeping."""
    failing = checks_report.failing_checks(run)
    failing_ids = set(failing) | checks_report.coverage_failing(run)
    out = {}
    for collection in run.collections:
        cov = run.coverage[collection]
        mine = [k for k in failing_ids if checks_report.check_scope(k) == collection]
        judged = [k for k in known if checks_report.check_scope(k) == collection
                  and k.startswith(checks_report.REPORT_PREFIXES)]
        gaps = Counter()
        for family, scopes in run.sequence.items():
            for scope, res in scopes.items():
                if scope == collection or scope.startswith(f"{collection}/"):
                    gaps["missing"] += len(res.missing)
                    gaps["duplicated"] += len(res.duplicated)
                    gaps["out_of_range"] += len(res.out_of_range)
        out[collection] = {
            "coverage_pct": cov.pct, "body_chars": cov.body_chars,
            "covered_chars": cov.covered_chars,
            "sequence": {k: gaps.get(k, 0) for k in ("missing", "duplicated", "out_of_range")},
            "failing_checks": len(mine),
            "known_defects": len(judged),
            "unexpected": sorted(k for k in mine if k not in known),
            "fixed_remove_entry": sorted(k for k in judged if k not in failing_ids),
        }
    return out


def known_release_status(failures: list[R.Failure], collections: list[str],
                         known: dict[str, dict]) -> dict:
    failing = {f.check_id for f in failures}
    judged = {k for k in known if k.startswith("release.")
              and checks_report.check_scope(k) in collections}
    return {"unexpected": sorted(failing - set(known)),
            "fixed_remove_entry": sorted(judged - failing),
            "known": len(judged & failing)}


def collection_section(collection: str, result: R.RemapResult, live: list[Document],
                       build: list[Document], old: dict[str, R.OldPassage],
                       new: dict[str, R.NewPassage], impact: dict, known: dict[str, dict],
                       excerpts: bool) -> dict:
    rows = [r for r in result.rows if r.collection == collection]
    methods: dict[str, Counter] = {}
    for r in rows:
        methods.setdefault(r.outcome, Counter())[r.method or "none"] += 1
    failures = [f for f in result.failures if f.collection == collection]
    return {
        "live": _totals(live), "build": _totals(build),
        "outcomes": {o: sum(1 for r in rows if r.outcome == o) for o in R.OUTCOMES},
        "new": sum(1 for p in result.new if p.collection == collection),
        "methods": {o: dict(sorted(c.items())) for o, c in sorted(methods.items())},
        "failures": [{"check_id": f.check_id, "check": f.check, "document_id": f.document_id,
                      "passage_id": f.passage_id, "anchor": f.anchor,
                      "score": None if f.score is None else round(f.score, 4),
                      "detail": f.detail, "known_defect": f.check_id in known}
                     for f in failures],
        "replacements": [r for r in result.replacements if r["collection"] == collection],
        "user_impact": impact.get(collection, {}),
        "samples": samples(result, old, new, collection, excerpts),
    }


# --------------------------------------------------------------------------- markdown

def _n(v) -> str:
    return "–" if v is None else f"{v:,}"


def report_md(data: dict, public: bool) -> str:
    collections = sorted(data["collections"])
    snap = data["snapshot"]
    lines = ["# Release report (0.1c)", "",
             f"Snapshot `{snap['date']}` exported {snap['exported_at']}"
             f"{', in the tracked index' if snap.get('indexed') else ', NOT in the tracked index'}"
             f"; hashes {'verified' if not snap.get('problems') else 'MISMATCH'}.",
             f"Build: {data['build']}. Anchor stability threshold "
             f"{data['threshold']} (`ANCHOR_STABILITY_THRESHOLD`).",
             f"Redirect rows required for outcomes other than `same`: "
             f"{'yes' if data.get('enforce_redirects') else 'no (2.1 not merged)'}.", ""]

    lines += ["## Totals, live against build", "",
              "| Collection | Live documents | Build documents | Live passages | "
              "Build passages | Live characters | Build characters |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    total = Counter()
    for c in collections:
        live, build = data["collections"][c]["live"], data["collections"][c]["build"]
        lines.append(f"| {c} | {_n(live['documents'])} | {_n(build['documents'])} | "
                     f"{_n(live['passages'])} | {_n(build['passages'])} | "
                     f"{_n(live['characters'])} | {_n(build['characters'])} |")
        for k in ("documents", "passages", "characters"):
            total[f"live_{k}"] += live[k]
            total[f"build_{k}"] += build[k]
    if len(collections) > 1:
        lines.append(f"| **Total** | {_n(total['live_documents'])} | {_n(total['build_documents'])} "
                     f"| {_n(total['live_passages'])} | {_n(total['build_passages'])} | "
                     f"{_n(total['live_characters'])} | {_n(total['build_characters'])} |")
    lines.append("")

    lines += ["## Outcomes", "",
              "Each live passage takes one outcome; `new` counts build passages that are no "
              "live passage's successor.", "",
              "| Collection | " + " | ".join(f"`{o}`" for o in R.OUTCOMES) + " | `new` |",
              "|---|" + "---:|" * (len(R.OUTCOMES) + 1)]
    sums = Counter()
    for c in collections:
        sec = data["collections"][c]
        lines.append(f"| {c} | " + " | ".join(_n(sec["outcomes"][o]) for o in R.OUTCOMES)
                     + f" | {_n(sec['new'])} |")
        sums.update(sec["outcomes"])
        sums["new"] += sec["new"]
    if len(collections) > 1:
        lines.append("| **Total** | " + " | ".join(_n(sums[o]) for o in R.OUTCOMES)
                     + f" | {_n(sums['new'])} |")
    lines += ["", "Matching method per outcome:", ""]
    for c in collections:
        parts = [f"{o} ({', '.join(f'{m} {n:,}' for m, n in ms.items())})"
                 for o, ms in data["collections"][c]["methods"].items()]
        lines.append(f"- {c}: " + "; ".join(parts))
    lines.append("")

    failures = [f for c in collections for f in data["collections"][c]["failures"]]
    status = data["known_defects"]
    by_check = Counter(f["check"] for f in failures)
    lines += ["## Checks that fail the report", "",
              f"{len(failures):,} failing: " +
              (", ".join(f"{k} {v:,}" for k, v in sorted(by_check.items())) or "none") +
              f". Listed in `checks/known_defects.json`: {status['known']:,}. "
              f"Unexpected: {len(status['unexpected']):,}. "
              f"Known defects that now pass (remove the entry): "
              f"{len(status['fixed_remove_entry']):,}.", ""]
    for label, ids in (("Unexpected", status["unexpected"]),
                       ("Fixed, remove entry", status["fixed_remove_entry"])):
        if ids:
            lines += [f"{label}:", ""] + [f"- `{i}`" for i in ids[:50]]
            if len(ids) > 50:
                lines.append(f"- and {len(ids) - 50:,} more (report.json)")
            lines.append("")
    if failures:
        lines += ["| Check | Collection | Document | Passage ID | Anchor | Score | Known |",
                  "|---|---|---|---|---|---:|---|"]
        for c in collections:
            for f in data["collections"][c]["failures"]:
                score = "" if f["score"] is None else f"{f['score']:.2f}"
                lines.append(f"| {f['check']} | {c} | `{f['document_id']}` | "
                             f"`{f['passage_id']}` | `{f['anchor']}` | {score} | "
                             f"{'yes' if f['known_defect'] else '**no**'} |")
        lines.append("")

    replacements = [r for c in collections for r in data["collections"][c]["replacements"]]
    lines += ["## Declared text replacements", ""]
    if replacements:
        lines += ["| Collection | Anchor | Reason | Score |", "|---|---|---|---:|"]
        for r in replacements:
            lines.append(f"| {r['collection']} | `{r['anchor']}` | {r['reason']} | "
                         f"{'' if r['score'] is None else r['score']} |")
    else:
        lines.append("None.")
    lines.append("")

    tables = R.USER_TABLES + ("reading_progress",)
    lines += ["## User impact", "",
              "Saved rows pointing at live passages that are `removed` or whose primary "
              "successor has a different ID, and reading_progress rows whose anchor or "
              "chapter changes (`chapter` counts rows with no anchor whose chapter moves). "
              f"`{R.BELOW_THRESHOLD}` counts rows on passages that keep their ID but would "
              "show different text.", "",
              "| Collection | Outcome | Passages | " + " | ".join(tables) + " |",
              "|---|---|---:|" + "---:|" * len(tables)]
    grand = Counter()
    for c in collections:
        for outcome, counts in data["collections"][c]["user_impact"].items():
            lines.append(f"| {c} | {outcome} | {_n(counts['passages'])} | "
                         + " | ".join(_n(counts[t]) for t in tables) + " |")
            grand.update(counts)
    lines.append("| **Total** | | " + _n(grand["passages"]) + " | "
                 + " | ".join(_n(grand[t]) for t in tables) + " |")
    lines.append("")

    lines += ["## Samples", "",
              f"Up to {SAMPLES} per outcome and collection, spread over the list. IDs, anchors "
              "and references only" + ("." if public else "; excerpts are local only, never "
                                       "paste them into a public PR."), ""]
    for c in collections:
        for outcome, rows in data["collections"][c]["samples"].items():
            lines += [f"<details><summary>{c}, {outcome} ({len(rows)})</summary>", ""]
            for row in rows:
                if outcome == R.NEW:
                    lines.append(f"- `{row['new_id']}` `{row['new_anchor']}` "
                                 f"({row['new_reference']})")
                else:
                    score = "" if row["score"] is None else f" {row['score']}"
                    lines.append(f"- `{row['old_id']}` `{row['old_anchor']}` "
                                 f"({row['old_reference']}) → "
                                 + (", ".join(f"`{i}`" for i in row["new_ids"]) or "nothing")
                                 + (f" `{row['new_anchor']}` ({row['new_reference']})"
                                    if row["new_anchor"] else "")
                                 + f" [{row['method'] or 'none'}{score}]")
                if not public:
                    for key in ("old_excerpt", "new_excerpt"):
                        if row.get(key):
                            lines.append(f"  - {key.split('_')[0]}: {row[key]!r}")
            lines += ["", "</details>", ""]

    lines += ["## Health (0.1b)", "",
              "Block-rule counts, live against build; the full table, with report rules, is "
              "health.md in this directory.", "",
              "| Collection | " + " | ".join(f"{r} live / build" for r in health.BLOCK_RULES)
              + " |", "|---|" + "---:|" * len(health.BLOCK_RULES)]
    for c in collections:
        h = data["collections"][c].get("health", {})
        lines.append(f"| {c} | " + " | ".join(
            f"{_n(h.get('live', {}).get(r))} / {_n(h.get('build', {}).get(r))}"
            for r in health.BLOCK_RULES) + " |")
    lines.append("")

    lines += ["## Coverage and sequence (0.1a)", ""]
    checks = {c: data["collections"][c].get("checks") for c in collections}
    if not any(checks.values()):
        lines.append("Not run: the vendored sources are not present.")
    else:
        lines += ["| Collection | Coverage % | Missing | Duplicated | Out of range | "
                  "Failing checks | Unexpected | Fixed, remove entry |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for c, s in checks.items():
            if s:
                lines.append(f"| {c} | {s['coverage_pct']} | {_n(s['sequence']['missing'])} | "
                             f"{_n(s['sequence']['duplicated'])} | "
                             f"{_n(s['sequence']['out_of_range'])} | {_n(s['failing_checks'])} | "
                             f"{_n(len(s['unexpected']))} | {_n(len(s['fixed_remove_entry']))} |")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- run

def run(snapshot_dir: str, collections: tuple[str, ...], out: str, public: bool = True,
        registry: R.Registry | None = None, build: dict[str, list[Document]] | None = None,
        run_checks: bool | None = None, index_path: str = SNAPSHOT_INDEX) -> int:
    meta, problems = verify_snapshot(snapshot_dir, index_path)
    if problems:
        for p in problems:
            print(f"snapshot: {p}", file=sys.stderr)
        print("REFUSING: the snapshot does not match its recorded hashes; nothing written",
              file=sys.stderr)
        return 1

    live = health_cli.load_snapshot(snapshot_dir, collections)
    old = old_passages(live)
    if build is None:
        checks_report.placeholder_credentials()
        build = {c: checks_report.SOURCE_ADAPTERS[c]() for c in collections}
    registry = registry if registry is not None else load_registry()
    built = [d for c in collections for d in build[c]]
    result = R.remap(old, built, registry)
    references = {}
    references_path = os.path.join(snapshot_dir, "references.json")
    if os.path.exists(references_path):
        with open(references_path, encoding="utf-8") as f:
            references = json.load(f)
    chapters = R.chapter_remap(old, result.rows, references)
    impact = R.user_impact(result.rows, chapters, references)

    known = checks_report.load_known()
    old_by_id = {o.id: o for o in old}
    new_by_id = {p.id: p for p in R.new_passages(built)}
    sections = {c: collection_section(c, result, live.get(c, []), build[c], old_by_id,
                                      new_by_id, impact, known, not public)
                for c in collections}

    # 0.1b health, build and live, into health.json beside the report.
    previous_health = {}
    health_path = os.path.join(out, "health.json")
    if os.path.exists(health_path):
        with open(health_path, encoding="utf-8") as f:
            previous_health = json.load(f)
    block_known = health.known_block_defects()
    stamp = f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}"
    health_data = health_cli.merge(
        previous_health, "build",
        {c: health_cli.collection_result(c, build[c], block_known) for c in collections},
        f"{checks_report._git_head()} at {stamp}")
    health_data = health_cli.merge(
        health_data, "snapshot",
        {c: health_cli.collection_result(c, live.get(c, []), block_known) for c in collections},
        f"{os.path.abspath(snapshot_dir)} at {stamp}")
    for c in collections:
        sections[c]["health"] = {
            "build": {r: health_data["build"][c]["counts"][r] for r in health.BLOCK_RULES},
            "live": {r: health_data["snapshot"][c]["counts"][r] for r in health.BLOCK_RULES}}

    # 0.1a coverage and sequence, when the sources are there.
    if run_checks is None:
        from checks.source_text import SOURCES
        run_checks = all(os.path.isdir(os.path.join(SOURCES, c)) for c in collections)
    if run_checks:
        summary = checks_summary(checks_report.run(collections, documents_by_collection=build),
                                 known)
        for c in collections:
            sections[c]["checks"] = summary[c]

    # Merge with an earlier report in <out>: this run's collections replace their rows.
    previous = {}
    report_path = os.path.join(out, "report.json")
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as f:
            previous = json.load(f)
    merged = dict(previous.get("collections", {}))
    merged.update(sections)
    all_failures = [R.Failure(**{k: f[k] for k in ("check", "document_id", "passage_id",
                                                 "anchor", "score", "detail")},
                              collection=c)
                    for c, sec in merged.items() for f in sec["failures"]]
    data = {
        "snapshot": {"path": os.path.abspath(snapshot_dir), "date": meta.get("date"),
                     "exported_at": meta.get("exported_at"), "indexed": meta["indexed"],
                     "problems": problems, "tables": meta.get("tables")},
        "build": checks_report._git_head(),
        "threshold": R.ANCHOR_STABILITY_THRESHOLD,
        "enforce_redirects": registry.enforce_redirects,
        "known_defects": known_release_status(all_failures, sorted(merged), known),
        "collections": dict(sorted(merged.items())),
    }

    os.makedirs(out, exist_ok=True)
    _write_jsonl(os.path.join(out, "remap.jsonl"), [r.to_json() for r in result.rows],
                 collections)
    _write_jsonl(os.path.join(out, "chapter_remap.jsonl"), chapters, collections)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md(data, public))
    health_cli.write_outputs(out, health_data)

    status = known_release_status(result.failures, list(collections), known)
    print(f"wrote {out}/report.md: " + ", ".join(
        f"{o} {n:,}" for o, n in result.outcome_counts().items()) +
        f", new {len(result.new):,}; {len(result.failures):,} failing checks, "
        f"{len(status['unexpected']):,} unexpected, "
        f"{len(status['fixed_remove_entry']):,} known defects now pass")
    for i in status["unexpected"][:20]:
        print(f"unexpected: {i}", file=sys.stderr)
    for i in status["fixed_remove_entry"][:20]:
        print(f"fixed, remove entry: {i}", file=sys.stderr)
    return 1 if status["unexpected"] or status["fixed_remove_entry"] else 0


def _write_jsonl(path: str, rows: list[dict], collections: tuple[str, ...]) -> None:
    """Write `rows`, keeping rows of other collections already in the file."""
    kept = [r for r in read_jsonl(path) if r.get("collection") not in collections]
    with open(path, "w", encoding="utf-8") as f:
        for row in kept + rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", required=True,
                        help="a snapshot directory written by scripts/export_live_snapshot.py")
    parser.add_argument("--collection", default="all",
                        choices=("all",) + checks_report.COLLECTIONS)
    parser.add_argument("--out")
    parser.add_argument("--public", action=argparse.BooleanOptionalAction, default=True,
                        help="keep passage text out of report.md (default); --no-public "
                             "adds excerpts for local reading")
    args = parser.parse_args(argv)
    collections = checks_report.COLLECTIONS if args.collection == "all" else (args.collection,)
    out = args.out or os.path.join(DATAPIPELINE, "releases", "local",
                                   f"report-{args.collection}-{datetime.now():%Y%m%d-%H%M%S}")
    return run(args.snapshot, collections, out, args.public)


if __name__ == "__main__":
    raise SystemExit(main())
