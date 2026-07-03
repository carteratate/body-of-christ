#!/usr/bin/env python3
# services/api/run_compare_batch.py
"""CLI entry point for the batch compare runner.

Usage:
  # Run all 50 queries (dev server must be running on :8000)
  python run_compare_batch.py --output results/batch_001.jsonl

  # Resume an interrupted run
  python run_compare_batch.py --output results/batch_001.jsonl

  # Generate HTML report from existing JSONL (no server needed)
  python run_compare_batch.py --report results/batch_001.jsonl

  # Dry run — print queries without calling the server
  python run_compare_batch.py --dry-run

  # Run specific query indices only
  python run_compare_batch.py --output /tmp/test.jsonl --queries 0 1 2

  # Subset of pipelines
  python run_compare_batch.py --output results/haiku_only.jsonl --pipelines s2_5_haiku s4_haiku
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_ALL_PIPELINES = ["s2_5_cohere", "s2_5_haiku", "s4_cohere", "s4_haiku"]
_ALL_COLLECTIONS = [
    "bible", "catechism", "summa", "encyclicals", "councils",
    "church-fathers", "medieval", "canon-law", "apostolic-exhortations",
    "papal-documents",
]
_COST_PER_QUERY_EST = 0.34  # all 4 pipelines + judge


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch RAG pipeline evaluation tool")
    p.add_argument("--output", help="JSONL output path (auto-named if omitted)")
    p.add_argument("--report", metavar="JSONL",
                   help="Generate HTML report from existing JSONL and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="Print queries without running")
    p.add_argument("--concurrency", type=int, default=3,
                   help="Max parallel queries (default: 3)")
    p.add_argument("--quota", type=int, default=4,
                   help="Chunks per collection (default: 4)")
    p.add_argument("--pipelines", nargs="+", default=_ALL_PIPELINES,
                   metavar="PIPELINE")
    p.add_argument("--collections", nargs="+", default=_ALL_COLLECTIONS,
                   metavar="COLLECTION")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--queries", type=int, nargs="+", metavar="IDX",
                   help="Only run specific query indices (0-based)")
    return p.parse_args()


def _print_summary(stats: "AggregateStats") -> None:
    dims = ["retrieval_relevance", "best_passage_selection",
            "multi_angle_coverage", "doctrinal_completeness", "redundancy_rate"]
    short = ["RR", "BPS", "MAC", "DC", "RdR"]
    header = f"{'Pipeline':<20} {'Mean':>6}  " + "  ".join(f"{s:>4}" for s in short) + "  Win%"
    print(f"\n{header}")
    print("-" * len(header))
    for p in stats.pipelines:
        dim_vals = "  ".join(f"{p.mean_dimensions.get(d, 0):.2f}" for d in dims)
        print(f"{p.pipeline:<20} {p.mean_total:.3f}  {dim_vals}  {p.win_rate*100:.0f}%")


def _report_mode(jsonl_path: Path) -> None:
    from compare_batch.aggregate import load_records, compute_stats
    from compare_batch.report import render_report

    records = load_records(jsonl_path)
    if not records:
        logger.error("No records found in %s", jsonl_path)
        sys.exit(1)

    stats = compute_stats(records)
    report_path = jsonl_path.with_suffix(".html")
    report_path.write_text(render_report(stats, records))
    logger.info("Report written to %s", report_path)
    _print_summary(stats)
    print(f"\n{stats.n_queries} queries · report: {report_path}")


async def _run_mode(args: argparse.Namespace) -> None:
    from compare_batch.queries import QUERIES
    from compare_batch.runner import run_batch

    valid_indices = [i for i in args.queries if i < len(QUERIES)] if args.queries else None
    queries = [QUERIES[i] for i in valid_indices] if valid_indices else QUERIES

    if args.dry_run:
        for pos, q in enumerate(queries):
            idx = valid_indices[pos] if valid_indices else pos
            print(f"[{idx:02d}] ({q.category:<12}) {q.query}")
        est = len(queries) * _COST_PER_QUERY_EST * (len(args.pipelines) / 4)
        print(f"\n{len(queries)} queries · estimated cost: ${est:.2f}")
        return

    if args.output:
        output_path = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"results/batch_{ts}.jsonl")

    n = len(queries)
    est = n * _COST_PER_QUERY_EST * (len(args.pipelines) / 4)
    logger.info(
        "Batch: %d queries · %d pipelines · concurrency=%d · quota=%d · est. cost $%.2f",
        n, len(args.pipelines), args.concurrency, args.quota, est,
    )
    logger.info("Output: %s", output_path)

    await run_batch(
        queries=queries,
        output_path=output_path,
        pipelines=args.pipelines,
        collections=args.collections,
        quota=args.quota,
        concurrency=args.concurrency,
        base_url=args.base_url,
    )

    from compare_batch.aggregate import load_records, compute_stats
    from compare_batch.report import render_report

    records = load_records(output_path)
    if records:
        stats = compute_stats(records)
        report_path = output_path.with_suffix(".html")
        report_path.write_text(render_report(stats, records))
        logger.info("Report: %s", report_path)
        _print_summary(stats)


def main() -> None:
    args = _parse_args()
    if args.report:
        _report_mode(Path(args.report))
        return
    asyncio.run(_run_mode(args))


if __name__ == "__main__":
    main()
