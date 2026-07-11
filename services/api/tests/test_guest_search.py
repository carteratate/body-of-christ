"""Tests for the /v1/search/guest endpoint."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.routes.guest_search import _get_client_ip, _hash_ip


# ── Pure-function unit tests ──────────────────────────────────────────────────

def test_hash_ip_is_deterministic():
    assert _hash_ip("1.2.3.4") == _hash_ip("1.2.3.4")


def test_hash_ip_differs_for_different_ips():
    assert _hash_ip("1.2.3.4") != _hash_ip("5.6.7.8")


def test_hash_ip_is_64_hex_chars():
    # SHA-256 produces a 64-character hexdigest
    result = _hash_ip("1.2.3.4")
    assert len(result) == 64
    assert "1.2.3.4" not in result  # must not contain plaintext IP


def test_get_client_ip_accepts_app_header_from_authenticated_proxy():
    req = MagicMock()
    req.headers = {
        "x-theocorpus-client-ip": "10.0.0.1",
        "x-internal-secret": "proxy-secret",
    }
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    with patch("app.routes.guest_search.settings.internal_api_secret", "proxy-secret"):
        assert _get_client_ip(req) == "10.0.0.1"


def test_get_client_ip_ignores_spoofed_forwarding_headers():
    req = MagicMock()
    req.headers = {
        "x-forwarded-for": "10.0.0.1",
        "x-theocorpus-client-ip": "10.0.0.2",
        "x-internal-secret": "wrong-secret",
    }
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    with patch("app.routes.guest_search.settings.internal_api_secret", "proxy-secret"):
        assert _get_client_ip(req) == "127.0.0.1"


def test_get_client_ip_rejects_invalid_trusted_proxy_value():
    req = MagicMock()
    req.headers = {
        "x-theocorpus-client-ip": "not-an-ip",
        "x-internal-secret": "proxy-secret",
    }
    req.client = MagicMock(host="127.0.0.1")
    with patch("app.routes.guest_search.settings.internal_api_secret", "proxy-secret"):
        assert _get_client_ip(req) == "127.0.0.1"


def test_get_client_ip_falls_back_to_client_host():
    req = MagicMock()
    req.headers.get = lambda key, default=None: None
    req.client = MagicMock()
    req.client.host = "192.168.1.5"
    assert _get_client_ip(req) == "192.168.1.5"


# ── _try_record_trial unit tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trial_slot_taken():
    """DB returns a row → slot was successfully claimed → returns True."""
    from app.routes.guest_search import _try_record_trial

    mock_row = {"id": "some-uuid"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=mock_pool):
        result = await _try_record_trial("somehash")

    assert result is True
    lock_sql = mock_conn.execute.await_args.args[0]
    assert "pg_advisory_xact_lock" in lock_sql
    assert "hashtextextended" in lock_sql
    mock_conn.transaction.assert_called_once_with()


@pytest.mark.asyncio
async def test_trial_slot_exhausted():
    """DB returns None (INSERT skipped) → trial already used → returns False."""
    from app.routes.guest_search import _try_record_trial

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=mock_pool):
        result = await _try_record_trial("somehash")

    assert result is False


# ── Route-level integration tests ─────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


def test_guest_search_success_returns_sse(client):
    async def fake_pipeline(*args, **kwargs):
        yield {"type": "chunk", "chunk_id": "abc", "content": "test passage", "source": {
            "collection": "bible", "document_title": "Genesis", "author": "",
            "reference": "Gen 1:1", "document_id": "doc-1", "anchor": None,
        }, "reranker_score": 0.9}
        yield {"type": "done", "search_id": "search-1", "result_count": 1}

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=True)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}, "quota": 3},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "chunk" in response.text


def test_guest_search_429_when_trial_exhausted(client):
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=False)):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 429
    assert response.json()["detail"] == "trial_exhausted"


@pytest.mark.parametrize("collections", [[], ["not-a-real-collection"], ["bible", "fake"]])
def test_guest_search_rejects_invalid_collections_without_consuming_trial(client, collections):
    record_trial = AsyncMock(return_value=True)
    with patch("app.routes.guest_search._try_record_trial", record_trial):
        response = client.post(
            "/v1/search/guest",
            json={"query": "test", "filters": {"collections": collections}},
        )

    assert response.status_code == 422
    record_trial.assert_not_awaited()


def test_guest_search_rejects_blank_query_without_consuming_trial(client):
    record_trial = AsyncMock(return_value=True)
    with patch("app.routes.guest_search._try_record_trial", record_trial):
        response = client.post(
            "/v1/search/guest",
            json={"query": "   \t ", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 422
    record_trial.assert_not_awaited()


def test_guest_search_strips_query_before_pipeline(client):
    captured = {}

    async def fake_pipeline(**kwargs):
        captured.update(kwargs)
        yield {"type": "done", "search_id": "x", "result_count": 0}

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=True)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        response = client.post(
            "/v1/search/guest",
            json={"query": "  grace  ", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 200
    assert captured["query"] == "grace"


def test_guest_search_caps_quota_at_guest_maximum(client):
    captured = {}

    async def fake_pipeline(query, collections, translation, quota, user_id):
        captured["quota"] = quota
        yield {"type": "done", "search_id": "x", "result_count": 0}

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=True)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        client.post(
            "/v1/search/guest",
            json={"query": "test", "filters": {"collections": ["bible"]}, "quota": 99},
        )

    assert captured.get("quota") == 3  # capped at _GUEST_QUOTA
