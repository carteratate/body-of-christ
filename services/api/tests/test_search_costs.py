"""Per-search cost persistence (`search_costs`, migration 0036)."""
from __future__ import annotations

import asyncio
import datetime
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag import pipeline
from app.rag.pipelines.registry import PIPELINES
from app.rag.pipelines.runner import PipelineExecutionError
from app.rag.search_plan import resolve_search_plan
from app.rag.steps.cost_tracker import PRICING_EFFECTIVE_DATE, CostTracker
from app.rag.steps.types import RankedChunk

_MIGRATION = Path(__file__).parents[3] / "supabase/migrations/0036_search_costs.sql"
_COLUMNS = (
    "search_id", "audience", "pipeline", "outcome", "completed", "collection_count",
    "quota", "focused", "delivered", "runner_cost", "explanation_cost",
    "cost_breakdown", "cost_eligible", "pricing_effective_date", "models",
)


class _Conn:
    def __init__(self, calls: list, fail: Exception | None = None) -> None:
        self.calls, self.fail = calls, fail

    async def execute(self, sql, *args, **kwargs):
        if self.fail:
            raise self.fail
        self.calls.append((sql, args, kwargs))


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list = []
        self.fail = fail

    def acquire(self, **_kw):
        return _Acquire(_Conn(self.calls, self.fail))

    def rows(self) -> list[dict]:
        return [dict(zip(_COLUMNS, args)) for sql, args, _ in self.calls
                if "INSERT INTO search_costs" in sql]


def _record(**overrides):
    kwargs = dict(
        search_id=None, user_id=None, plan=resolve_search_plan(["bible"], 4),
        config=PIPELINES["hyde_cohere_luna"],
        runner_breakdown={"hyde": 0.001, "rerank_cohere": 0.0025},
        runner_cost_eligible=True, outcome="success", delivered=4, completed=True,
    )
    kwargs.update(overrides)
    pipeline._record_search_cost(**kwargs)


async def _drain() -> None:
    await asyncio.gather(*list(pipeline._COST_WRITES))


@pytest.mark.asyncio
async def test_records_runner_and_explanation_cost_with_models(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    explanation = CostTracker()
    explanation.record("explain", "gpt-6-luna", input_tokens=1000, output_tokens=100)
    search_id = str(uuid.uuid4())

    _record(search_id=search_id, user_id="user-1",
            plan=resolve_search_plan(["bible", "catechism"], 4),
            delivered=8, explanation_cost=explanation)
    await _drain()

    (row,) = pool.rows()
    assert row["search_id"] == uuid.UUID(search_id)
    assert (row["audience"], row["pipeline"], row["outcome"], row["completed"]) == (
        "authenticated", "hyde_cohere_luna", "success", True)
    assert (row["collection_count"], row["quota"], row["focused"], row["delivered"]) == (
        2, 4, False, 8)
    assert row["runner_cost"] == pytest.approx(0.0035)
    assert row["explanation_cost"] == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6)
    # jsonb goes in as objects: app/db.py's codec serialises once. A pre-dumped
    # string would store a jsonb *string* (the 0033 repair).
    assert isinstance(row["cost_breakdown"], dict) and isinstance(row["models"], dict)
    assert set(row["cost_breakdown"]) == {"hyde", "rerank_cohere", "explain"}
    assert row["cost_eligible"] is True
    assert row["pricing_effective_date"] == datetime.date.fromisoformat(PRICING_EFFECTIVE_DATE)
    models = row["models"]
    assert models["rerank"] == "gpt-5.6-luna"
    assert models["rerank_reasoning_effort"] == "medium"
    assert models["explain"] == "gpt-6-luna"
    assert models["explain_reasoning_effort"] == "none"
    assert models["hyde_genre"] == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_guest_and_unpersisted_searches_record_without_a_search_id(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    _record(plan=resolve_search_plan(["bible"], 10), outcome="no_candidates", delivered=0)
    await _drain()

    (row,) = pool.rows()
    assert row["search_id"] is None
    assert row["audience"] == "guest"
    assert row["focused"] is True
    assert row["explanation_cost"] == 0.0


@pytest.mark.asyncio
async def test_write_failure_is_logged_not_raised(monkeypatch, caplog):
    # e.g. migration 0036 not applied yet when the API deploys.
    pool = _Pool(fail=RuntimeError('relation "search_costs" does not exist'))
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    _record()
    with caplog.at_level("WARNING"):
        await _drain()
    assert "search cost persist failed" in caplog.text


@pytest.mark.asyncio
async def test_a_malformed_breakdown_cannot_escape_the_finally(monkeypatch, caplog):
    """The recorder runs from the SSE generator's `finally`; raising there would
    replace whatever the generator was doing with an exception."""
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    with caplog.at_level("WARNING"):
        _record(runner_breakdown={"hyde": "not a number"})
    assert "search cost record skipped" in caplog.text
    assert not pipeline._COST_WRITES and not pool.calls


def test_no_running_loop_is_skipped_without_leaking_a_coroutine(monkeypatch, caplog):
    monkeypatch.setattr(pipeline, "get_pool", lambda: _Pool())
    with caplog.at_level("WARNING"):
        _record()
    assert "search cost record skipped" in caplog.text


def test_no_models_reported_for_hyde_a_pipeline_does_not_run():
    models = pipeline._models_used(PIPELINES["nohyde_cohere"])
    assert "hyde_passage" not in models and "hyde_genre" not in models


def test_no_pool_is_a_no_op(monkeypatch):
    monkeypatch.setattr(pipeline, "get_pool", lambda: None)
    _record()
    assert not pipeline._COST_WRITES


def test_migration_matches_the_insert_and_is_closed_to_the_data_api():
    sql = _MIGRATION.read_text()
    table = sql.split("CREATE TABLE search_costs")[1].split(");")[0]
    for column in _COLUMNS:
        assert f"\n    {column} " in table, column
    assert "user_id" not in table
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON TABLE search_costs FROM PUBLIC, anon, authenticated" in sql
    insert = pipeline._write_search_cost.__code__.co_consts
    assert any(isinstance(c, str) and all(col in c for col in _COLUMNS) for c in insert)


# --- through the SSE generator ------------------------------------------------

def _chunk(i: int) -> RankedChunk:
    return RankedChunk(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content="content",
        reference="Gen 1:1", collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis", author=None, reranker_score=0.9,
    )


def _result(n: int):
    result = MagicMock()
    result.chunks = [_chunk(i) for i in range(n)]
    result.outcome = "success"
    result.collection_outcomes = {"bible": "results"}
    result.delivery_outcome = None
    result.cost_breakdown = {"hyde": 0.001, "rerank_cohere": 0.0025}
    result.cost_eligible = True
    result.total_cost = 0.0035
    result.context = {}
    result.recovery_events = []
    result.degradation_events = []
    return result


async def _one_delta(*_a, cost_tracker=None, **_kw):
    cost_tracker.record("explain", "gpt-6-luna", input_tokens=1000, output_tokens=100)
    yield "because"


@pytest.mark.asyncio
async def test_client_leaving_mid_explanations_still_records_cost(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=_result(3))), \
         patch("app.rag.pipeline.stream_explanation", _one_delta):
        gen = pipeline.run_search_pipeline(
            query="q", collections=["bible"], translation="CPDV", quota=4, user_id=None,
        )
        async for event in gen:
            if event["type"] == "explanation_delta":
                break                      # client disconnects after one delta
        await gen.aclose()
    await _drain()

    (row,) = pool.rows()
    assert row["completed"] is False
    assert row["delivered"] == 3
    assert row["runner_cost"] == pytest.approx(0.0035)
    # Only the one explanation that ran before the stream closed.
    assert row["explanation_cost"] == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6)


@pytest.mark.asyncio
async def test_completed_search_records_once(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=_result(2))), \
         patch("app.rag.pipeline.stream_explanation", _one_delta):
        events = [e async for e in pipeline.run_search_pipeline(
            query="q", collections=["bible"], translation="CPDV", quota=4, user_id=None,
        )]
    await _drain()

    assert events[-1]["type"] == "explanation_delta"
    (row,) = pool.rows()
    assert row["completed"] is True
    assert row["explanation_cost"] == pytest.approx(2 * (1000 * 0.10 + 100 * 0.50) / 1e6)


@pytest.mark.asyncio
async def test_failed_runner_stage_records_what_it_had_spent(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    failure = PipelineExecutionError("rerank", {"hyde": 0.001, "rerank_cohere": 0.005}, True)
    with patch("app.rag.pipeline.run_pipeline", AsyncMock(side_effect=failure)):
        events = [e async for e in pipeline.run_search_pipeline(
            query="q", collections=["bible"], translation="CPDV", quota=4, user_id=None,
        )]
    await _drain()

    assert events[-1]["type"] == "error"
    (row,) = pool.rows()
    assert row["outcome"] == "stage_failed:rerank"
    assert row["completed"] is True
    assert row["runner_cost"] == pytest.approx(0.006)
    assert row["delivered"] == 0


@pytest.mark.asyncio
async def test_runner_stage_failure_carries_the_cost_so_far():
    from app.rag.pipelines import runner

    async def boom(*_a, **_kw):
        raise RuntimeError("qdrant down")

    async def hyde(query, collections, tracker, **_kw):
        tracker.record("hyde", "gpt-5.6-luna", input_tokens=1_000_000, output_tokens=0)
        return {}

    with patch("app.rag.steps.embed.run", AsyncMock(return_value=[0.1])), \
         patch("app.rag.steps.hyde_s25.run", hyde), \
         patch("app.rag.steps.retrieve_vector.run", boom):
        with pytest.raises(PipelineExecutionError) as caught:
            await runner.run(PIPELINES["hyde_cohere_luna"], "q", ["bible"], 4)

    assert caught.value.stage == "retrieve_vector"
    assert caught.value.cost_breakdown["hyde"] == pytest.approx(0.20)
