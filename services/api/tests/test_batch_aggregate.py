from compare_batch.aggregate import compute_stats, AggregateStats, PipelineStats, DIMENSIONS

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
        "judge": {"scores": judge_scores, "cost": 0.12},
        "pipeline_results": [
            {"pipeline": p, "total_duration_s": 10.0, "total_cost": 0.02, "chunk_count": 10}
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
