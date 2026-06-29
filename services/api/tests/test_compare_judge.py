import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.compare.judge import run as judge_run, JudgeReport
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
    assert report.model == "claude-haiku-4-5"
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
    assert report.model == "claude-haiku-4-5"
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
