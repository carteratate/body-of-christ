"""Tests for _validate_collections dependency and delete endpoint in search routes."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.search import SearchFilters, SearchRequest
from app.rag.constants import VALID_COLLECTIONS
from app.routes.search import _validate_collections, router

USER_ID = "00000000-0000-0000-0000-000000000001"
SEARCH_ID = "00000000-0000-0000-0000-000000000009"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id=USER_ID)
    return TestClient(app)


@pytest.mark.asyncio
async def test_validate_collections_returns_valid_subset():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=["bible", "not-a-collection"], translation="CPDV"),
        quota=3,
    )
    result = await _validate_collections(body)
    assert result == ["bible"]


@pytest.mark.asyncio
async def test_validate_collections_raises_400_when_all_invalid():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=["not-a-collection", "also-invalid"], translation="CPDV"),
        quota=3,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate_collections(body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_collections_raises_400_when_empty():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=[], translation="CPDV"),
        quota=3,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate_collections(body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_collections_accepts_all_valid():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(
            collections=list(VALID_COLLECTIONS),
            translation="CPDV",
        ),
        quota=3,
    )
    result = await _validate_collections(body)
    assert set(result) == set(VALID_COLLECTIONS)


def test_delete_search_returns_204_on_success():
    pool = AsyncMock()
    pool.execute.return_value = "DELETE 1"
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().delete(f"/v1/searches/{SEARCH_ID}")

    assert response.status_code == 204
    assert "WHERE id = $1 AND user_id = $2" in pool.execute.await_args.args[0]


def test_delete_search_missing_row_returns_404():
    pool = AsyncMock()
    pool.execute.return_value = "DELETE 0"
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().delete(f"/v1/searches/{SEARCH_ID}")

    assert response.status_code == 404


def test_delete_search_rejects_invalid_uuid_without_db_call():
    pool = AsyncMock()
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().delete("/v1/searches/not-a-uuid")

    assert response.status_code == 422
    pool.execute.assert_not_awaited()


def test_restore_reports_missing_historical_results():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        "id": SEARCH_ID,
        "query": "grace",
        "result_count": 3,
    }
    pool.fetch.return_value = []
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get(f"/v1/searches/{SEARCH_ID}/results")

    assert response.status_code == 200
    body = response.json()
    assert body["restore_status"] == "results_unavailable"
    assert body["expected_result_count"] == 3
    assert body["results"] == []


def test_restore_of_genuine_empty_search_is_complete():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        "id": SEARCH_ID,
        "query": "grace",
        "result_count": 0,
    }
    pool.fetch.return_value = []
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get(f"/v1/searches/{SEARCH_ID}/results")

    assert response.status_code == 200
    body = response.json()
    assert body["restore_status"] == "complete"
    assert body["expected_result_count"] == 0
