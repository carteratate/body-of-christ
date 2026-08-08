import datetime
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.routes.reading_progress import router

USER_ID = "00000000-0000-0000-0000-000000000001"
DOC_ID = "00000000-0000-0000-0000-000000000002"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id=USER_ID)
    return TestClient(app)


def _progress_row():
    return {
        "document_id": DOC_ID,
        "chapter_key": "chapter-2",
        "chapter_label": "Chapter 2",
        "anchor": None,
        "updated_at": datetime.datetime(2026, 8, 4, tzinfo=datetime.timezone.utc),
        "collection": "catechism",
        "document_title": "Catechism",
        "author": None,
    }


def test_list_progress_is_owned_bounded_and_recent_first():
    pool = AsyncMock()
    pool.fetch.return_value = [_progress_row()]
    with patch("app.routes.reading_progress.get_pool", return_value=pool):
        response = _client().get("/v1/reading-progress?limit=5")

    assert response.status_code == 200
    assert response.json()["items"][0]["chapter_key"] == "chapter-2"
    sql, user_id, limit = pool.fetch.await_args.args
    assert "rp.user_id = $1" in sql
    assert "ORDER BY rp.updated_at DESC" in sql
    assert user_id == USER_ID
    assert limit == 5


def test_get_progress_rejects_invalid_document_id_without_db_call():
    pool = AsyncMock()
    with patch("app.routes.reading_progress.get_pool", return_value=pool):
        response = _client().get("/v1/reading-progress/not-a-uuid")

    assert response.status_code == 422
    pool.fetchrow.assert_not_awaited()


def test_put_progress_validates_chapter_and_anchor_relationship():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    with patch("app.routes.reading_progress.get_pool", return_value=pool):
        response = _client().put(
            f"/v1/reading-progress/{DOC_ID}",
            json={"chapter_key": "chapter-2", "anchor": "wrong-anchor"},
        )

    assert response.status_code == 404
    assert pool.fetchrow.await_count == 1
    assert "c.document_id = $1 AND c.chapter_key = $2" in pool.fetchrow.await_args.args[0]


def test_put_progress_upserts_for_authenticated_user():
    pool = AsyncMock()
    stored = _progress_row()
    pool.fetchrow.side_effect = [
        {"chapter_label": "Chapter 2"},
        {key: stored[key] for key in ("document_id", "chapter_key", "anchor", "updated_at")},
        {"collection": "catechism", "document_title": "Catechism", "author": None},
    ]
    with patch("app.routes.reading_progress.get_pool", return_value=pool):
        response = _client().put(
            f"/v1/reading-progress/{DOC_ID}",
            json={"chapter_key": "chapter-2"},
        )

    assert response.status_code == 200
    upsert = pool.fetchrow.await_args_list[1]
    assert "ON CONFLICT (user_id, document_id)" in upsert.args[0]
    assert upsert.args[1] == USER_ID
    assert str(upsert.args[2]) == DOC_ID
