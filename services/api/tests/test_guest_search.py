"""Tests for the /v1/search/guest endpoint."""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.routes.guest_search import TrialClaim, _get_client_ip, _hash_ip

CLAIM_ID = uuid.UUID("00000000-0000-0000-0000-000000000123")
ALLOWED_CLAIM = TrialClaim(allowed=True, claim_id=CLAIM_ID)
DENIED_CLAIM = TrialClaim(allowed=False, claim_id=None)


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

    mock_row = {"id": CLAIM_ID}
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=mock_pool):
        result = await _try_record_trial("somehash")

    assert result == ALLOWED_CLAIM
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

    assert result == DENIED_CLAIM


@pytest.mark.asyncio
async def test_trial_store_without_pool_fails_closed():
    from app.routes.guest_search import TrialStoreUnavailable, _try_record_trial

    with patch("app.routes.guest_search.get_pool", return_value=None), \
         pytest.raises(TrialStoreUnavailable):
        await _try_record_trial("somehash")


@pytest.mark.asyncio
async def test_trial_store_database_error_fails_closed():
    from app.routes.guest_search import TrialStoreUnavailable, _try_record_trial

    pool = MagicMock()
    pool.acquire.side_effect = RuntimeError("database unavailable")
    with patch("app.routes.guest_search.get_pool", return_value=pool), \
         pytest.raises(TrialStoreUnavailable):
        await _try_record_trial("somehash")


@pytest.mark.asyncio
async def test_refund_deletes_only_the_exact_claim():
    from app.routes.guest_search import _refund_trial

    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))

    with patch("app.routes.guest_search.get_pool", return_value=pool):
        await _refund_trial("somehash", CLAIM_ID)

    delete_call = conn.execute.await_args_list[1]
    assert "WHERE id = $1 AND ip_hash = $2" in delete_call.args[0]
    assert delete_call.args[1:] == (CLAIM_ID, "somehash")


@pytest.mark.asyncio
async def test_client_closing_guest_stream_does_not_refund_trial():
    from app.routes.guest_search import _stream_guest_events

    async def fake_pipeline(*args, **kwargs):
        yield {"type": "status", "phase": "searching"}
        await AsyncMock()()

    refund = AsyncMock()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._refund_trial", refund):
        stream = _stream_guest_events(
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            claim=ALLOWED_CLAIM,
        )
        await anext(stream)
        await stream.aclose()

    refund.assert_not_awaited()


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

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}, "quota": 3},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "chunk" in response.text


def test_guest_search_429_when_trial_exhausted(client):
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=DENIED_CLAIM)):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 429
    assert response.json()["detail"] == "trial_exhausted"


def test_guest_search_503_when_trial_store_unavailable(client):
    from app.routes.guest_search import TrialStoreUnavailable

    with patch(
        "app.routes.guest_search._try_record_trial",
        AsyncMock(side_effect=TrialStoreUnavailable),
    ):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Guest search is temporarily unavailable."


def test_guest_pipeline_failure_refunds_trial(client):
    async def fake_pipeline(*args, **kwargs):
        yield {"type": "error", "code": "retrieval_failed", "detail": "failed"}

    refund = AsyncMock()
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search._refund_trial", refund), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 200
    refund.assert_awaited_once_with(_hash_ip("testclient"), CLAIM_ID)


def test_guest_pipeline_success_keeps_trial_consumed(client):
    async def fake_pipeline(*args, **kwargs):
        yield {"type": "done", "search_id": None, "result_count": 0}

    refund = AsyncMock()
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search._refund_trial", refund), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 200
    refund.assert_not_awaited()


@pytest.mark.parametrize("collections", [[], ["not-a-real-collection"], ["bible", "fake"]])
def test_guest_search_rejects_invalid_collections_without_consuming_trial(client, collections):
    record_trial = AsyncMock(return_value=ALLOWED_CLAIM)
    with patch("app.routes.guest_search._try_record_trial", record_trial):
        response = client.post(
            "/v1/search/guest",
            json={"query": "test", "filters": {"collections": collections}},
        )

    assert response.status_code == 422
    record_trial.assert_not_awaited()


def test_guest_search_rejects_blank_query_without_consuming_trial(client):
    record_trial = AsyncMock(return_value=ALLOWED_CLAIM)
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

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
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

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        client.post(
            "/v1/search/guest",
            json={"query": "test", "filters": {"collections": ["bible"]}, "quota": 99},
        )

    assert captured.get("quota") == 3  # capped at _GUEST_QUOTA
