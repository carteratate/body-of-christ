import json
import pytest

from compare_batch.aggregate import (
    compute_stats, load_records, AggregateStats, PipelineStats, DIMENSIONS,
)

DIMENSION_KEYS = [
    "retrieval_relevance",
    "best_passage_selection",
    "multi_angle_coverage",
    "doctrinal_completeness",
    "redundancy_rate",
]

WEIGHTS = {
    "retrieval_relevance": 0.30,
    "best_passage_selection": 0.20,
    "multi_angle_coverage": 0.20,
    "doctrinal_completeness": 0.15,
    "redundancy_rate": 0.15,
}


def _weighted_total(dim_scores: dict[str, float]) -> float:
    return round(sum(dim_scores[d] * WEIGHTS[d] for d in DIMENSION_KEYS), 4)


def _make_record(query_idx, query, category, scores_by_pipeline):
    judge_scores = []
    for pipeline, dim_scores in scores_by_pipeline.items():
        judge_scores.append({
            "pipeline": pipeline,
            "dimensions": {
                dim: {"score": dim_scores[dim], "reasoning": "test"}
                for dim in DIMENSION_KEYS
            },
            "weighted_total": _weighted_total(dim_scores),
            "summary": "test summary",
        })
    return {
        "query_idx": query_idx,
        "query": query,
        "category": category,
        "expected_collections": [],
        "judge": {"scores": judge_scores, "cost": 0.12, "valid": True},
        "pipeline_results": [
            {
                "pipeline": p, "total_duration_s": 10.0, "total_cost": 0.02,
                "chunk_count": 10, "quality_eligible": True,
                "latency_eligible": True, "cost_eligible": True,
            }
            for p in scores_by_pipeline
        ],
    }


def _perfect():
    return {d: 1.0 for d in DIMENSION_KEYS}


def _zero():
    return {d: 0.0 for d in DIMENSION_KEYS}


def test_compute_stats_returns_aggregate_stats():
    records = [
        _make_record(0, "q1", "doctrinal", {
            "s2_5_haiku": _perfect(),
            "s4_haiku": {**_perfect(), "retrieval_relevance": 0.5},
        }),
    ]
    stats = compute_stats(records)
    assert isinstance(stats, AggregateStats)
    assert stats.n_queries == 1
    assert len(stats.pipelines) == 2


def test_mean_total_calculation():
    records = [
        _make_record(0, "q1", "doctrinal", {
            "s2_5_haiku": _perfect(),   # weighted_total = 1.0
            "s4_haiku": _zero(),        # weighted_total = 0.0
        }),
        _make_record(1, "q2", "ethical", {
            "s2_5_haiku": _perfect(),   # 1.0
            "s4_haiku": _perfect(),     # 1.0
        }),
    ]
    stats = compute_stats(records)
    h25 = next(p for p in stats.pipelines if p.pipeline == "s2_5_haiku")
    h4  = next(p for p in stats.pipelines if p.pipeline == "s4_haiku")
    assert abs(h25.mean_total - 1.0) < 1e-6
    assert abs(h4.mean_total - 0.5) < 1e-6


def test_win_rate():
    records = [
        _make_record(0, "q1", "doctrinal", {"a": _perfect(), "b": _zero()}),   # a wins
        _make_record(1, "q2", "ethical",   {"a": _zero(),    "b": _perfect()}), # b wins
        _make_record(2, "q3", "pastoral",  {"a": _perfect(), "b": _perfect()}), # tie → both win
    ]
    stats = compute_stats(records)
    a = next(p for p in stats.pipelines if p.pipeline == "a")
    b = next(p for p in stats.pipelines if p.pipeline == "b")
    assert abs(a.win_rate - 2/3) < 1e-6
    assert abs(b.win_rate - 2/3) < 1e-6


def test_mean_dimension_scores():
    records = [
        _make_record(0, "q1", "doctrinal", {"p": {
            "retrieval_relevance": 0.8,
            "best_passage_selection": 0.6,
            "multi_angle_coverage": 0.4,
            "doctrinal_completeness": 1.0,
            "redundancy_rate": 0.9,
        }}),
        _make_record(1, "q2", "ethical", {"p": {
            "retrieval_relevance": 0.4,
            "best_passage_selection": 0.8,
            "multi_angle_coverage": 0.6,
            "doctrinal_completeness": 0.5,
            "redundancy_rate": 0.7,
        }}),
    ]
    stats = compute_stats(records)
    p = stats.pipelines[0]
    assert abs(p.mean_dimensions["retrieval_relevance"] - 0.6) < 1e-6
    assert abs(p.mean_dimensions["best_passage_selection"] - 0.7) < 1e-6


def test_win_rate_by_category():
    records = [
        _make_record(0, "q1", "doctrinal", {"a": _perfect(), "b": _zero()}),
        _make_record(1, "q2", "doctrinal", {"a": _zero(),    "b": _perfect()}),
        _make_record(2, "q3", "ethical",   {"a": _perfect(), "b": _zero()}),
    ]
    stats = compute_stats(records)
    a = next(p for p in stats.pipelines if p.pipeline == "a")
    assert abs(a.win_rate_by_category["doctrinal"] - 0.5) < 1e-6
    assert abs(a.win_rate_by_category["ethical"] - 1.0) < 1e-6


def test_record_with_empty_judge_scores_counts_in_n_queries():
    records = [
        _make_record(0, "q1", "doctrinal", {"a": _perfect()}),
        {
            "query_idx": 1, "query": "q2", "category": "ethical",
            "expected_collections": [],
            "judge": {"scores": [], "cost": 0.0},
            "pipeline_results": [],
        },
    ]
    stats = compute_stats(records)
    assert stats.n_queries == 2
    a = next(p for p in stats.pipelines if p.pipeline == "a")
    assert a.n == 1


def test_dimensions_constant_matches_expected():
    assert DIMENSIONS == [
        "retrieval_relevance",
        "best_passage_selection",
        "multi_angle_coverage",
        "doctrinal_completeness",
        "redundancy_rate",
    ]


def test_contract_versions_are_aggregated_separately():
    legacy = _make_record(0, "q1", "doctrinal", {"hyde_haiku": _perfect()})
    structured = _make_record(1, "q2", "doctrinal", {"hyde_haiku": _perfect()})
    structured["pipeline_results"][0]["rerank_contract_version"] = (
        "structured-positional-v1"
    )

    stats = compute_stats([legacy, structured])
    assert {pipeline.pipeline for pipeline in stats.pipelines} == {
        "hyde_haiku",
        "hyde_haiku@structured-positional-v1",
    }
    assert all(pipeline.n == 1 for pipeline in stats.pipelines)


def test_ineligible_and_unversioned_legacy_results_are_quarantined():
    degraded = _make_record(0, "q1", "doctrinal", {"a": _perfect()})
    degraded["pipeline_results"][0]["quality_eligible"] = False
    legacy = _make_record(1, "q2", "doctrinal", {"a": _perfect()})
    del legacy["pipeline_results"][0]["quality_eligible"]

    stats = compute_stats([degraded, legacy])

    assert stats.pipelines == []
    assert stats.quarantined_results == 2


def test_invalid_judge_scores_are_quarantined():
    record = _make_record(0, "q", "doctrinal", {"a": _zero(), "b": _zero()})
    record["judge"]["valid"] = False

    stats = compute_stats([record])

    assert stats.pipelines == []
    assert stats.quarantined_results == 2


def test_invalid_judge_counts_expected_results_when_scores_are_missing():
    record = _make_record(0, "q", "doctrinal", {"a": _zero(), "b": _zero()})
    record["judge"] = {"scores": [], "valid": False}

    stats = compute_stats([record])

    assert stats.pipelines == []
    assert stats.quarantined_results == 2


def test_versioned_win_rate_uses_eligible_appearances_not_all_queries():
    legacy = _make_record(0, "q1", "doctrinal", {"a": _perfect()})
    versioned = _make_record(1, "q2", "doctrinal", {"a": _perfect()})
    versioned["pipeline_results"][0]["rerank_contract_version"] = "v2"

    stats = compute_stats([legacy, versioned])

    assert all(pipeline.win_rate == 1.0 for pipeline in stats.pipelines)


def test_degraded_competitor_does_not_award_an_uncontested_win():
    record = _make_record(0, "q", "doctrinal", {"a": _perfect(), "b": _zero()})
    record["pipeline_results"][1]["quality_eligible"] = False

    stats = compute_stats([record])

    a = next(pipeline for pipeline in stats.pipelines if pipeline.pipeline == "a")
    assert a.n == 1
    assert a.win_rate == 0.0


def test_ineligible_latency_and_cost_are_unavailable_not_zero():
    record = _make_record(0, "q", "doctrinal", {"a": _perfect()})
    result = record["pipeline_results"][0]
    result["latency_eligible"] = False
    result["cost_eligible"] = False

    pipeline = compute_stats([record]).pipelines[0]

    assert pipeline.mean_duration_s is None
    assert pipeline.mean_cost is None


def test_load_records_rejects_malformed_or_mixed_batch_artifacts(tmp_path):
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"batch_fingerprint":"a","query_idx":0}\n{broken}\n')
    with pytest.raises(ValueError, match="line 2"):
        load_records(malformed)

    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text("\n".join([
        json.dumps({"batch_fingerprint": "a", "query_idx": 0}),
        json.dumps({"batch_fingerprint": "b", "query_idx": 1}),
    ]) + "\n")
    with pytest.raises(ValueError, match="mixes methodologies"):
        load_records(mixed)


def test_load_records_rejects_duplicate_query_indices(tmp_path):
    artifact = tmp_path / "duplicate.jsonl"
    record = {"batch_fingerprint": "a", "query_idx": 0}
    artifact.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n")

    with pytest.raises(ValueError, match="Duplicate query_idx 0"):
        load_records(artifact)


def test_missing_requested_pipeline_quarantines_entire_contest():
    record = _make_record(0, "q", "doctrinal", {"a": _perfect()})
    record["methodology"] = {"pipelines": {"a": {}, "b": {}}}

    stats = compute_stats([record])

    assert stats.pipelines == []
    assert stats.quarantined_results == 2


def test_duplicate_judge_pipeline_quarantines_entire_contest():
    record = _make_record(0, "q", "doctrinal", {"a": _perfect()})
    record["judge"]["scores"].append(record["judge"]["scores"][0])

    stats = compute_stats([record])

    assert stats.pipelines == []
    assert stats.quarantined_results == 1
