"""Per-search cost persistence (`search_costs`, migration 0036)."""
from __future__ import annotations

import asyncio
import datetime
import uuid
from pathlib import Path

import pytest

from app.rag import pipeline
from app.rag.pipelines.registry import PIPELINES
from app.rag.search_plan import resolve_search_plan
from app.rag.steps.cost_tracker import PRICING_EFFECTIVE_DATE, CostTracker
from app.rag.steps.types import PipelineResult, StepTiming

_MIGRATION = Path(__file__).parents[3] / "supabase/migrations/0036_search_costs.sql"


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


def _result() -> PipelineResult:
    return PipelineResult(
        pipeline="hyde_cohere_luna", chunks=[], step_timings=[StepTiming("embed", 0.1)],
        total_duration_s=1.0,
        cost_breakdown={"hyde": 0.001, "rerank_cohere": 0.0025},
        total_cost=0.0035,
    )


async def _drain() -> None:
    await asyncio.gather(*list(pipeline._COST_WRITES))


@pytest.mark.asyncio
async def test_records_runner_and_explanation_cost_with_models(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)
    explanation = CostTracker()
    explanation.record("explain", "gpt-6-luna", input_tokens=1000, output_tokens=100)
    search_id = str(uuid.uuid4())

    pipeline._record_search_cost(
        search_id=search_id, user_id="user-1",
        plan=resolve_search_plan(["bible", "catechism"], 4),
        config=PIPELINES["hyde_cohere_luna"], pipeline_result=_result(),
        outcome="success", delivered=8, explanation_cost=explanation,
    )
    await _drain()

    (_sql, args, _kw), = pool.calls
    (sid, audience, name, outcome, n_cols, quota, focused, delivered,
     runner_cost, explain_cost, breakdown, eligible, pricing_date, models) = args
    assert sid == uuid.UUID(search_id)
    assert (audience, name, outcome, n_cols, quota, focused, delivered) == (
        "authenticated", "hyde_cohere_luna", "success", 2, 4, False, 8)
    assert runner_cost == pytest.approx(0.0035)
    assert explain_cost == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6)
    # jsonb goes in as objects: app/db.py's codec serialises once. A pre-dumped
    # string would store a jsonb *string* (the 0033 repair).
    assert isinstance(breakdown, dict) and isinstance(models, dict)
    assert set(breakdown) == {"hyde", "rerank_cohere", "explain"}
    assert eligible is True
    assert pricing_date == datetime.date.fromisoformat(PRICING_EFFECTIVE_DATE)
    assert models["rerank"] == "gpt-5.6-luna"
    assert models["rerank_reasoning_effort"] == "medium"
    assert models["explain"] == "gpt-6-luna"
    assert models["explain_reasoning_effort"] == "none"
    assert models["hyde_genre"] == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_guest_and_unpersisted_searches_record_without_a_search_id(monkeypatch):
    pool = _Pool()
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)

    pipeline._record_search_cost(
        search_id=None, user_id=None, plan=resolve_search_plan(["bible"], 10),
        config=PIPELINES["hyde_cohere_luna"], pipeline_result=_result(),
        outcome="no_candidates", delivered=0,
    )
    await _drain()

    args = pool.calls[0][1]
    assert args[0] is None
    assert args[1] == "guest"
    assert args[6] is True            # focused
    assert args[9] == 0.0             # no explanations ran


@pytest.mark.asyncio
async def test_write_failure_is_logged_not_raised(monkeypatch, caplog):
    # e.g. migration 0036 not applied yet when the API deploys.
    pool = _Pool(fail=RuntimeError('relation "search_costs" does not exist'))
    monkeypatch.setattr(pipeline, "get_pool", lambda: pool)

    pipeline._record_search_cost(
        search_id=None, user_id=None, plan=resolve_search_plan(["bible"], 4),
        config=PIPELINES["hyde_cohere_luna"], pipeline_result=_result(),
        outcome="success", delivered=4,
    )
    with caplog.at_level("WARNING"):
        await _drain()
    assert "search cost persist failed" in caplog.text


def test_no_pool_is_a_no_op(monkeypatch):
    monkeypatch.setattr(pipeline, "get_pool", lambda: None)
    pipeline._record_search_cost(
        search_id=None, user_id=None, plan=resolve_search_plan(["bible"], 4),
        config=PIPELINES["hyde_cohere_luna"], pipeline_result=_result(),
        outcome="success", delivered=4,
    )
    assert not pipeline._COST_WRITES


def test_migration_matches_the_insert_and_is_closed_to_the_data_api():
    sql = _MIGRATION.read_text()
    for column in (
        "search_id", "audience", "pipeline", "outcome", "collection_count", "quota",
        "focused", "delivered", "runner_cost", "explanation_cost", "cost_breakdown",
        "cost_eligible", "pricing_effective_date", "models",
    ):
        assert column in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON TABLE search_costs FROM PUBLIC, anon, authenticated" in sql
    assert "user_id" not in sql.split("CREATE TABLE")[1].split(");")[0]
