"""Tests that DB errors in sessions routes return a sanitized 503."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.routes.sessions import router
from app.deps.auth import get_current_user
from app.models.auth import AuthUser


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    async def _fake_user() -> AuthUser:
        return AuthUser(user_id="00000000-0000-0000-0000-000000000001")

    app.dependency_overrides[get_current_user] = _fake_user
    return app


def test_list_sessions_db_error_returns_503():
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=Exception("asyncpg: pool exhausted"))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routes.sessions.get_pool") as mock_get_pool:
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_cm
        mock_get_pool.return_value = mock_pool

        response = client.get("/v1/sessions")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "Service temporarily unavailable"
    assert "asyncpg" not in response.text


def test_list_sessions_no_pool_returns_503():
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    with patch("app.routes.sessions.get_pool", return_value=None):
        response = client.get("/v1/sessions")

    assert response.status_code == 503


def test_get_session_messages_db_error_returns_503():
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(side_effect=Exception("asyncpg: connection lost"))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routes.sessions.get_pool") as mock_get_pool:
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_cm
        mock_get_pool.return_value = mock_pool

        response = client.get("/v1/sessions/00000000-0000-0000-0000-000000000001/messages")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "Service temporarily unavailable"
    assert "asyncpg" not in response.text


def test_get_session_messages_404_not_swallowed():
    """Verify that the 404 for a missing session is not swallowed by the outer except Exception."""
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=None)  # session does not exist
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routes.sessions.get_pool") as mock_get_pool:
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_cm
        mock_get_pool.return_value = mock_pool

        response = client.get("/v1/sessions/00000000-0000-0000-0000-000000000001/messages")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
