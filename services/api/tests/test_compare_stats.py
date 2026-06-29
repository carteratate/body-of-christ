# services/api/tests/test_compare_stats.py
"""Tests for compare run persistence (save_compare_runs) and stats endpoint."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# save_compare_runs tests
# ---------------------------------------------------------------------------

def _make_pipeline_result(pipeline: str = "s2_5_haiku"):
    """Build a minimal PipelineResult-like object for mocking."""
    from app.rag.steps.types import PipelineResult, RankedChunk, StepTiming

    chunk = RankedChunk(
        chunk_id="c1",
        content="test content",
        reference="CCC 1",
        collection="catechism",
        document_id="d1",
        document_title="Catechism",
        author=None,
        reranker_score=0.9,
    )
    return PipelineResult(
        pipeline=pipeline,
        chunks=[chunk],
        step_timings=[StepTiming(step="hyde", duration_s=0.5)],
        total_duration_s=1.2,
        cost_breakdown={"haiku": 0.0001},
        total_cost=0.0001,
    )


@pytest.mark.asyncio
async def test_save_compare_runs_inserts_rows():
    """save_compare_runs calls executemany with one row per pipeline result."""
    from app.rag.compare.persist import save_compare_runs

    mock_conn = AsyncMock()
    mock_conn.executemany = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    results = [_make_pipeline_result("s2_5_haiku"), _make_pipeline_result("s4_haiku")]

    with patch("app.rag.compare.persist.get_pool", return_value=mock_pool):
        await save_compare_runs("test query", ["catechism"], 4, results)

    mock_conn.executemany.assert_called_once()
    call_args = mock_conn.executemany.call_args
    rows = call_args[0][1]  # second positional arg is the list of rows
    assert len(rows) == 2
    # First row should be for s2_5_haiku
    assert rows[0][3] == "s2_5_haiku"
    assert rows[1][3] == "s4_haiku"
    # chunk_count should be 1 for each (one chunk per result)
    assert rows[0][6] == 1
    assert rows[1][6] == 1


@pytest.mark.asyncio
async def test_save_compare_runs_skips_when_pool_none():
    """save_compare_runs returns silently when pool is unavailable."""
    from app.rag.compare.persist import save_compare_runs

    results = [_make_pipeline_result()]
    with patch("app.rag.compare.persist.get_pool", return_value=None):
        # Should not raise
        await save_compare_runs("query", ["bible"], 4, results)


@pytest.mark.asyncio
async def test_save_compare_runs_logs_error_on_db_failure():
    """save_compare_runs swallows DB errors and logs them instead of raising."""
    from app.rag.compare.persist import save_compare_runs

    mock_conn = AsyncMock()
    mock_conn.executemany = AsyncMock(side_effect=Exception("DB connection reset"))

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    results = [_make_pipeline_result()]

    with patch("app.rag.compare.persist.get_pool", return_value=mock_pool):
        # Must not raise
        await save_compare_runs("query", ["bible"], 4, results)


# ---------------------------------------------------------------------------
# compare stats endpoint tests
# ---------------------------------------------------------------------------

def test_stats_endpoint_returns_empty_when_no_runs(monkeypatch):
    """GET /v1/search/compare/stats returns empty pipelines list when table is empty."""
    monkeypatch.setenv("APP_ENV", "development")

    from app.main import app

    client = TestClient(app)

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    with patch("app.routes.compare_stats.get_pool", return_value=mock_pool), \
         patch("app.deps.auth.verify_supabase_jwt", new_callable=AsyncMock) as mock_verify:
        from app.models.auth import AuthUser
        mock_verify.return_value = AuthUser(user_id="u1")
        response = client.get(
            "/v1/search/compare/stats",
            headers={"x-internal-secret": "test", "Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 200
    assert response.json()["pipelines"] == []


def test_stats_endpoint_no_pool_returns_empty(monkeypatch):
    """GET /v1/search/compare/stats returns empty pipelines list when pool is None."""
    monkeypatch.setenv("APP_ENV", "development")

    from app.main import app

    client = TestClient(app)

    with patch("app.routes.compare_stats.get_pool", return_value=None), \
         patch("app.deps.auth.verify_supabase_jwt", new_callable=AsyncMock) as mock_verify:
        from app.models.auth import AuthUser
        mock_verify.return_value = AuthUser(user_id="u1")
        response = client.get(
            "/v1/search/compare/stats",
            headers={"x-internal-secret": "test", "Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"pipelines": []}


def test_stats_endpoint_requires_auth(monkeypatch):
    """GET /v1/search/compare/stats returns 401 without auth token."""
    monkeypatch.setenv("APP_ENV", "production")

    from app.main import app

    client = TestClient(app)

    response = client.get(
        "/v1/search/compare/stats",
        headers={"x-internal-secret": "test"},
    )
    assert response.status_code == 401


def test_stats_html_viewer_contains_stats_button(monkeypatch):
    """GET /v1/search/compare/view HTML contains the Stats button."""
    monkeypatch.setenv("APP_ENV", "development")

    from app.main import app

    client = TestClient(app)
    response = client.get(
        "/v1/search/compare/view",
        headers={"x-internal-secret": "test"},
    )
    assert response.status_code == 200
    assert "Stats" in response.text
    assert "loadStats" in response.text
