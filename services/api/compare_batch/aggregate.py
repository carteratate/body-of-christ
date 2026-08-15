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


def _methodology_key(pipeline_result: dict) -> str:
    """Create a stable aggregate key that never mixes rerank contracts."""
    pipeline = pipeline_result["pipeline"]
    version = pipeline_result.get("rerank_contract_version")
    # Unversioned historical records retain their old display key; every new
    # version receives a distinct suffix, so combining/resuming files cannot mix.
    return f"{pipeline}@{version}" if version else pipeline


@dataclass
class PipelineStats:
    pipeline: str
    n: int                                    # queries where this pipeline had a judge score
    mean_total: float
    mean_dimensions: dict[str, float]
    win_rate: float                           # fraction of all queries where this pipeline tied-for-best
    win_rate_by_category: dict[str, float]
    mean_total_by_category: dict[str, float]
    mean_duration_s: float | None
    mean_cost: float | None


@dataclass
class AggregateStats:
    n_queries: int
    pipelines: list[PipelineStats]           # sorted best-to-worst by mean_total
    categories: list[str]
    quarantined_results: int = 0


def compute_stats(records: list[dict]) -> AggregateStats:
    n_queries = len(records)
    categories_seen: set[str] = set()

    # pipeline → list of per-query entries
    pipeline_rows: dict[str, list[dict]] = defaultdict(list)
    wins: dict[str, int] = defaultdict(int)
    wins_by_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals_by_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    appearances: dict[str, int] = defaultdict(int)
    appearances_by_cat: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    comparable_appearances: dict[str, int] = defaultdict(int)
    comparable_appearances_by_cat: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    quarantined_results = 0

    for record in records:
        category = record.get("category", "unknown")
        categories_seen.add(category)

        judge = record.get("judge") or {}
        scores = judge.get("scores") or []
        pipeline_results = record.get("pipeline_results") or []
        timing_map: dict[str, dict] = {
            pr["pipeline"]: {**pr, "methodology_key": _methodology_key(pr)}
            for pr in pipeline_results
        }

        methodology_pipelines = ((record.get("methodology") or {}).get("pipelines") or {})
        requested_pipelines = set(methodology_pipelines) or set(timing_map)
        result_names = [pr.get("pipeline") for pr in pipeline_results]
        score_names = [score.get("pipeline") for score in scores]
        complete_contract = (
            len(result_names) == len(set(result_names))
            and len(score_names) == len(set(score_names))
            and set(result_names) == requested_pipelines
            and set(score_names) == requested_pipelines
        )

        if judge.get("valid") is not True or not complete_contract:
            quarantined_results += len(requested_pipelines or timing_map)
            continue

        eligible_scores: list[tuple[dict, str, dict]] = []
        for s in scores:
            raw_pipeline = s["pipeline"]
            dims_raw = s.get("dimensions") or {}
            dim_scores = {
                dim: float((dims_raw.get(dim) or {}).get("score", 0.0))
                for dim in DIMENSIONS
            }
            timing = timing_map.get(raw_pipeline, {})
            pipeline = timing.get(
                "methodology_key", raw_pipeline,
            )
            # Missing eligibility means a legacy artifact that cannot prove the
            # configured reranker completed. Quarantine rather than silently score.
            if timing.get("quality_eligible") is not True:
                quarantined_results += 1
                continue
            eligible_scores.append((s, pipeline, timing))
            appearances[pipeline] += 1
            appearances_by_cat[category][pipeline] += 1
            pipeline_rows[pipeline].append({
                "weighted_total": float(s.get("weighted_total", 0.0)),
                "dimensions": dim_scores,
                "category": category,
                "duration_s": (
                    float(timing.get("total_duration_s", 0.0))
                    if timing.get("latency_eligible") is True else None
                ),
                "cost": (
                    float(timing.get("total_cost", 0.0))
                    if timing.get("cost_eligible") is True else None
                ),
            })
            totals_by_cat[category][pipeline].append(float(s.get("weighted_total", 0.0)))

        # A win is meaningful only for a complete head-to-head. Keep per-pipeline
        # quality means above, but do not reward a survivor merely because one of
        # its configured competitors degraded or was omitted by the judge.
        expected_pipelines = requested_pipelines
        eligible_raw_pipelines = {score[0]["pipeline"] for score in eligible_scores}
        comparable = (
            bool(expected_pipelines)
            and eligible_raw_pipelines == expected_pipelines
            and len(eligible_scores) == len(expected_pipelines)
        )
        if comparable:
            for _score, pipeline, _timing in eligible_scores:
                comparable_appearances[pipeline] += 1
                comparable_appearances_by_cat[category][pipeline] += 1
            max_total = max(
                float(score.get("weighted_total", 0.0))
                for score, _pipeline, _timing in eligible_scores
            )
            for s, pipeline, _timing in eligible_scores:
                if float(s.get("weighted_total", 0.0)) >= max_total - 1e-9:
                    wins[pipeline] += 1
                    wins_by_cat[category][pipeline] += 1

    pipeline_stats: list[PipelineStats] = []
    for pipeline, rows in pipeline_rows.items():
        n = len(rows)
        mean_total = sum(r["weighted_total"] for r in rows) / n
        mean_dimensions = {
            dim: sum(r["dimensions"][dim] for r in rows) / n
            for dim in DIMENSIONS
        }
        comparable_n = comparable_appearances[pipeline]
        win_rate = wins[pipeline] / comparable_n if comparable_n else 0.0

        win_rate_by_cat: dict[str, float] = {}
        mean_total_by_cat: dict[str, float] = {}
        for cat in categories_seen:
            n_cat = comparable_appearances_by_cat[cat][pipeline]
            win_rate_by_cat[cat] = wins_by_cat[cat][pipeline] / n_cat if n_cat else 0.0
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
            mean_duration_s=round(
                sum(r["duration_s"] for r in rows if r["duration_s"] is not None)
                / sum(1 for r in rows if r["duration_s"] is not None),
                2,
            ) if any(r["duration_s"] is not None for r in rows) else None,
            mean_cost=round(
                sum(r["cost"] for r in rows if r["cost"] is not None)
                / sum(1 for r in rows if r["cost"] is not None),
                6,
            ) if any(r["cost"] is not None for r in rows) else None,
        ))

    pipeline_stats.sort(key=lambda p: p.mean_total, reverse=True)

    return AggregateStats(
        n_queries=n_queries,
        pipelines=pipeline_stats,
        categories=sorted(categories_seen),
        quarantined_results=quarantined_results,
    )


def load_records(jsonl_path: Path) -> list[dict]:
    records = []
    seen_query_indices: set[int] = set()
    with jsonl_path.open() as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Malformed JSONL record at line {line_number} in {jsonl_path}"
                    ) from exc
                if not isinstance(record, dict):
                    raise ValueError(
                        f"JSONL record at line {line_number} must be an object."
                    )
                query_idx = record.get("query_idx")
                if (
                    isinstance(query_idx, bool)
                    or not isinstance(query_idx, int)
                    or query_idx < 0
                ):
                    raise ValueError(
                        f"JSONL record at line {line_number} has an invalid query_idx."
                    )
                if query_idx in seen_query_indices:
                    raise ValueError(f"Duplicate query_idx {query_idx} in {jsonl_path}.")
                seen_query_indices.add(query_idx)
                records.append(record)
    fingerprints = {record.get("batch_fingerprint") for record in records}
    if records and (None in fingerprints or len(fingerprints) != 1):
        raise ValueError(
            "Batch report requires one nonmissing batch_fingerprint; "
            "the artifact is legacy or mixes methodologies."
        )
    return records
