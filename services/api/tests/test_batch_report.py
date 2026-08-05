"""Minimal smoke tests for compare_batch.report.render_report."""
from compare_batch.aggregate import compute_stats, DIMENSIONS
from compare_batch.report import render_report
from app.rag.steps.cost_tracker import pricing_snapshot

WEIGHTS = {
    "retrieval_relevance": 0.30,
    "best_passage_selection": 0.20,
    "multi_angle_coverage": 0.20,
    "doctrinal_completeness": 0.15,
    "redundancy_rate": 0.15,
}


def _weighted_total(dim_scores: dict) -> float:
    return round(sum(dim_scores[d] * WEIGHTS[d] for d in DIMENSIONS), 4)


def _make_record(query_idx, query, category, scores_by_pipeline):
    judge_scores = []
    for pipeline, dim_scores in scores_by_pipeline.items():
        judge_scores.append({
            "pipeline": pipeline,
            "dimensions": {
                dim: {"score": dim_scores[dim], "reasoning": "test"}
                for dim in DIMENSIONS
            },
            "weighted_total": _weighted_total(dim_scores),
            "summary": "test summary",
        })
    return {
        "query_idx": query_idx,
        "query": query,
        "category": category,
        "expected_collections": [],
        "pricing": pricing_snapshot(),
        "judge": {"scores": judge_scores, "cost": 0.05},
        "pipeline_results": [
            {"pipeline": p, "total_duration_s": 5.0, "total_cost": 0.01, "chunk_count": 10}
            for p in scores_by_pipeline
        ],
    }


def _perfect():
    return {d: 1.0 for d in DIMENSIONS}


def _make_stats_and_records():
    records = [
        _make_record(0, "What is the Trinity?", "doctrinal", {
            "s2_5_haiku": _perfect(),
            "s4_haiku": {**_perfect(), "retrieval_relevance": 0.5},
        }),
        _make_record(1, "What is grace?", "ethical", {
            "s2_5_haiku": {**_perfect(), "doctrinal_completeness": 0.6},
            "s4_haiku": _perfect(),
        }),
    ]
    return compute_stats(records), records


def test_render_report_returns_html_string():
    stats, records = _make_stats_and_records()
    result = render_report(stats, records)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "<html" in result


def test_render_report_contains_pipeline_names():
    stats, records = _make_stats_and_records()
    result = render_report(stats, records)
    for p in stats.pipelines:
        assert p.pipeline in result


def test_render_report_contains_query_text():
    stats, records = _make_stats_and_records()
    result = render_report(stats, records)
    assert "What is the Trinity?" in result
    assert "What is grace?" in result


def test_render_report_identifies_pricing_schedule():
    stats, records = _make_stats_and_records()
    result = render_report(stats, records)
    assert "Pricing effective 2026-07-30 (USD)" in result


def test_render_report_flags_historical_pricing():
    stats, records = _make_stats_and_records()
    for record in records:
        record["pricing"] = {
            **pricing_snapshot(),
            "effective_date": "2026-07-09",
        }
    result = render_report(stats, records)
    assert "historical rates; current rates differ" in result


def test_render_report_flags_mixed_pricing_schedules():
    stats, records = _make_stats_and_records()
    records[0]["pricing"] = {
        **pricing_snapshot(),
        "effective_date": "2026-07-09",
    }
    result = render_report(stats, records)
    assert "aggregate costs are not comparable" in result


def test_render_report_empty_records():
    """render_report with no records should still return valid HTML."""
    from compare_batch.aggregate import AggregateStats
    stats = AggregateStats(n_queries=0, pipelines=[], categories=[])
    result = render_report(stats, [])
    assert "<html" in result
    assert isinstance(result, str)
