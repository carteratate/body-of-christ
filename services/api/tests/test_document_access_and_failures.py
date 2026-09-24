"""Reader access control and database-failure handling, against a fake pool."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.db import POOL_ACQUIRE_TIMEOUT_SECONDS
from app.models.auth import AuthUser
from app.routes import sources
from app.routes.documents import (
    get_document, get_document_reader, get_document_toc, require_document_access,
)
from app.routes.sources import get_sources
from tests.fake_pool import FakePool

DOC = "11111111-1111-1111-1111-111111111111"
USER = AuthUser(user_id="u", email=None)
GUEST_TOKEN = "g" * 40


def _request(guest_token: str | None = None) -> Request:
    headers = [] if guest_token is None else [(b"x-theocorpus-guest-token", guest_token.encode())]
    return Request({"type": "http", "headers": headers})


async def _status(call) -> int:
    with pytest.raises(HTTPException) as caught:
        await call
    return caught.value.status_code


# --- require_document_access ---------------------------------------------------

async def test_a_bearer_token_is_verified_and_skips_the_guest_check():
    pool = FakePool()
    with (
        patch("app.routes.documents.verify_supabase_jwt", new=AsyncMock()) as verify,
        patch("app.routes.documents.get_pool", return_value=pool),
    ):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="jwt")
        await require_document_access(DOC, _request(), credentials)

    verify.assert_awaited_once_with("jwt")
    assert pool.acquire_timeouts == []


@pytest.mark.parametrize("token", [None, "short"])
async def test_a_missing_or_malformed_guest_token_is_401(token):
    assert await _status(require_document_access(DOC, _request(token), None)) == 401


async def test_a_guest_with_a_bad_document_id_is_422():
    assert await _status(require_document_access("not-a-uuid", _request(GUEST_TOKEN), None)) == 422


@pytest.mark.parametrize(("allowed", "expected"), [(True, None), (False, 403)])
async def test_a_guest_reads_only_documents_their_session_retrieved(allowed, expected):
    pool = FakePool()
    pool.conn.fetchval.return_value = allowed
    with patch("app.routes.documents.get_pool", return_value=pool):
        if expected is None:
            await require_document_access(DOC, _request(GUEST_TOKEN), None)
        else:
            assert await _status(require_document_access(DOC, _request(GUEST_TOKEN), None)) == expected

    assert pool.acquire_timeouts == [POOL_ACQUIRE_TIMEOUT_SECONDS]
    assert pool.released == 1


@pytest.mark.parametrize("failure", ["acquire", "query"])
async def test_a_database_failure_in_the_guest_check_is_a_retryable_503(failure):
    if failure == "acquire":
        pool = FakePool(acquire_error=TimeoutError())
    else:
        pool = FakePool()
        pool.conn.fetchval.side_effect = ConnectionError("pooler reset")
    with patch("app.routes.documents.get_pool", return_value=pool):
        assert await _status(require_document_access(DOC, _request(GUEST_TOKEN), None)) == 503


# --- routes ------------------------------------------------------------------------

ROUTES = {
    "document": lambda: get_document(DOC, user=USER),
    "toc": lambda: get_document_toc(DOC, user=USER),
    "reader": lambda: get_document_reader(DOC, anchor=None, chapter=None, user=USER),
}


@pytest.mark.parametrize("route", sorted(ROUTES))
async def test_an_exhausted_pool_is_a_retryable_503(route):
    pool = FakePool(acquire_error=TimeoutError())
    with patch("app.routes.documents.get_pool", return_value=pool):
        assert await _status(ROUTES[route]()) == 503
    assert pool.acquire_timeouts == [POOL_ACQUIRE_TIMEOUT_SECONDS]


async def test_sources_on_an_exhausted_pool_is_a_retryable_503():
    pool = FakePool(acquire_error=TimeoutError())
    with (
        patch("app.routes.sources.get_pool", return_value=pool),
        patch.object(sources, "_sources_cache", None),
    ):
        assert await _status(get_sources(user=USER)) == 503


@pytest.mark.parametrize("route", sorted(ROUTES))
async def test_a_404_raised_mid_request_still_returns_the_connection(route):
    pool = FakePool()
    pool.conn.fetchrow.return_value = None  # the document does not exist
    with patch("app.routes.documents.get_pool", return_value=pool):
        assert await _status(ROUTES[route]()) == 404
    assert pool.released == 1
