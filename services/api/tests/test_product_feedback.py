"""Security, validation, and shared rate-limit tests for product feedback."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.routes.product_feedback import router

USER_ID = "00000000-0000-0000-0000-000000000001"
SEARCH_ID = "00000000-0000-0000-0000-000000000002"
CHUNK_ID = "00000000-0000-0000-0000-000000000003"
DOC_ID = "00000000-0000-0000-0000-000000000004"
FEEDBACK_ID = "00000000-0000-0000-0000-000000000005"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id=USER_ID)
    return TestClient(app)


def _pool(conn: AsyncMock) -> MagicMock:
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction)
    acquired = MagicMock()
    acquired.__aenter__ = AsyncMock(return_value=conn)
    acquired.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = acquired
    return pool


def _body(**updates) -> dict:
    return {
        "category": "bug",
        "message": "The reader stopped responding after I changed chapters.",
        "contact_allowed": False,
        "route": "/reader",
        **updates,
    }


def test_feedback_is_rate_limited_atomically_and_stores_normalized_context():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[0, 1, 1, uuid.UUID(DOC_ID)])
    conn.fetchrow = AsyncMock(return_value={"id": FEEDBACK_ID})
    with patch("app.routes.product_feedback.get_pool", return_value=_pool(conn)):
        response = _client().post(
            "/v1/product-feedback",
            json=_body(search_id=SEARCH_ID, chunk_id=CHUNK_ID, document_id=DOC_ID),
            headers={
                "user-agent": "Vercel proxy runtime",
                "x-theocorpus-user-agent": "Mozilla/5.0 Edg/126.0",
            },
        )

    assert response.status_code == 201
    assert response.json() == {"feedback_id": FEEDBACK_ID}
    assert "pg_advisory_xact_lock" in conn.execute.await_args.args[0]
    insert_args = conn.fetchrow.await_args.args
    assert insert_args[5] == "/reader"
    assert insert_args[8] == "edge"
    assert insert_args[9:12] == (
        uuid.UUID(SEARCH_ID),
        uuid.UUID(CHUNK_ID),
        uuid.UUID(DOC_ID),
    )


def test_feedback_rejects_foreign_search_context():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[0, None])
    with patch("app.routes.product_feedback.get_pool", return_value=_pool(conn)):
        response = _client().post("/v1/product-feedback", json=_body(search_id=SEARCH_ID))
    assert response.status_code == 404
    assert response.json()["detail"] == "Feedback context not found"
    conn.fetchrow.assert_not_awaited()


def test_feedback_rejects_chunk_not_returned_by_search():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[0, 1, None])
    with patch("app.routes.product_feedback.get_pool", return_value=_pool(conn)):
        response = _client().post(
            "/v1/product-feedback",
            json=_body(search_id=SEARCH_ID, chunk_id=CHUNK_ID),
        )
    assert response.status_code == 404
    conn.fetchrow.assert_not_awaited()


def test_feedback_rejects_invalid_ids_routes_and_blank_messages_before_insert():
    client = _client()
    assert client.post("/v1/product-feedback", json=_body(search_id="not-a-uuid")).status_code == 422
    assert client.post("/v1/product-feedback", json=_body(route="https://evil.example")).status_code == 422
    assert client.post("/v1/product-feedback", json=_body(message="           ")).status_code == 422


def test_feedback_uses_shared_database_rate_limit():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=5)
    with patch("app.routes.product_feedback.get_pool", return_value=_pool(conn)):
        response = _client().post("/v1/product-feedback", json=_body())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "600"
    conn.fetchrow.assert_not_awaited()


def test_feedback_database_error_is_sanitized():
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=Exception("database password leaked"))
    with patch("app.routes.product_feedback.get_pool", return_value=_pool(conn)):
        response = _client().post("/v1/product-feedback", json=_body())
    assert response.status_code == 503
    assert response.json()["detail"] == "Service temporarily unavailable"
    assert "password" not in response.text
