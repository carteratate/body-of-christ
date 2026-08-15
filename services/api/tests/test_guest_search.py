"""Tests for the /v1/search/guest endpoint."""
import asyncio
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.models.auth import AuthUser
from app.routes.guest_search import ClaimGuestSessionRequest, TrialClaim, _get_client_ip, _hash_ip

CLAIM_ID = uuid.UUID("00000000-0000-0000-0000-000000000123")
ALLOWED_CLAIM = TrialClaim(allowed=True, claim_id=CLAIM_ID)
DENIED_CLAIM = TrialClaim(allowed=False, claim_id=None)
GUEST_TOKEN = "guest-session-token-with-at-least-32-characters"


# ── Pure-function unit tests ──────────────────────────────────────────────────

def test_hash_ip_is_deterministic():
    assert _hash_ip("1.2.3.4") == _hash_ip("1.2.3.4")


def test_hash_ip_differs_for_different_ips():
    assert _hash_ip("1.2.3.4") != _hash_ip("5.6.7.8")


def test_hash_ip_groups_ipv6_hosts_within_same_64_prefix():
    assert _hash_ip("2001:db8:abcd:1234::1") == _hash_ip("2001:db8:abcd:1234::ffff")


def test_hash_ip_separates_different_ipv6_64_prefixes():
    assert _hash_ip("2001:db8:abcd:1234::1") != _hash_ip("2001:db8:abcd:1235::1")


def test_hash_ip_is_64_hex_chars():
    # HMAC-SHA-256 produces a 64-character hexdigest.
    result = _hash_ip("1.2.3.4")
    assert len(result) == 64
    assert "1.2.3.4" not in result  # must not contain plaintext IP


def test_hash_ip_changes_when_server_secret_changes():
    with patch("app.routes.guest_search.settings.guest_ip_hash_secret", "secret-a"):
        first = _hash_ip("1.2.3.4")
    with patch("app.routes.guest_search.settings.guest_ip_hash_secret", "secret-b"):
        second = _hash_ip("1.2.3.4")
    assert first != second


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
        result = await _try_record_trial("somehash", _hash_ip(GUEST_TOKEN))

    assert result == ALLOWED_CLAIM
    assert mock_conn.fetchrow.await_args.args[3:] == (2, 2)
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
        result = await _try_record_trial("somehash", _hash_ip(GUEST_TOKEN))

    assert result == DENIED_CLAIM


@pytest.mark.asyncio
async def test_trial_store_without_pool_fails_closed():
    from app.routes.guest_search import TrialStoreUnavailable, _try_record_trial

    with patch("app.routes.guest_search.get_pool", return_value=None), \
         pytest.raises(TrialStoreUnavailable):
        await _try_record_trial("somehash", _hash_ip(GUEST_TOKEN))


@pytest.mark.asyncio
async def test_trial_store_database_error_fails_closed():
    from app.routes.guest_search import TrialStoreUnavailable, _try_record_trial

    pool = MagicMock()
    pool.acquire.side_effect = RuntimeError("database unavailable")
    with patch("app.routes.guest_search.get_pool", return_value=pool), \
         pytest.raises(TrialStoreUnavailable):
        await _try_record_trial("somehash", _hash_ip(GUEST_TOKEN))


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
async def test_client_closing_guest_stream_still_finalizes_for_transfer():
    from app.routes.guest_search import _stream_guest_events

    async def fake_pipeline(*args, **kwargs):
        yield {"type": "status", "phase": "searching"}
        await asyncio.sleep(0)
        yield {"type": "done", "search_id": None, "result_count": 0}

    refund = AsyncMock()
    persist = AsyncMock()
    finalize = AsyncMock()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._refund_trial", refund), \
         patch("app.routes.guest_search._persist_guest_results", persist), \
         patch("app.routes.guest_search._finalize_guest_results", finalize):
        stream = _stream_guest_events(
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            session_token_hash="sessionhash",
            claim=ALLOWED_CLAIM,
        )
        await anext(stream)
        await stream.aclose()
        for _ in range(10):
            if finalize.await_count:
                break
            await asyncio.sleep(0)

    refund.assert_not_awaited()
    persist.assert_awaited_once()
    finalize.assert_awaited_once_with(CLAIM_ID, "sessionhash", {})


@pytest.mark.asyncio
async def test_finalize_failure_never_emits_done_or_loses_failure_signal():
    from app.routes.guest_search import _produce_guest_events

    async def fake_pipeline(*args, **kwargs):
        yield {"type": "done", "search_id": None, "result_count": 0}

    queue = asyncio.Queue()
    refund = AsyncMock()
    mark_failed = AsyncMock()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock(side_effect=RuntimeError("db unavailable"))), \
         patch("app.routes.guest_search._mark_guest_transfer_failed", mark_failed), \
         patch("app.routes.guest_search._refund_trial", refund):
        await _produce_guest_events(
            queue,
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            session_token_hash="sessionhash",
            claim=ALLOWED_CLAIM,
        )

    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    assert not any(isinstance(item, str) and '"type": "done"' in item for item in items)
    assert any(isinstance(item, RuntimeError) for item in items)
    refund.assert_not_awaited()
    mark_failed.assert_awaited_once_with(CLAIM_ID, "sessionhash")


@pytest.mark.asyncio
async def test_double_database_failure_keeps_persisted_trial_instead_of_refunding():
    from app.routes.guest_search import _produce_guest_events

    async def fake_pipeline(*args, **kwargs):
        yield {"type": "done", "search_id": None, "result_count": 0}

    queue = asyncio.Queue()
    persist = AsyncMock()
    refund = AsyncMock()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", persist), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock(side_effect=RuntimeError("db unavailable"))), \
         patch("app.routes.guest_search._mark_guest_transfer_failed", AsyncMock(side_effect=RuntimeError("still unavailable"))), \
         patch("app.routes.guest_search._refund_trial", refund):
        await _produce_guest_events(
            queue,
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            session_token_hash="sessionhash",
            claim=ALLOWED_CLAIM,
        )

    persist.assert_awaited_once()
    refund.assert_not_awaited()
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    assert any(isinstance(item, str) and '"type": "results_ready"' in item for item in items)
    assert not any(isinstance(item, str) and '"type": "done"' in item for item in items)


@pytest.mark.asyncio
async def test_producer_that_loses_transfer_ownership_does_not_emit_done():
    from app.routes.guest_search import GuestTransferOwnershipLost, _produce_guest_events

    async def fake_pipeline(*args, **kwargs):
        yield {"type": "done", "search_id": None, "result_count": 0}

    queue = asyncio.Queue()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock(side_effect=GuestTransferOwnershipLost)):
        await _produce_guest_events(
            queue,
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            session_token_hash="sessionhash",
            claim=ALLOWED_CLAIM,
        )

    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    assert any(isinstance(item, str) and '"type": "results_ready"' in item for item in items)
    assert not any(isinstance(item, str) and '"type": "done"' in item for item in items)
    assert not any(isinstance(item, Exception) for item in items)


@pytest.mark.asyncio
async def test_results_ready_is_emitted_before_explanations_finish():
    from app.routes.guest_search import _produce_guest_events

    explanations_blocked = asyncio.Event()
    release_explanations = asyncio.Event()
    chunk_id = "00000000-0000-0000-0000-000000000456"

    async def fake_pipeline(*args, **kwargs):
        yield {"type": "chunk", "chunk_id": chunk_id}
        yield {"type": "done", "search_id": None, "result_count": 1}
        explanations_blocked.set()
        await release_explanations.wait()
        yield {"type": "explanation_delta", "chunk_id": chunk_id, "delta": "Relevant"}

    queue = asyncio.Queue()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock()):
        task = asyncio.create_task(_produce_guest_events(
            queue,
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            session_token_hash="sessionhash",
            claim=ALLOWED_CLAIM,
        ))
        first = await queue.get()
        second = await queue.get()
        await explanations_blocked.wait()
        assert '"type": "chunk"' in first
        assert '"type": "results_ready"' in second
        assert not task.done()
        release_explanations.set()
        await task

    remaining = []
    while not queue.empty():
        remaining.append(queue.get_nowait())
    assert any(isinstance(item, str) and '"type": "done"' in item for item in remaining)


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted_before_cancel", [False, True])
async def test_cancelled_producer_refunds_pre_and_post_persist_reservations(persisted_before_cancel):
    from app.routes.guest_search import _produce_guest_events

    reached_wait = asyncio.Event()

    async def fake_pipeline(*args, **kwargs):
        if persisted_before_cancel:
            yield {"type": "done", "search_id": None, "result_count": 0}
        else:
            yield {"type": "status", "phase": "searching"}
        reached_wait.set()
        await asyncio.Event().wait()

    refund = AsyncMock()
    mark_failed = AsyncMock()
    with patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._mark_guest_transfer_failed", mark_failed), \
         patch("app.routes.guest_search._refund_trial", refund):
        task = asyncio.create_task(_produce_guest_events(
            asyncio.Queue(),
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
            ip_hash="somehash",
            session_token_hash="sessionhash",
            claim=ALLOWED_CLAIM,
        ))
        await reached_wait.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    if persisted_before_cancel:
        refund.assert_not_awaited()
        mark_failed.assert_awaited_once_with(CLAIM_ID, "sessionhash")
    else:
        refund.assert_awaited_once_with("somehash", CLAIM_ID)
        mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_guest_results_sets_ready_only_after_explanations():
    from app.routes.guest_search import _finalize_guest_results

    conn = AsyncMock()
    operations = []
    conn.execute.side_effect = lambda *args: operations.append(("execute", args[0]))
    conn.executemany.side_effect = lambda *args: operations.append(("executemany", args[0]))
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
    chunk_id = uuid.UUID("00000000-0000-0000-0000-000000000456")

    with patch("app.routes.guest_search.get_pool", return_value=pool):
        await _finalize_guest_results(CLAIM_ID, "sessionhash", {str(chunk_id): "Complete explanation"})

    assert "guest-session:sessionhash" in conn.execute.await_args_list[0].args
    conn.executemany.assert_awaited_once()
    assert "transfer_ready_at=now()" in conn.execute.await_args_list[-1].args[0]
    # The ready marker is issued after the explanation write inside one transaction.
    assert operations[-2][0] == "executemany"
    assert "transfer_ready_at=now()" in operations[-1][1]


@pytest.mark.asyncio
async def test_base_result_persistence_durably_marks_pending_before_display():
    from app.routes.guest_search import _persist_guest_results

    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=pool):
        await _persist_guest_results(CLAIM_ID, "grace", ["bible"], "CPDV", 3, [], {})

    sql = conn.execute.await_args.args[0]
    assert "transfer_pending_at=now()" in sql
    assert "transfer_lease_until=now() + interval '90 seconds'" in sql


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
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock()):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "What is grace?", "filters": {"collections": ["bible"]}, "quota": 3},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "chunk" in response.text


def test_guest_search_429_when_trial_exhausted(client):
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=DENIED_CLAIM)):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "What is grace?", "filters": {"collections": ["bible"]}},
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
            json={"session_token": GUEST_TOKEN, "query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Guest search is temporarily unavailable."


def test_guest_pipeline_failure_refunds_trial(client):
    async def fake_pipeline(*args, **kwargs):
        yield {"type": "error", "code": "retrieval_failed", "detail": "failed"}

    refund = AsyncMock()
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search._refund_trial", refund), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock()):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 200
    refund.assert_awaited_once_with(_hash_ip("testclient"), CLAIM_ID)


def test_guest_pipeline_success_keeps_trial_consumed(client):
    async def fake_pipeline(*args, **kwargs):
        yield {"type": "done", "search_id": None, "result_count": 0}

    refund = AsyncMock()
    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search._refund_trial", refund), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock()):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 200
    refund.assert_not_awaited()


@pytest.mark.parametrize("collections", [[], ["not-a-real-collection"], ["bible", "fake"]])
def test_guest_search_rejects_invalid_collections_without_consuming_trial(client, collections):
    record_trial = AsyncMock(return_value=ALLOWED_CLAIM)
    with patch("app.routes.guest_search._try_record_trial", record_trial):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "test", "filters": {"collections": collections}},
        )

    assert response.status_code == 422
    record_trial.assert_not_awaited()


def test_guest_search_rejects_blank_query_without_consuming_trial(client):
    record_trial = AsyncMock(return_value=ALLOWED_CLAIM)
    with patch("app.routes.guest_search._try_record_trial", record_trial):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "   \t ", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 422
    record_trial.assert_not_awaited()


def test_guest_search_strips_query_before_pipeline(client):
    captured = {}

    async def fake_pipeline(**kwargs):
        captured.update(kwargs)
        yield {"type": "done", "search_id": "x", "result_count": 0}

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock()):
        response = client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "  grace  ", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 200
    assert captured["query"] == "grace"


def test_guest_search_caps_quota_at_guest_maximum(client):
    captured = {}

    async def fake_pipeline(query, collections, translation, quota, user_id):
        captured["quota"] = quota
        yield {"type": "done", "search_id": "x", "result_count": 0}

    with patch("app.routes.guest_search._try_record_trial", AsyncMock(return_value=ALLOWED_CLAIM)), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline), \
         patch("app.routes.guest_search._persist_guest_results", AsyncMock()), \
         patch("app.routes.guest_search._finalize_guest_results", AsyncMock()):
        client.post(
            "/v1/search/guest",
            json={"session_token": GUEST_TOKEN, "query": "test", "filters": {"collections": ["bible"]}, "quota": 99},
        )

    assert captured.get("quota") == 3  # capped at _GUEST_QUOTA


@pytest.mark.asyncio
async def test_claim_waits_until_guest_search_is_transfer_ready():
    from app.routes.guest_search import claim_guest_session

    conn = AsyncMock()
    conn.fetchval.side_effect = [True, True]
    conn.fetch.return_value = []
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=pool), \
         pytest.raises(HTTPException) as exc:
        await claim_guest_session(
            ClaimGuestSessionRequest(session_token=GUEST_TOKEN),
            AuthUser(user_id="00000000-0000-0000-0000-000000000789"),
        )

    assert exc.value.status_code == 409
    assert "transfer_ready_at IS NULL" in conn.fetchval.await_args.args[0]
    conn.fetch.assert_awaited_once()  # checks for a recoverable failed finalization


@pytest.mark.asyncio
async def test_claim_imports_only_transfer_ready_searches_and_their_saved_chunks():
    from app.routes.guest_search import claim_guest_session

    trial_id = uuid.UUID("00000000-0000-0000-0000-000000000321")
    chunk_id = uuid.UUID("00000000-0000-0000-0000-000000000654")
    conn = AsyncMock()
    conn.fetchval.return_value = False
    conn.fetch.side_effect = [
        [{
            "id": trial_id,
            "query": "What is grace?",
            "filters": {"collections": ["bible"], "translation": "CPDV", "quota": 3},
            "result_count": 1,
            "created_at": "2026-08-13T12:00:00Z",
        }],
        [{"chunk_id": chunk_id, "rank": 1, "reranker_score": 0.9, "explanation": "Relevant"}],
    ]
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=pool):
        result = await claim_guest_session(
            ClaimGuestSessionRequest(session_token=GUEST_TOKEN, saved_chunk_ids=[chunk_id]),
            AuthUser(user_id="00000000-0000-0000-0000-000000000789"),
        )

    assert result.searches_imported == 1
    assert result.passages_saved == 1
    assert "transfer_ready_at IS NOT NULL" in conn.fetch.await_args_list[0].args[0]
    assert any("INSERT INTO bookmarks" in call.args[0] for call in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_claim_recovers_displayed_search_after_finalization_failure():
    from app.routes.guest_search import claim_guest_session

    trial_id = uuid.UUID("00000000-0000-0000-0000-000000000321")
    chunk_id = uuid.UUID("00000000-0000-0000-0000-000000000654")
    trial = {
        "id": trial_id,
        "query": "What is grace?",
        "filters": {"collections": ["bible"], "translation": "CPDV", "quota": 3},
        "result_count": 1,
        "created_at": "2026-08-13T12:00:00Z",
    }
    conn = AsyncMock()
    conn.fetchval.side_effect = [True, False]
    conn.fetch.side_effect = [
        [{"id": trial_id}],
        [trial],
        [{"chunk_id": chunk_id, "rank": 1, "reranker_score": 0.9, "explanation": "Explanation unavailable — please read the passage directly."}],
    ]
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))

    with patch("app.routes.guest_search.get_pool", return_value=pool):
        result = await claim_guest_session(
            ClaimGuestSessionRequest(session_token=GUEST_TOKEN, saved_chunk_ids=[chunk_id]),
            AuthUser(user_id="00000000-0000-0000-0000-000000000789"),
        )

    assert result.searches_imported == 1
    assert result.passages_saved == 1
    executed_sql = [call.args[0] for call in conn.execute.await_args_list]
    assert "transfer_lease_until < now()" in conn.fetch.await_args_list[0].args[0]
    assert any("Explanation unavailable" in sql for sql in executed_sql)
    assert any("SET transfer_ready_at=now()" in sql for sql in executed_sql)
