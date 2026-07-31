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


def _make_tool_input(pipelines: list[str]) -> dict:
    """Build a valid score_pipelines tool input for the given pipeline names."""
    return {
        "pipeline_scores": [
            {
                "pipeline": p,
                "retrieval_relevance_reasoning": "All chunks are on-topic.",
                "retrieval_relevance_score": 0.9,
                "best_passage_selection_reasoning": "Canonical sections found.",
                "best_passage_selection_score": 0.8,
                "multi_angle_coverage_reasoning": "Three angles covered.",
                "multi_angle_coverage_score": 0.85,
                "doctrinal_completeness_reasoning": "Non-contested topic; default 1.0.",
                "doctrinal_completeness_score": 1.0,
                "redundancy_rate_reasoning": "No same-source repeats.",
                "redundancy_rate_score": 1.0,
                "summary": f"{p} retrieval is strong.",
            }
            for p in pipelines
        ],
        "comparative_analysis": f"Comparing {len(pipelines)} pipeline(s).",
    }


def _mock_tool_response(tool_input: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    response.usage = MagicMock(input_tokens=500, output_tokens=200)
    return response



def _stub_streaming_client(response, capture: list | None = None):
    """Client double for the judge's streamed call.

    The judge uses `client.with_options(...).messages.stream(...)` as an async
    context manager and awaits `get_final_message()`. Mirrors that shape so the
    tests exercise the real call path rather than a create() that no longer exists.
    """

    class _Stream:
        def __init__(self, **kwargs):
            if capture is not None:
                capture.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_final_message(self):
            if isinstance(response, Exception):
                raise response
            return response

    class _Messages:
        @staticmethod
        def stream(**kwargs):
            return _Stream(**kwargs)

    class _Client:
        messages = _Messages()

        def with_options(self, **_kw):
            return self

    return _Client()


@pytest.mark.asyncio
async def test_judge_returns_multidimensional_report():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku"), _make_result("s4_haiku")]
    mock_response = _mock_tool_response(_make_tool_input(["s2_5_haiku", "s4_haiku"]))

    import app.rag.compare.judge as judge_module
    judge_module._client = _stub_streaming_client(mock_response)

    report = await judge_run("what is love?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 2
    assert report.model == "claude-opus-5"
    assert report.cost > 0
    assert report.tokens_used == 700
    assert report.comparative_analysis == "Comparing 2 pipeline(s)."


@pytest.mark.asyncio
async def test_judge_dimension_scores_parsed_correctly():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku")]
    mock_response = _mock_tool_response(_make_tool_input(["s2_5_haiku"]))

    import app.rag.compare.judge as judge_module
    judge_module._client = _stub_streaming_client(mock_response)

    report = await judge_run("what is grace?", results, overlap)

    score = report.scores[0]
    assert score.pipeline == "s2_5_haiku"
    assert set(score.dimensions.keys()) == set(WEIGHTS.keys())
    assert score.dimensions["retrieval_relevance"].score == 0.9
    assert score.dimensions["retrieval_relevance"].reasoning == "All chunks are on-topic."
    assert score.dimensions["doctrinal_completeness"].score == 1.0
    # Weight values come from WEIGHTS so a re-weighting cannot silently break this,
    # but each dimension is still paired with its own weight by hand — that pairing
    # is the thing that could actually go wrong.
    expected_total = (
        0.9 * WEIGHTS["retrieval_relevance"]
        + 0.8 * WEIGHTS["best_passage_selection"]
        + 0.85 * WEIGHTS["multi_angle_coverage"]
        + 1.0 * WEIGHTS["doctrinal_completeness"]
        + 1.0 * WEIGHTS["redundancy_rate"]
    )
    assert abs(score.weighted_total - expected_total) < 1e-4
    assert score.summary == "s2_5_haiku retrieval is strong."


@pytest.mark.asyncio
async def test_judge_falls_back_on_llm_error():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku"), _make_result("s4_haiku")]

    import app.rag.compare.judge as judge_module
    judge_module._client = _stub_streaming_client(RuntimeError("network error"))

    report = await judge_run("what is love?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 2
    assert all(s.weighted_total == 0.0 for s in report.scores)
    assert all(
        all(ds.score == 0.0 for ds in s.dimensions.values())
        for s in report.scores
    )
    assert report.tokens_used == 0
    assert report.cost == 0.0
    assert "failed" in report.comparative_analysis.lower()


@pytest.mark.asyncio
async def test_judge_falls_back_on_missing_tool_block():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku")]

    # Response with no tool_use block (e.g., text-only response)
    text_block = MagicMock()
    text_block.type = "text"
    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=20)

    import app.rag.compare.judge as judge_module
    judge_module._client = _stub_streaming_client(mock_response)

    report = await judge_run("grace?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 1
    assert report.scores[0].weighted_total == 0.0
    # API call succeeded before StopIteration, so tokens and cost are recorded
    assert report.tokens_used == 120
    assert report.cost > 0


@pytest.mark.asyncio
async def test_judge_scores_include_pipeline_names():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("pipeline_a"), _make_result("pipeline_b")]
    mock_response = _mock_tool_response(_make_tool_input(["pipeline_a", "pipeline_b"]))

    import app.rag.compare.judge as judge_module
    judge_module._client = _stub_streaming_client(mock_response)

    report = await judge_run("what is faith?", results, overlap)

    pipeline_names = {s.pipeline for s in report.scores}
    assert "pipeline_a" in pipeline_names
    assert "pipeline_b" in pipeline_names
    assert report.comparative_analysis == "Comparing 2 pipeline(s)."
    assert report.tokens_used == 700


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
    # Only retrieval_relevance contributes, so the total must be exactly its weight.
    assert abs(compute_weighted_total(scores) - WEIGHTS["retrieval_relevance"]) < 1e-9


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
    expected = (
        0.9 * WEIGHTS["retrieval_relevance"]
        + 0.8 * WEIGHTS["best_passage_selection"]
        + 0.7 * WEIGHTS["multi_angle_coverage"]
        + 1.0 * WEIGHTS["doctrinal_completeness"]
        + 1.0 * WEIGHTS["redundancy_rate"]
    )
    assert abs(js.weighted_total - expected) < 1e-9
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


# --- position bias: presentation order must be randomised and recorded ---

def test_judge_prompt_does_not_send_temperature():
    """Opus 5 removed `temperature` — sending it returns 400 '`temperature` is
    deprecated for this model', which would fail every judge call."""
    import inspect

    from app.rag.compare import judge

    src = inspect.getsource(judge.run)
    # Strip comments so the explanatory note about temperature doesn't self-match.
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )
    assert "temperature=" not in code


def test_judge_leaves_thinking_enabled():
    """Thinking is on by default on Opus 5 and must stay on: with thinking disabled
    the model occasionally emits a tool call as plain text, which this judge would
    read as a missing tool block and silently fall back to all-zero scores."""
    import inspect

    from app.rag.compare import judge

    src = inspect.getsource(judge.run)
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )
    assert "disabled" not in code


@pytest.mark.asyncio
async def test_judge_randomises_presentation_order_and_records_it():
    """A listwise judge weights earlier items more, so a fixed order would give
    whichever pipeline sorts first a permanent advantage."""
    from app.rag.compare import judge

    results = [_make_result(f"p{i}") for i in range(6)]
    mock_response = _mock_tool_response(_make_tool_input([f"p{i}" for i in range(6)]))

    orders: list[list[str]] = []

    captured: list[dict] = []
    stub = _stub_streaming_client(mock_response, capture=captured)

    with patch.object(judge, "_client", stub):
        for _ in range(12):
            report = await judge.run("q", results, OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={}))
            orders.append(report.presentation_order)

    # The recorded order must match the order actually rendered into the prompt.
    prompts = [c["messages"][0]["content"] for c in captured]
    for prompt, order in zip(prompts, orders):
        positions = [prompt.index(f"=== Pipeline: {p} ===") for p in order]
        assert positions == sorted(positions), "recorded order != prompt order"

    # And it must actually vary across calls.
    assert len({tuple(o) for o in orders}) > 1, "presentation order never varied"


@pytest.mark.asyncio
async def test_judge_streams_and_bounds_the_call():
    """A non-streaming judge call hung for 35 minutes in a batch run: Opus 5 with
    adaptive thinking on a large multi-pipeline prompt exceeded the SDK's 10-minute
    default, which then retried twice. Streaming keeps the connection active, and an
    explicit timeout with no retries bounds the worst case."""
    import inspect

    from app.config import settings
    from app.rag.compare import judge

    src = inspect.getsource(judge.run)
    assert "messages.stream(" in src
    assert "get_final_message" in src
    assert "messages.create(" not in src
    assert "max_retries=0" in src  # retry later from cached artifacts
    assert settings.judge_timeout_s > 0


@pytest.mark.asyncio
async def test_judge_warns_when_a_pipeline_is_missing_from_its_scores(caplog):
    """A skipped pipeline is not a zero, so the batch harness's all-zeros guard
    cannot catch it; the aggregate would then average that pipeline over a
    self-selected subset of queries."""
    import app.rag.compare.judge as judge_module

    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("hyde_haiku"), _make_result("hyde_cohere")]
    # Judge returns only one of the two pipelines.
    resp = _mock_tool_response(_make_tool_input(["hyde_haiku"]))
    judge_module._client = _stub_streaming_client(resp)

    with caplog.at_level("WARNING"):
        report = await judge_run("q", results, overlap)

    assert "scored 1 of 2 pipelines" in caplog.text
    assert "hyde_cohere" in caplog.text
    assert {s.pipeline for s in report.scores} == {"hyde_haiku"}


@pytest.mark.asyncio
async def test_judge_drops_hallucinated_pipeline_names(caplog):
    """A name that was never sent would become a phantom pipeline in the aggregate."""
    import app.rag.compare.judge as judge_module

    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("hyde_haiku")]
    resp = _mock_tool_response(_make_tool_input(["hyde_haiku", "Pipeline 3"]))
    judge_module._client = _stub_streaming_client(resp)

    with caplog.at_level("WARNING"):
        report = await judge_run("q", results, overlap)

    assert {s.pipeline for s in report.scores} == {"hyde_haiku"}
    assert "Pipeline 3" in caplog.text


@pytest.mark.asyncio
async def test_judge_is_silent_when_every_pipeline_is_scored(caplog):
    import app.rag.compare.judge as judge_module

    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("a"), _make_result("b")]
    judge_module._client = _stub_streaming_client(
        _mock_tool_response(_make_tool_input(["a", "b"])))

    with caplog.at_level("WARNING"):
        await judge_run("q", results, overlap)
    assert "pipelines (missing" not in caplog.text
