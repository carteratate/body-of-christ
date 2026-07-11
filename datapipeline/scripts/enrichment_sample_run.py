"""Human-readable test-run harness for the 3-pass enrichment redesign.

Takes a small, explicit list of chunks (via --chunks-csv, columns:
collection,anchor) and runs the full Pass 1 (generation) -> Pass 2
(classification) -> Pass 3 (annotation assembly) flow against each one in
isolated --sample mode: EnrichDeps(cache=None, backup=None,
annotation_writer=None) and enrich_one(..., sample=True), the same isolated
code path used by `pipeline.py --sample` and `scripts/sample_search.py` — zero
writes to cache.db, Supabase, or the enrichments/ backup.

Writes a human-readable review file with, per chunk: reference, content,
facets (question + all Pass 2 labels: grounding, kind, kind_secondary,
evidence), and the assembled Pass 3 annotation — followed by a per-collection
summary table (facet count, grounding distribution, kind distribution,
secondary-kind count, validation warnings/failures).

Costs pennies to run (three short Anthropic calls per chunk), but does NOT
run against anything until you supply real chunk IDs via --chunks-csv — there
is no bundled default chunk list.

    cd datapipeline && python3 scripts/enrichment_sample_run.py \\
        --chunks-csv chunks.csv

chunks.csv format (header optional, exactly two columns):
    collection,anchor
    bible,genesis/3/1
    catechism,ccc/2/1/1/1
    ...
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


class WarningCollector(logging.Handler):
    """Captures stages.enrich's per-chunk annotation validation warnings without
    changing enrich.py's public API — cleared between chunks so counts can be
    attributed to the chunk (and its collection) currently being processed."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def read_chunk_list(path: str) -> list[tuple[str, str]]:
    """Reads (collection, anchor) pairs from a CSV. A literal header row of
    exactly `collection,anchor` (case-insensitive) is skipped if present."""
    rows: list[tuple[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.reader(f)):
            if not row or not row[0].strip():
                continue
            if len(row) < 2:
                raise ValueError(f"{path}: row {i + 1} needs 2 columns (collection,anchor): {row!r}")
            if i == 0 and row[0].strip().lower() == "collection" and row[1].strip().lower() == "anchor":
                continue
            rows.append((row[0].strip(), row[1].strip()))
    return rows


def group_by_collection(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for collection, anchor in rows:
        grouped[collection].append(anchor)
    return dict(grouped)


def format_facet(index: int, facet) -> str:
    kind = f"{facet.kind}/{facet.kind_secondary}" if facet.kind_secondary else facet.kind
    return (
        f"  [{index}] {kind} | {facet.grounding}\n"
        f"      TEXT:     {facet.text}\n"
        f"      QUESTION: {facet.question}\n"
        f"      EVIDENCE: {facet.evidence}"
    )


def format_chunk_report(collection: str, anchor: str, passage, *,
                        merged=None, error: str | None = None,
                        warnings: list[str] | None = None) -> str:
    lines = [
        "=" * 78,
        f"{collection} :: {anchor}" + (f"  (ref: {passage.reference})" if passage else ""),
        "=" * 78,
    ]
    if passage is not None:
        lines.append("CONTENT:")
        lines.append(f"  {passage.content}")
        lines.append("")
    if error is not None:
        lines.append(f"*** VALIDATION FAILED: {error} ***")
        lines.append("")
        return "\n".join(lines)
    lines.append(f"FACETS ({len(merged.facets)}):")
    for i, f in enumerate(merged.facets, 1):
        lines.append(format_facet(i, f))
        lines.append("")
    lines.append("ANNOTATION:")
    lines.append(f"  {merged.annotation}")
    if warnings:
        lines.append("")
        lines.append("WARNINGS:")
        for w in warnings:
            lines.append(f"  - {w}")
    lines.append("")
    return "\n".join(lines)


def build_summary_table(results: dict[str, list], failures: dict[str, int],
                        warning_counts: dict[str, int]) -> str:
    lines = ["=" * 78, "SUMMARY", "=" * 78]
    header = (f"{'collection':26s} {'chunks':>7s} {'facets':>7s} "
              f"{'expl/set/inf':>13s} {'2nd-kind':>9s} {'warn':>5s} {'fail':>5s}")
    lines.append(header)
    lines.append("-" * len(header))
    all_collections = sorted(set(list(results) + list(failures)))
    for collection in all_collections:
        merged_list = results.get(collection, [])
        all_facets = [f for m in merged_list for f in m.facets]
        grounding_counts = Counter(f.grounding for f in all_facets)
        secondary_count = sum(1 for f in all_facets if f.kind_secondary)
        ground_str = (f"{grounding_counts.get('explicit', 0)}/"
                     f"{grounding_counts.get('settled', 0)}/"
                     f"{grounding_counts.get('inferential', 0)}")
        lines.append(
            f"{collection:26s} {len(merged_list):>7d} {len(all_facets):>7d} "
            f"{ground_str:>13s} {secondary_count:>9d} "
            f"{warning_counts.get(collection, 0):>5d} {failures.get(collection, 0):>5d}")
        kind_counts = Counter(f.kind for f in all_facets)
        if kind_counts:
            lines.append(f"    kind distribution: {dict(sorted(kind_counts.items()))}")
    return "\n".join(lines)


async def run(chunks_csv: str, out_path: str | None) -> str:
    from stages.parse import parse
    from enrichment.client import EnrichmentClient
    from enrichment.merge import MergeError
    from enrichment.validation import ValidationFailedError
    from stages.enrich import EnrichDeps, enrich_one
    import stages.enrich as enrich_mod

    rows = read_chunk_list(chunks_csv)
    if not rows:
        raise SystemExit(f"No chunk rows found in {chunks_csv}. Expected columns: collection,anchor")
    grouped = group_by_collection(rows)

    api_key = settings.require_anthropic()
    gen_client = EnrichmentClient(api_key, settings.ANTHROPIC_ENRICH_MODEL, settings.OPUS_CONCURRENCY)
    classify_client = EnrichmentClient(api_key, settings.ANTHROPIC_CLASSIFY_MODEL,
                                       settings.CLASSIFY_CONCURRENCY)
    deps = EnrichDeps(cache=None, gen_client=gen_client, classify_client=classify_client,
                      backup=None, annotation_writer=None)

    collector = WarningCollector()
    enrich_mod.logger.addHandler(collector)
    enrich_mod.logger.setLevel(logging.WARNING)

    results: dict[str, list] = defaultdict(list)
    failures: dict[str, int] = defaultdict(int)
    warning_counts: dict[str, int] = defaultdict(int)
    report_sections: list[str] = []

    try:
        for collection, anchors in grouped.items():
            docs = parse(collection)
            by_anchor = {p.anchor: (d, p) for d in docs for p in d.passages}
            for anchor in anchors:
                found = by_anchor.get(anchor)
                if found is None:
                    report_sections.append(format_chunk_report(
                        collection, anchor, None,
                        error=f"no chunk found with anchor {anchor!r} in collection {collection!r}"))
                    failures[collection] += 1
                    continue
                doc, passage = found
                collector.messages.clear()
                try:
                    merged, _usage = await enrich_one(doc, passage, deps, sample=True)
                except (ValidationFailedError, MergeError) as exc:
                    report_sections.append(format_chunk_report(
                        collection, anchor, passage, error=str(exc)))
                    failures[collection] += 1
                    continue
                chunk_warnings = list(collector.messages)
                warning_counts[collection] += len(chunk_warnings)
                results[collection].append(merged)
                report_sections.append(format_chunk_report(
                    collection, anchor, passage, merged=merged, warnings=chunk_warnings))
    finally:
        enrich_mod.logger.removeHandler(collector)
        await gen_client.close()
        await classify_client.close()

    summary = build_summary_table(results, failures, warning_counts)

    if out_path is None:
        os.makedirs(SAMPLE_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M")
        out_path = os.path.join(SAMPLE_DIR, f"enrichment_sample_run-{ts}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_sections))
        f.write("\n")
        f.write(summary)
        f.write("\n")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks-csv", required=True,
                    help="CSV with columns: collection,anchor (optional header row)")
    ap.add_argument("--out", default=None,
                    help="Output review file path (default: samples/enrichment_sample_run-<ts>.txt)")
    args = ap.parse_args()
    written_to = asyncio.run(run(args.chunks_csv, args.out))
    print(f"Review written to {written_to}")
