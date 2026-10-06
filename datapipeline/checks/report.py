"""Coverage and sequence report (0.1a).

    python3 -m checks.report --collection all|<name> [--baseline checks/baselines/<file>]
                             [--out <dir>] [--write-baseline [<file>]]

Builds documents through SOURCE_ADAPTERS, runs coverage, the sequence checks and the
sentinels, and writes <out>/coverage.json, <out>/sequence.json and <out>/summary.md.
--write-baseline also writes this run's numbers as the baseline (checks/baselines/
coverage.json unless a file is given), replacing only the collections this run measured;
a PR that changes any file's coverage commits it.
summary.md holds numbers and IDs only, so it can be pasted into a public PR; the
uncovered-sentence snippets stay in coverage.json, under the gitignored releases/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import health  # noqa: E402
from checks import sequence as seq  # noqa: E402
from checks.coverage import CoverageResult, coverage, documents_by_file  # noqa: E402
from checks.source_text import SOURCES, collection_files, editorial_divs, file_units  # noqa: E402
from model import Document  # noqa: E402
from publication import SOURCE_ADAPTERS  # noqa: E402

CHECKS_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_DEFECTS_PATH = os.path.join(CHECKS_DIR, "known_defects.json")
BASELINE_DIR = os.path.join(CHECKS_DIR, "baselines")
DEFAULT_BASELINE = os.path.join(BASELINE_DIR, "coverage.json")
# A file's coverage may fall this many percentage points below its baseline, or rise this
# many above it before the baseline must be rewritten.
COVERAGE_TOLERANCE = 0.5
# A file's measured body may differ this much (a fraction) from its baseline before the
# baseline must be rewritten: the source or the extractor changed.
BODY_TOLERANCE = 0.01
# Files below this coverage have a known_defects.json entry; at or above it the entry is
# reported "fixed, remove entry".
COVERAGE_ENTRY_BELOW = 95.0

# The collections the datapipeline builds, from its one adapter registry (which a test
# keeps equal to the API's VALID_COLLECTIONS), so a new collection is checked too.
COLLECTIONS = tuple(sorted(SOURCE_ADAPTERS))
SECTION_COLLECTIONS = ("apostolic-exhortations", "councils", "encyclicals", "papal-documents")
THML_COLLECTIONS = ("church-fathers", "medieval")
FAMILIES = ("bible_verses", "ccc_paragraphs", "canons", "summa_articles",
            "numbered_paragraphs", "thml_chapters")


# --------------------------------------------------------------------------- sentinels

@dataclass(frozen=True)
class Sentinel:
    """A minimum size for a unit the audits named, as a number."""
    name: str
    collection: str
    minimum: int
    description: str


SENTINELS = (
    Sentinel("nostra_aetate_4", "councils", 2000, "Nostra Aetate §4, characters"),
    Sentinel("dei_verbum_12", "councils", 1500, "Dei Verbum §12, characters"),
    Sentinel("gaudium_et_spes_total", "councils", 200_000, "Gaudium et Spes, characters"),
    Sentinel("trent_total", "councils", 500_000, "Council of Trent, characters"),
    Sentinel("vatican_i_total", "councils", 50_000, "First Vatican Council, characters"),
    Sentinel("daniel_13", "bible", 1, "Daniel 13, passages"),
    Sentinel("daniel_14", "bible", 1, "Daniel 14, passages"),
    Sentinel("summa_i_q71", "summa", 1, "Summa I q.71, passages"),
    Sentinel("summa_i_q72", "summa", 1, "Summa I q.72, passages"),
)


def _by_title(documents: list[Document], title: str) -> list[Document]:
    return [d for d in documents if d.title == title]


def _chars(documents: list[Document], section: str | None = None) -> int:
    return sum(len(p.content) for d in documents for p in d.passages
               if section is None or re.search(rf"§{section}\s*$", p.reference))


def sentinel_value(sentinel: Sentinel, documents: list[Document]) -> int:
    name = sentinel.name
    if name == "nostra_aetate_4":
        return _chars(_by_title(documents, "Nostra Aetate"), "4")
    if name == "dei_verbum_12":
        return _chars(_by_title(documents, "Dei Verbum"), "12")
    if name == "gaudium_et_spes_total":
        return _chars(_by_title(documents, "Gaudium et Spes"))
    if name == "trent_total":
        return _chars(_by_title(documents, "Council of Trent"))
    if name == "vatican_i_total":
        return _chars(_by_title(documents, "First Vatican Council"))
    if name in ("daniel_13", "daniel_14"):
        label = f"Daniel {name[-2:]}"
        return sum(1 for d in _by_title(documents, "Daniel") for p in d.passages
                   if p.chapter_label == label)
    if name in ("summa_i_q71", "summa_i_q72"):
        q = name[-2:]
        return sum(1 for d in documents for p in d.passages
                   if re.search(rf"First Part, Question {q}\b", p.reference))
    raise ValueError(name)


# --------------------------------------------------------------------------- run

@dataclass
class RunResult:
    collections: list[str]
    coverage: dict[str, CoverageResult] = field(default_factory=dict)
    # family → scope → SequenceResult. Scope is "<collection>/<file>" for per-file
    # families and the collection for the others.
    sequence: dict[str, dict[str, seq.SequenceResult]] = field(default_factory=dict)
    summa_articles: dict[str, tuple[int, int]] = field(default_factory=dict)
    sentinels: dict[str, int] = field(default_factory=dict)
    # collection → its 0.1b block-rule violations (the report rules are checks.health's).
    health: dict[str, list[health.Violation]] = field(default_factory=dict)
    seconds: float = 0.0


def placeholder_credentials() -> None:
    """config.settings requires store credentials at import, which the adapters do on
    their first call. The checks read local files only and never connect, so placeholders
    do. Variables already in the environment are kept; a placeholder does override a
    value that is only in datapipeline/.env."""
    for name, placeholder in (("DATABASE_URL", "postgresql://checks:checks@localhost/checks"),
                              ("OPENAI_API_KEY", "unused"), ("QDRANT_URL", "http://localhost"),
                              ("QDRANT_API_KEY", "unused"), ("ANTHROPIC_API_KEY", "unused")):
        os.environ.setdefault(name, placeholder)


def run(collections: list[str] | tuple[str, ...] = COLLECTIONS,
        sources: str = SOURCES,
        documents_by_collection: dict[str, list[Document]] | None = None) -> RunResult:
    """Coverage, sequence, sentinels and health block rules for `collections`, building
    each through SOURCE_ADAPTERS unless `documents_by_collection` already holds it (the
    release report builds once and passes its build in)."""
    placeholder_credentials()
    started = time.monotonic()
    result = RunResult(list(collections))
    for collection in collections:
        documents = (documents_by_collection or {}).get(collection)
        if documents is None:
            documents = SOURCE_ADAPTERS[collection]()
        files = collection_files(collection, sources)
        units_by_file = {f: file_units(collection, f, sources) for f in files}
        units = [u for f in files for u in units_by_file[f]]
        result.coverage[collection] = coverage(collection, documents, units, sources)

        if collection == "bible":
            result.sequence.setdefault("bible_verses", {})[collection] = \
                seq.bible_verses(documents, units)
        elif collection == "catechism":
            result.sequence.setdefault("ccc_paragraphs", {})[collection] = \
                seq.ccc_paragraphs(documents)
        elif collection == "canon-law":
            result.sequence.setdefault("canons", {})[collection] = seq.canons(documents)
        elif collection == "summa":
            articles = seq.summa_article_list(os.path.join(sources, "summa", "summa.xml"))
            result.sequence.setdefault("summa_articles", {})[collection] = \
                seq.summa_articles(documents, units, articles)
            result.summa_articles = seq.summa_article_coverage(
                documents, units, {a[0] for a in articles})
        if collection in SECTION_COLLECTIONS or collection in THML_COLLECTIONS:
            placed = documents_by_file(collection, documents, files, sources)
            for f in files:
                if collection in THML_COLLECTIONS:
                    result.sequence.setdefault("thml_chapters", {})[f"{collection}/{f}"] = \
                        seq.thml_chapters(placed[f], units_by_file[f], editorial_divs(f))
                elif collection != "councils" or f.startswith("vat2-"):
                    for doc in placed[f]:
                        result.sequence.setdefault("numbered_paragraphs", {})[
                            f"{collection}/{f}"] = seq.numbered_paragraphs(doc, units_by_file[f])
        for sentinel in SENTINELS:
            if sentinel.collection == collection:
                result.sentinels[sentinel.name] = sentinel_value(sentinel, documents)
        result.health[collection] = health.check_documents(collection, documents, report=False)
    result.seconds = round(time.monotonic() - started, 1)
    return result


# --------------------------------------------------------------------------- defects

def load_known(path: str = KNOWN_DEFECTS_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def failing_checks(result: RunResult) -> dict[str, list[str]]:
    """Every failing sequence, sentinel and health block-rule check id → the unit ids
    behind it."""
    out: dict[str, list[str]] = {}
    for family, scopes in result.sequence.items():
        for scope, res in scopes.items():
            out.update(seq.check_ids(family, scope, res))
    for sentinel in SENTINELS:
        value = result.sentinels.get(sentinel.name)
        if value is not None and value < sentinel.minimum:
            out[f"sentinel.{sentinel.name}"] = [str(value)]
    for violations in result.health.values():
        for v in violations:
            out[v.check_id] = [v.detail]
    return out


# Check-id prefixes this report computes. `release.` ids belong to the release report
# (0.1c), which judges them against a live snapshot.
REPORT_PREFIXES = ("coverage.", "sequence.", "sentinel.", "health.")


def check_scope(check_id: str) -> str | None:
    """The collection a check id belongs to, or None for an id this run cannot judge."""
    kind, _, rest = check_id.partition(".")
    # health.<rule>:<collection>/<document_id>[#<anchor>]; release.<check>:<collection>/<id>
    if kind in ("health", "release"):
        return rest.partition(":")[2].split("/", 1)[0] or None
    if kind == "coverage":
        return rest.split(".", 1)[0]
    if kind == "sentinel":
        return next((s.collection for s in SENTINELS if f"sentinel.{s.name}" == check_id), None)
    family, _, unit = rest.partition(":")
    family = family.split(".")[0]
    return {"bible_verses": "bible", "ccc_paragraphs": "catechism", "canons": "canon-law",
            "summa_articles": "summa"}.get(family) or unit.split("/", 1)[0]


def coverage_failing(result: RunResult) -> set[str]:
    """Coverage check ids of files under COVERAGE_ENTRY_BELOW."""
    return {f"coverage.{c}.{name}" for c, cov in result.coverage.items()
            for name, f in cov.files.items() if f.pct < COVERAGE_ENTRY_BELOW}


def known_defect_status(check_id: str, failing: set[str], known: dict[str, dict]) -> str:
    """How a check stands against known_defects.json. `failing` holds the failing
    sequence and sentinel ids and the coverage ids of files under the threshold."""
    if check_id in failing:
        if check_id in known:
            return f"known defect, fixed by {known[check_id]['fixed_by']}"
        return "unexpected failure"
    if check_id in known:
        return "fixed, remove entry"
    return "pass"


def coverage_regressions(result: RunResult, baseline: dict,
                         known: dict[str, dict]) -> list[str]:
    """Files whose coverage fell more than COVERAGE_TOLERANCE points below baseline,
    except those whose known-defect entry expects coverage to go down."""
    out = []
    for collection, cov in result.coverage.items():
        for name, f in cov.files.items():
            key = f"{collection}/{name}"
            base = baseline.get("files", {}).get(key)
            if base is None:
                continue
            entry = known.get(f"coverage.{collection}.{name}", {})
            if entry.get("expected_direction") == "down":
                continue
            if f.pct < base["pct"] - COVERAGE_TOLERANCE:
                out.append(f"{key}: {f.pct} < baseline {base['pct']}")
    return out


def stale_baseline(result: RunResult, baseline: dict) -> list[str]:
    """Files whose baseline no longer describes them: coverage risen more than
    COVERAGE_TOLERANCE points (a fix landed; the baseline must rise with it, or a later
    PR could lose the fix again), body characters changed by more than BODY_TOLERANCE
    (the source or the extractor changed), or a file the baseline does not hold. Each
    is cleared by rewriting the baseline with --write-baseline."""
    out = []
    files = baseline.get("files", {})
    for collection, cov in result.coverage.items():
        for name, f in cov.files.items():
            key = f"{collection}/{name}"
            base = files.get(key)
            if base is None:
                out.append(f"{key}: not in the baseline")
            elif f.pct > base["pct"] + COVERAGE_TOLERANCE:
                out.append(f"{key}: {f.pct} > baseline {base['pct']}")
            elif abs(f.body_chars - base["body_chars"]) > BODY_TOLERANCE * base["body_chars"]:
                out.append(f"{key}: body {f.body_chars:,} characters, baseline "
                           f"{base['body_chars']:,}")
    return out


def grown_defects(failing: dict[str, list[str]], known: dict[str, dict]) -> dict[str, list[str]]:
    """Known defects that fail on more units than their entry lists. A check id that
    groups units (a source file's § numbers, a Bible chapter's verses) lists them in
    "units", so a new gap in a file that already has one is not hidden by the entry."""
    out = {}
    for check_id, units in failing.items():
        listed = known.get(check_id, {}).get("units")
        if listed is not None:
            listed = set(listed)
            new = [u for u in units if u not in listed]
            if new:
                out[check_id] = new
    return out


# --------------------------------------------------------------------------- output

def baseline_json(result: RunResult, measured_on: str, previous: dict | None = None) -> dict:
    """Numbers and IDs only: safe in the public repo. The run's collections replace
    their own rows in `previous` (the baseline being rewritten); every other
    collection's rows are kept, so `--collection catechism --write-baseline` updates the
    Catechism without dropping the other nine. `measured_on` is per collection."""
    previous = previous or {}
    ran = set(result.coverage)
    old_measured = previous.get("measured_on") or {}
    if isinstance(old_measured, str):      # an older baseline: one label for all
        old_measured = {k.split("/", 1)[0]: old_measured for k in previous.get("files", {})}
    measured = {c: m for c, m in old_measured.items() if c not in ran}
    files = {k: v for k, v in previous.get("files", {}).items()
             if k.split("/", 1)[0] not in ran}
    documents = {k: v for k, v in previous.get("documents", {}).items()
                 if v.get("collection") not in ran}
    for collection, cov in sorted(result.coverage.items()):
        measured[collection] = measured_on
        for name, f in sorted(cov.files.items()):
            files[f"{collection}/{name}"] = {"body_chars": f.body_chars,
                                             "covered_chars": f.covered_chars, "pct": f.pct}
        for doc_id, d in sorted(cov.documents.items()):
            documents[doc_id] = {"collection": collection, "source_file": d.source_file,
                                 "body_chars": d.body_chars, "covered_chars": d.covered_chars,
                                 "pct": d.pct}
    return {"measured_on": dict(sorted(measured.items())), "files": dict(sorted(files.items())),
            "documents": dict(sorted(documents.items()))}


def sequence_json(result: RunResult) -> dict:
    return {family: {scope: r.to_json() for scope, r in sorted(scopes.items())}
            for family, scopes in sorted(result.sequence.items())}


def _delta(pct: float, base: float | None) -> str:
    if base is None:
        return "new"
    d = round(pct - base, 2)
    return f"{d:+.2f}" if d else "0.00"


def summary_md(result: RunResult, baseline: dict, known: dict[str, dict],
               baseline_name: str) -> str:
    failing = failing_checks(result)
    failing_ids = set(failing) | coverage_failing(result)
    lines = [f"# Coverage and sequence summary (0.1a)", "",
             f"Collections: {', '.join(result.collections)}. Runtime {result.seconds} s. "
             f"Baseline: `{baseline_name}`.", "",
             "Coverage is covered characters over the characters of body sentences of 30 "
             "characters or more. \"With notes\" divides by body plus note characters. "
             "Note leakage counts note sentences found in passages.", ""]
    base_files = baseline.get("files", {})

    for collection in result.collections:
        cov = result.coverage[collection]
        lines += [f"## {collection}", "",
                  f"Body {cov.body_chars:,} characters, covered {cov.covered_chars:,} "
                  f"({cov.pct}%), notes {cov.note_chars:,}.", "",
                  "| Source file | Body | Covered | % | With notes | Δ baseline | "
                  "Note leakage | Status |",
                  "|---|---:|---:|---:|---:|---:|---:|---|"]
        rows = sorted(cov.files.values(), key=lambda f: (f.pct, f.source_file))
        hidden = 0
        for f in rows:
            key = f"{collection}/{f.source_file}"
            status = known_defect_status(f"coverage.{collection}.{f.source_file}",
                                         failing_ids, known)
            base = base_files.get(key, {}).get("pct")
            if base is not None and f.pct < base - COVERAGE_TOLERANCE:
                status = f"regression ({status})"
            elif base is not None and f.pct > base + COVERAGE_TOLERANCE:
                status = f"improved, rewrite baseline ({status})"
            if f.pct >= 99.5 and status == "pass" and _delta(f.pct, base) in ("0.00", "new"):
                hidden += 1   # complete and unchanged: counted below, not listed
                continue
            lines.append(f"| {f.source_file} | {f.body_chars:,} | {f.covered_chars:,} | "
                         f"{f.pct} | {f.pct_with_notes} | {_delta(f.pct, base)} | "
                         f"{f.note_leakage} | {status} |")
        lines += ["", f"Files at 99.5% or more and unchanged, not listed: "
                      f"{hidden} of {len(rows)}.", ""]

        for family, scopes in sorted(result.sequence.items()):
            mine = {s: r for s, r in scopes.items()
                    if s == collection or s.startswith(f"{collection}/")}
            if not mine:
                continue
            gaps = sum(len(r.missing) for r in mine.values())
            dups = sum(len(r.duplicated) for r in mine.values())
            over = sum(len(r.out_of_range) for r in mine.values())
            lines.append(f"Sequence `{family}`: {gaps} missing, {dups} duplicated, "
                         f"{over} out of range, in {sum(1 for r in mine.values() if not r.ok)} "
                         f"of {len(mine)} scopes.")
        lines.append("")

    if result.summa_articles:
        partial = sorted(((cov / body, art, body) for art, (body, cov)
                          in result.summa_articles.items() if body), key=lambda t: t[0])
        lines += ["## Summa articles by characters kept", "",
                  "Articles range from a few hundred to many thousand characters, so this "
                  "lists the articles with the lowest share of their characters reaching a "
                  "passage.", "", "| Article | Body | Kept % |", "|---|---:|---:|"]
        for share, art, body in partial[:15]:
            lines.append(f"| {art} | {body:,} | {round(100 * share, 1)} |")
        lines.append("")

    lines += ["## Sentinels", "", "| Sentinel | Value | Minimum | Status |",
              "|---|---:|---:|---|"]
    for s in SENTINELS:
        if s.name in result.sentinels:
            status = known_defect_status(f"sentinel.{s.name}", failing_ids, known)
            lines.append(f"| {s.description} | {result.sentinels[s.name]:,} | "
                         f"{s.minimum:,} | {status} |")
    lines.append("")

    judged = {k for k in known if check_scope(k) in result.collections
              and k.startswith(REPORT_PREFIXES)}
    unexpected = sorted(i for i in failing_ids if i not in known)
    fixed = sorted(k for k in judged if k not in failing_ids)
    regressions = coverage_regressions(result, baseline, known)
    grown = grown_defects(failing, known)
    stale = stale_baseline(result, baseline)
    by_owner: dict[str, int] = {}
    for k in judged:
        by_owner[known[k]["fixed_by"]] = by_owner.get(known[k]["fixed_by"], 0) + 1
    lines += ["## Known defects", "",
              f"{len(judged)} entries judged by this run, by item: " +
              ", ".join(f"{o} {n}" for o, n in sorted(by_owner.items())) + ".",
              f"Unexpected failures: {len(unexpected)}. Fixed, remove entry: {len(fixed)}. "
              f"Grown: {len(grown)}. Coverage regressions: {len(regressions)}. "
              f"Baseline out of date: {len(stale)}.", ""]
    grown_lines = [f"{k}: {', '.join(v)}" for k, v in sorted(grown.items())]
    for label, ids in (("Unexpected failures", unexpected), ("Fixed, remove entry", fixed),
                       ("Grown (new units in a known defect)", grown_lines),
                       ("Coverage regressions", regressions),
                       ("Baseline out of date (rerun with --write-baseline)", stale)):
        if ids:
            lines += [f"{label}:", ""] + [f"- `{i}`" for i in ids] + [""]
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(result: RunResult, out_dir: str, baseline: dict, baseline_name: str,
                  known: dict[str, dict]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    coverage_out = {c: r.to_json(with_text=True) for c, r in result.coverage.items()}
    with open(os.path.join(out_dir, "coverage.json"), "w", encoding="utf-8") as f:
        json.dump(coverage_out, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "sequence.json"), "w", encoding="utf-8") as f:
        json.dump({"sequence": sequence_json(result), "sentinels": result.sentinels,
                   "summa_articles": result.summa_articles,
                   "failing": failing_checks(result)}, f, indent=1)
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(summary_md(result, baseline, known, baseline_name))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--collection", default="all",
                        choices=("all",) + COLLECTIONS)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--out")
    parser.add_argument("--write-baseline", metavar="FILE", nargs="?", const=DEFAULT_BASELINE,
                        help="also write this run's numbers as a baseline file "
                             "(default checks/baselines/coverage.json)")
    args = parser.parse_args(argv)

    collections = COLLECTIONS if args.collection == "all" else (args.collection,)
    result = run(collections)
    baseline = {}
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, encoding="utf-8") as f:
            baseline = json.load(f)
    known = load_known()
    out = args.out or os.path.join(DATAPIPELINE, "releases", "local",
                                   f"checks-{datetime.now():%Y%m%d-%H%M%S}")
    write_outputs(result, out, baseline, os.path.relpath(args.baseline, DATAPIPELINE)
                  if args.baseline else "none", known)
    if args.write_baseline:
        previous = {}
        if os.path.exists(args.write_baseline):
            with open(args.write_baseline, encoding="utf-8") as f:
                previous = json.load(f)
        with open(args.write_baseline, "w", encoding="utf-8") as f:
            json.dump(baseline_json(result, _git_head(), previous), f, indent=1)
            f.write("\n")
    print(f"wrote {out}/summary.md ({result.seconds} s)")
    return 0


def _git_head() -> str:
    import subprocess

    try:
        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=DATAPIPELINE, capture_output=True,
                                  text=True, check=True).stdout.strip()
        return f"{git('rev-parse', '--abbrev-ref', 'HEAD')} {git('rev-parse', '--short', 'HEAD')}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
