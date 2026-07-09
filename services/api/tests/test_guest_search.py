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


def test_get_client_ip_prefers_x_forwarded_for():
    req = MagicMock()
    req.headers.get = lambda key, default=None: "10.0.0.1, 172.16.0.1" if key == "x-forwarded-for" else default
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    assert _get_client_ip(req) == "10.0.0.1"


def test_get_client_ip_strips_whitespace_from_xff():
    req = MagicMock()
    req.headers.get = lambda key, default=None: "  10.0.0.1  , 172.16.0.1" if key == "x-forwarded-for" else default
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    assert _get_client_ip(req) == "10.0.0.1"


def test_get_client_ip_falls_back_to_client_host():
    req = MagicMock()
    req.headers.get = lambda key, default=None: None
    req.client = MagicMock()
    req.client.host = "192.168.1.5"
    assert _get_client_ip(req) == "192.168.1.5"


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

    with patch("app.routes.guest_search._has_used_trial", AsyncMock(return_value=False)), \
         patch("app.routes.guest_search._record_trial", AsyncMock()), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}, "quota": 3},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "chunk" in response.text


def test_guest_search_429_when_trial_exhausted(client):
    with patch("app.routes.guest_search._has_used_trial", AsyncMock(return_value=True)):
        response = client.post(
            "/v1/search/guest",
            json={"query": "What is grace?", "filters": {"collections": ["bible"]}},
        )

    assert response.status_code == 429
    assert response.json()["detail"] == "trial_exhausted"


def test_guest_search_400_for_invalid_collections(client):
    with patch("app.routes.guest_search._has_used_trial", AsyncMock(return_value=False)), \
         patch("app.routes.guest_search._record_trial", AsyncMock()):
        response = client.post(
            "/v1/search/guest",
            json={"query": "test", "filters": {"collections": ["not-a-real-collection"]}},
        )

    assert response.status_code == 400


def test_guest_search_caps_quota_at_guest_maximum(client):
    captured = {}

    async def fake_pipeline(query, collections, translation, quota, user_id):
        captured["quota"] = quota
        yield {"type": "done", "search_id": "x", "result_count": 0}

    with patch("app.routes.guest_search._has_used_trial", AsyncMock(return_value=False)), \
         patch("app.routes.guest_search._record_trial", AsyncMock()), \
         patch("app.routes.guest_search.run_search_pipeline", fake_pipeline):
        client.post(
            "/v1/search/guest",
            json={"query": "test", "filters": {"collections": ["bible"]}, "quota": 99},
        )

    assert captured.get("quota") == 3  # capped at _GUEST_QUOTA
