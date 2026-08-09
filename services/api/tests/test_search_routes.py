"""Tests for search validation, history, restore, and deletion routes."""
import datetime
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
SEARCH_ID_2 = "00000000-0000-0000-0000-000000000010"
SEARCH_ID_3 = "00000000-0000-0000-0000-000000000011"


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


def test_search_history_returns_an_opaque_next_cursor():
    pool = AsyncMock()
    now = datetime.datetime(2026, 8, 4, 16, 0, tzinfo=datetime.timezone.utc)
    pool.fetch.return_value = [
        {"id": SEARCH_ID, "query": "grace", "filters": {}, "result_count": 3, "created_at": now},
        {"id": SEARCH_ID_2, "query": "hope", "filters": {}, "result_count": 2, "created_at": now - datetime.timedelta(minutes=1)},
        {"id": SEARCH_ID_3, "query": "charity", "filters": {}, "result_count": 1, "created_at": now - datetime.timedelta(minutes=2)},
    ]
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get("/v1/searches?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["searches"]] == [SEARCH_ID, SEARCH_ID_2]
    assert body["next_cursor"]
    assert pool.fetch.await_args.args[-1] == 3


def test_search_history_rejects_an_invalid_cursor_without_db_call():
    pool = AsyncMock()
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get("/v1/searches?cursor=not-a-valid-cursor")

    assert response.status_code == 422
    pool.fetch.assert_not_awaited()


def test_search_history_cursor_uses_timestamp_and_id_tie_breaker():
    pool = AsyncMock()
    same_time = datetime.datetime(2026, 8, 4, 16, 0, tzinfo=datetime.timezone.utc)
    pool.fetch.side_effect = [
        [
            {"id": SEARCH_ID_3, "query": "three", "filters": {}, "result_count": 1, "created_at": same_time},
            {"id": SEARCH_ID_2, "query": "two", "filters": {}, "result_count": 1, "created_at": same_time},
            {"id": SEARCH_ID, "query": "one", "filters": {}, "result_count": 1, "created_at": same_time},
        ],
        [
            {"id": SEARCH_ID, "query": "one", "filters": {}, "result_count": 1, "created_at": same_time},
        ],
    ]
    with patch("app.routes.search.get_pool", return_value=pool):
        first = _client().get("/v1/searches?limit=2").json()
        second = _client().get(f"/v1/searches?limit=2&cursor={first['next_cursor']}").json()

    assert [item["id"] for item in first["searches"]] == [SEARCH_ID_3, SEARCH_ID_2]
    assert [item["id"] for item in second["searches"]] == [SEARCH_ID]
    second_args = pool.fetch.await_args_list[1].args
    assert second_args[2] == same_time
    assert str(second_args[3]) == SEARCH_ID_2


def test_search_history_query_uses_literal_substring_matching():
    pool = AsyncMock()
    pool.fetch.return_value = []
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get("/v1/searches?q=%25_%5C")

    assert response.status_code == 200
    sql = pool.fetch.await_args.args[0]
    assert "strpos(lower(query), lower($4))" in sql
    assert pool.fetch.await_args.args[4] == "%_\\"


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
        "filters": {"collections": ["bible", "catechism"], "translation": "WEB-C", "quota": 5},
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
    assert body["filters"] == {"collections": ["bible", "catechism"], "translation": "WEB-C", "quota": 5}


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


def test_restore_preserves_document_author_on_result_cards():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        "id": SEARCH_ID,
        "query": "providence",
        "filters": {"collections": ["summa"]},
        "result_count": 1,
    }
    pool.fetch.return_value = [
        {
            "rank": 1,
            "reranker_score": 0.91,
            "explanation": "Directly relevant",
            "chunk_id": "00000000-0000-0000-0000-000000000012",
            "content": "All things are subject to divine providence.",
            "reference": "Summa Theologiae, First Part, Question 22, Article 2",
            "position": 1,
            "anchor": "summa-1-22-2",
            "chapter_key": "first-part-question-22",
            "collection": "summa",
            "document_title": "Summa Theologiae",
            "author": "Thomas Aquinas",
            "document_id": "00000000-0000-0000-0000-000000000013",
        }
    ]
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get(f"/v1/searches/{SEARCH_ID}/results")

    assert response.status_code == 200
    assert response.json()["results"][0]["source"]["author"] == "Thomas Aquinas"


def test_restore_timeout_returns_bounded_gateway_timeout():
    pool = AsyncMock()
    pool.fetchrow.side_effect = TimeoutError
    with patch("app.routes.search.get_pool", return_value=pool):
        response = _client().get(f"/v1/searches/{SEARCH_ID}/results")

    assert response.status_code == 504
    assert response.json()["detail"] == "Saved search took too long to load"
