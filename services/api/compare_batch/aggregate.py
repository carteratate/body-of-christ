"""Compute aggregate statistics from batch compare JSONL records."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DIMENSIONS = [
    "retrieval_relevance",
    "best_passage_selection",
    "multi_angle_coverage",
    "doctrinal_completeness",
    "redundancy_rate",
]


@dataclass
class PipelineStats:
    pipeline: str
    n: int                                    # queries where this pipeline had a judge score
    mean_total: float
    mean_dimensions: dict[str, float]
    win_rate: float                           # fraction of all queries where this pipeline tied-for-best
    win_rate_by_category: dict[str, float]
    mean_total_by_category: dict[str, float]
    mean_duration_s: float
    mean_cost: float


@dataclass
class AggregateStats:
    n_queries: int
    pipelines: list[PipelineStats]           # sorted best-to-worst by mean_total
    categories: list[str]


def compute_stats(records: list[dict]) -> AggregateStats:
    n_queries = len(records)
    categories_seen: set[str] = set()

    # pipeline → list of per-query entries
    pipeline_rows: dict[str, list[dict]] = defaultdict(list)
    wins: dict[str, int] = defaultdict(int)
    wins_by_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals_by_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    queries_by_cat: dict[str, int] = defaultdict(int)

    for record in records:
        category = record.get("category", "unknown")
        categories_seen.add(category)
        queries_by_cat[category] += 1

        judge = record.get("judge") or {}
        scores = judge.get("scores") or []
        timing_map: dict[str, dict] = {
            pr["pipeline"]: pr
            for pr in (record.get("pipeline_results") or [])
        }

        for s in scores:
            pipeline = s["pipeline"]
            dims_raw = s.get("dimensions") or {}
            dim_scores = {
                dim: float((dims_raw.get(dim) or {}).get("score", 0.0))
                for dim in DIMENSIONS
            }
            timing = timing_map.get(pipeline, {})
            pipeline_rows[pipeline].append({
                "weighted_total": float(s.get("weighted_total", 0.0)),
                "dimensions": dim_scores,
                "category": category,
                "duration_s": float(timing.get("total_duration_s", 0.0)),
                "cost": float(timing.get("total_cost", 0.0)),
            })
            totals_by_cat[category][pipeline].append(float(s.get("weighted_total", 0.0)))

        if scores:
            max_total = max(float(s.get("weighted_total", 0.0)) for s in scores)
            for s in scores:
                if float(s.get("weighted_total", 0.0)) >= max_total - 1e-9:
                    wins[s["pipeline"]] += 1
                    wins_by_cat[category][s["pipeline"]] += 1

    pipeline_stats: list[PipelineStats] = []
    for pipeline, rows in pipeline_rows.items():
        n = len(rows)
        mean_total = sum(r["weighted_total"] for r in rows) / n
        mean_dimensions = {
            dim: sum(r["dimensions"][dim] for r in rows) / n
            for dim in DIMENSIONS
        }
        win_rate = wins[pipeline] / n_queries if n_queries > 0 else 0.0

        win_rate_by_cat: dict[str, float] = {}
        mean_total_by_cat: dict[str, float] = {}
        for cat, n_cat in queries_by_cat.items():
            win_rate_by_cat[cat] = wins_by_cat[cat][pipeline] / n_cat if n_cat > 0 else 0.0
            cat_vals = totals_by_cat[cat][pipeline]
            mean_total_by_cat[cat] = sum(cat_vals) / len(cat_vals) if cat_vals else 0.0

        pipeline_stats.append(PipelineStats(
            pipeline=pipeline,
            n=n,
            mean_total=round(mean_total, 4),
            mean_dimensions={k: round(v, 4) for k, v in mean_dimensions.items()},
            win_rate=win_rate,
            win_rate_by_category={k: round(v, 4) for k, v in win_rate_by_cat.items()},
            mean_total_by_category={k: round(v, 4) for k, v in mean_total_by_cat.items()},
            mean_duration_s=round(sum(r["duration_s"] for r in rows) / n, 2),
            mean_cost=round(sum(r["cost"] for r in rows) / n, 6),
        ))

    pipeline_stats.sort(key=lambda p: p.mean_total, reverse=True)

    return AggregateStats(
        n_queries=n_queries,
        pipelines=pipeline_stats,
        categories=sorted(categories_seen),
    )


def load_records(jsonl_path: Path) -> list[dict]:
    records = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records
