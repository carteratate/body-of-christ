"""Focused tests for responsive bookmark mutations."""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.routes.bookmarks import _write_rate_timestamps, router


USER_ID = "00000000-0000-0000-0000-000000000001"
CHUNK_ID = "00000000-0000-0000-0000-000000000002"
BOOKMARK_ID = "00000000-0000-0000-0000-000000000003"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id=USER_ID)
    _write_rate_timestamps.clear()
    return TestClient(app)


def test_create_bookmark_uses_one_upsert_round_trip():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        "id": BOOKMARK_ID,
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    }
    with patch("app.routes.bookmarks.get_pool", return_value=pool):
        response = _client().post("/v1/bookmarks", json={"chunk_id": CHUNK_ID})

    assert response.status_code == 201
    assert pool.fetchrow.await_count == 1
    assert "ON CONFLICT (user_id, chunk_id)" in pool.fetchrow.await_args.args[0]
    assert "DO UPDATE" in pool.fetchrow.await_args.args[0]


def test_create_bookmark_maps_missing_chunk_to_404():
    class ForeignKeyViolationError(Exception):
        pass

    pool = AsyncMock()
    pool.fetchrow.side_effect = ForeignKeyViolationError()
    with patch("app.routes.bookmarks.get_pool", return_value=pool):
        response = _client().post("/v1/bookmarks", json={"chunk_id": CHUNK_ID})

    assert response.status_code == 404
    assert response.json()["detail"] == "Chunk not found"


def test_create_bookmark_rejects_invalid_uuid_without_db_call():
    pool = AsyncMock()
    with patch("app.routes.bookmarks.get_pool", return_value=pool):
        response = _client().post("/v1/bookmarks", json={"chunk_id": "bad"})

    assert response.status_code == 422
    pool.fetchrow.assert_not_awaited()


def test_list_bookmarks_queries_each_request_and_has_deterministic_newest_order():
    pool = AsyncMock()
    pool.fetch.return_value = []
    with patch("app.routes.bookmarks.get_pool", return_value=pool):
        client = _client()
        first = client.get("/v1/bookmarks")
        second = client.get("/v1/bookmarks")

    assert first.status_code == 200
    assert second.status_code == 200
    assert pool.fetch.await_count == 2
    assert "ORDER BY b.created_at DESC, b.id DESC" in pool.fetch.await_args.args[0]
