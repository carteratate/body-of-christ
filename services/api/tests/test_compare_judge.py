import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.compare.judge import (
    run as judge_run,
    JudgeReport,
    DimensionScore,
    JudgeScore,
    WEIGHTS,
    compute_weighted_total,
)
from app.rag.compare.overlap import OverlapReport
from app.rag.steps.types import RankedChunk, PipelineResult, StepTiming


def _make_result(pipeline: str) -> PipelineResult:
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000001",
        content="For God so loved the world.",
        reference="John 3:16",
        collection="bible",
        document_id="d1",
        document_title="Bible",
        author=None,
        reranker_score=0.9,
    )
    return PipelineResult(
        pipeline=pipeline,
        chunks=[chunk],
        step_timings=[StepTiming("embed", 0.1)],
        total_duration_s=1.0,
        cost_breakdown={},
        total_cost=0.0,
    )


@pytest.mark.asyncio
async def test_judge_returns_report():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku"), _make_result("s4_haiku")]

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"scores": [{"pipeline": "s2_5_haiku", "score": 0.8, "reasoning": "good"}, '
                 '{"pipeline": "s4_haiku", "score": 0.7, "reasoning": "ok"}], '
                 '"overall_reasoning": "s2_5 wins"}'
        )
    ]
    mock_response.usage = MagicMock(input_tokens=500, output_tokens=200)

    with patch("anthropic.AsyncAnthropic"):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        import app.rag.compare.judge as judge_module
        judge_module._client = mock_client

        report = await judge_run("what is love?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 2
    assert report.model == "claude-sonnet-4-6"
    assert report.cost > 0


@pytest.mark.asyncio
async def test_judge_falls_back_on_llm_error():
    """If the LLM call raises, judge returns a report with zero scores and no cost."""
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku"), _make_result("s4_haiku")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=RuntimeError("network error"))

    import app.rag.compare.judge as judge_module
    judge_module._client = mock_client

    report = await judge_run("what is love?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert report.model == "claude-sonnet-4-6"
    # Scores still contain one entry per pipeline with 0.0 score
    assert len(report.scores) == 2
    assert all(s.score == 0.0 for s in report.scores)
    # No tokens used when the call failed
    assert report.tokens_used == 0
    # Cost is zero when no successful LLM call
    assert report.cost == 0.0
    # overall_reasoning explains the failure
    assert "failed" in report.overall_reasoning.lower() or "Judge" in report.overall_reasoning


@pytest.mark.asyncio
async def test_judge_falls_back_on_json_parse_error():
    """If the LLM returns malformed JSON, judge returns fallback scores."""
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku")]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="this is not json")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=20)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    import app.rag.compare.judge as judge_module
    judge_module._client = mock_client

    report = await judge_run("grace?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 1
    assert report.scores[0].score == 0.0


@pytest.mark.asyncio
async def test_judge_scores_include_pipeline_names():
    """Scores are tied to pipeline names from the input results."""
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("pipeline_a"), _make_result("pipeline_b")]

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"scores": [{"pipeline": "pipeline_a", "score": 0.9, "reasoning": "best"}, '
                 '{"pipeline": "pipeline_b", "score": 0.6, "reasoning": "ok"}], '
                 '"overall_reasoning": "pipeline_a wins"}'
        )
    ]
    mock_response.usage = MagicMock(input_tokens=300, output_tokens=100)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    import app.rag.compare.judge as judge_module
    judge_module._client = mock_client

    report = await judge_run("what is faith?", results, overlap)

    pipeline_names = {s.pipeline for s in report.scores}
    assert "pipeline_a" in pipeline_names
    assert "pipeline_b" in pipeline_names
    assert report.overall_reasoning == "pipeline_a wins"
    assert report.tokens_used == 400  # 300 + 100


# ============================================================================
# Task 1: New tests for DimensionScore, weights, and compute_weighted_total
# ============================================================================


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_weights_contain_all_dimensions():
    expected = {
        "retrieval_relevance",
        "best_passage_selection",
        "multi_angle_coverage",
        "doctrinal_completeness",
        "redundancy_rate",
    }
    assert set(WEIGHTS.keys()) == expected


def test_compute_weighted_total_perfect_scores():
    scores = {dim: 1.0 for dim in WEIGHTS}
    assert compute_weighted_total(scores) == 1.0


def test_compute_weighted_total_zero_scores():
    scores = {dim: 0.0 for dim in WEIGHTS}
    assert compute_weighted_total(scores) == 0.0


def test_compute_weighted_total_mixed():
    scores = {
        "retrieval_relevance": 1.0,
        "best_passage_selection": 0.0,
        "multi_angle_coverage": 0.0,
        "doctrinal_completeness": 0.0,
        "redundancy_rate": 0.0,
    }
    # Only retrieval_relevance (weight 0.30) contributes
    assert abs(compute_weighted_total(scores) - 0.30) < 1e-9


def test_dimension_score_dataclass():
    ds = DimensionScore(score=0.8, reasoning="Good coverage.")
    assert ds.score == 0.8
    assert ds.reasoning == "Good coverage."


def test_judge_score_dataclass():
    dims = {
        "retrieval_relevance": DimensionScore(0.9, "On-target."),
        "best_passage_selection": DimensionScore(0.8, "Canonical sections."),
        "multi_angle_coverage": DimensionScore(0.7, "Three angles."),
        "doctrinal_completeness": DimensionScore(1.0, "Non-contested topic."),
        "redundancy_rate": DimensionScore(1.0, "No same-source repeats."),
    }
    total = compute_weighted_total({k: v.score for k, v in dims.items()})
    js = JudgeScore(
        pipeline="s2_5_haiku",
        dimensions=dims,
        weighted_total=total,
        summary="Strong retrieval.",
    )
    assert js.pipeline == "s2_5_haiku"
    assert abs(js.weighted_total - (0.9*0.30 + 0.8*0.20 + 0.7*0.20 + 1.0*0.15 + 1.0*0.15)) < 1e-9
    assert js.summary == "Strong retrieval."


def test_judge_report_dataclass():
    report = JudgeReport(
        scores=[],
        comparative_analysis="No pipelines compared.",
        tokens_used=0,
        cost=0.0,
        model="claude-sonnet-4-6",
    )
    assert report.comparative_analysis == "No pipelines compared."
    assert not hasattr(report, "overall_reasoning")
