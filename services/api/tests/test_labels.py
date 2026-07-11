"""Security and data-integrity tests for POST /v1/labels."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.routes.labels import router


USER_ID = "00000000-0000-0000-0000-000000000001"
SEARCH_ID = "00000000-0000-0000-0000-000000000002"
CHUNK_ID = "00000000-0000-0000-0000-000000000003"
LABEL_ID = "00000000-0000-0000-0000-000000000004"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    async def user() -> AuthUser:
        return AuthUser(user_id=USER_ID)

    app.dependency_overrides[get_current_user] = user
    return app


def _pool(conn: AsyncMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = cm
    return pool


def _body(label: str = "up") -> dict[str, str]:
    return {"chunk_id": CHUNK_ID, "search_id": SEARCH_ID, "label": label}


def test_label_uses_canonical_persisted_rank():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[SEARCH_ID, 7])
    conn.fetchrow = AsyncMock(return_value={"id": LABEL_ID})

    with patch("app.routes.labels.get_pool", return_value=_pool(conn)):
        response = TestClient(_app()).post("/v1/labels", json=_body())

    assert response.status_code == 201
    assert response.json() == {"label_id": LABEL_ID}
    assert conn.fetchrow.await_args.args[-1] == 7


def test_client_cannot_spoof_rank():
    body = {**_body(), "rank": 99}
    response = TestClient(_app()).post("/v1/labels", json=body)
    assert response.status_code == 422


def test_invalid_chunk_uuid_is_rejected():
    response = TestClient(_app()).post("/v1/labels", json={**_body(), "chunk_id": "nope"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid chunk_id: must be a UUID"


def test_invalid_search_uuid_is_rejected():
    response = TestClient(_app()).post("/v1/labels", json={**_body(), "search_id": "nope"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid search_id: must be a UUID"


def test_foreign_or_missing_search_is_rejected():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    with patch("app.routes.labels.get_pool", return_value=_pool(conn)):
        response = TestClient(_app()).post("/v1/labels", json=_body())
    assert response.status_code == 404
    assert response.json()["detail"] == "Search not found"
    conn.fetchrow.assert_not_awaited()


def test_chunk_not_in_search_is_rejected():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[SEARCH_ID, None])
    with patch("app.routes.labels.get_pool", return_value=_pool(conn)):
        response = TestClient(_app()).post("/v1/labels", json=_body())
    assert response.status_code == 404
    assert response.json()["detail"] == "Retrieval not found"
    conn.fetchrow.assert_not_awaited()


def test_label_flip_uses_upsert_and_keeps_canonical_rank():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[SEARCH_ID, 2, SEARCH_ID, 2])
    conn.fetchrow = AsyncMock(return_value={"id": LABEL_ID})
    client = TestClient(_app())
    with patch("app.routes.labels.get_pool", return_value=_pool(conn)):
        first = client.post("/v1/labels", json=_body("up"))
        second = client.post("/v1/labels", json=_body("down"))
    assert first.status_code == second.status_code == 201
    assert conn.fetchrow.await_count == 2
    assert conn.fetchrow.await_args_list[0].args[-2:] == ("up", 2)
    assert conn.fetchrow.await_args_list[1].args[-2:] == ("down", 2)
    assert "ON CONFLICT ON CONSTRAINT retrieval_labels_user_chunk_search_unique" in conn.fetchrow.await_args_list[1].args[0]


def test_no_pool_returns_sanitized_503():
    with patch("app.routes.labels.get_pool", return_value=None):
        response = TestClient(_app()).post("/v1/labels", json=_body())
    assert response.status_code == 503
    assert response.json()["detail"] == "Service temporarily unavailable"


def test_database_error_returns_sanitized_503():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=Exception("password secret in DB failure"))
    with patch("app.routes.labels.get_pool", return_value=_pool(conn)):
        response = TestClient(_app(), raise_server_exceptions=False).post("/v1/labels", json=_body())
    assert response.status_code == 503
    assert response.json()["detail"] == "Service temporarily unavailable"
    assert "password" not in response.text
