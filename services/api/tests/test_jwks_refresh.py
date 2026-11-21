"""JWKS cache refresh.

The lock is held across the fetch, so concurrent requests that find the cache stale
share one fetch to Supabase instead of each making their own.
"""

import asyncio
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import jwks
from app.auth.verify import verify_supabase_jwt
from app.config import settings

CONCURRENCY = 50


def _keypair(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid=kid, alg="RS256", use="sig")
    return private, jwk


@pytest.fixture(scope="module")
def old_key():
    return _keypair("old")


@pytest.fixture(scope="module")
def new_key():
    return _keypair("new")


def _token(key, sub: str = "user-1") -> str:
    private, jwk = key
    claims = {
        "sub": sub,
        "aud": settings.supabase_jwt_audience,
        "iss": f"{settings.supabase_project_url}/auth/v1",
        "exp": int(time.time()) + 300,
    }
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": jwk["kid"]})


@pytest.fixture(autouse=True)
def _fresh_module_state(monkeypatch):
    # A fresh lock per test: an asyncio.Lock binds to the event loop it first waits on.
    monkeypatch.setattr(jwks, "_cache", {})
    monkeypatch.setattr(jwks, "_lock", asyncio.Lock())
    monkeypatch.setattr(jwks, "_generation", 0)
    monkeypatch.setattr(jwks, "_last_error", None)


class FakeRemote:
    """Stands in for Supabase. Each fetch waits on `gate`, so callers pile up behind it."""

    def __init__(self, monkeypatch, *results):
        self.results = list(results)
        self.calls = 0
        self.gate = asyncio.Event()
        self.gate.set()
        monkeypatch.setattr(jwks, "_fetch_from_remote", self.fetch)

    async def fetch(self):
        self.calls += 1
        await self.gate.wait()
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, BaseException):
            raise result
        return result


def _seed_cache(keys, *, stale: bool):
    age = settings.supabase_jwks_ttl_seconds + 1 if stale else 0
    jwks._cache["jwks"] = {"keys": keys}
    jwks._cache["fetched_at"] = time.monotonic() - age


async def _gather_held(remote, coros):
    """Start every coroutine while the fetch is held open, then let it finish."""
    remote.gate.clear()
    tasks = [asyncio.ensure_future(c) for c in coros]
    for _ in range(5):
        await asyncio.sleep(0)
    remote.gate.set()
    return await asyncio.gather(*tasks, return_exceptions=True)


async def test_fresh_cache_is_served_without_a_fetch(monkeypatch, old_key):
    remote = FakeRemote(monkeypatch, {"keys": []})
    _seed_cache([old_key[1]], stale=False)

    user = await verify_supabase_jwt(_token(old_key))

    assert user.user_id == "user-1"
    assert remote.calls == 0


async def test_concurrent_verifications_against_a_stale_cache_fetch_once(monkeypatch, old_key):
    remote = FakeRemote(monkeypatch, {"keys": [old_key[1]]})
    _seed_cache([old_key[1]], stale=True)

    results = await _gather_held(
        remote, [verify_supabase_jwt(_token(old_key, f"u{i}")) for i in range(CONCURRENCY)]
    )

    assert [r.user_id for r in results] == [f"u{i}" for i in range(CONCURRENCY)]
    assert remote.calls == 1
    assert not jwks._is_stale()


async def test_concurrent_verifications_against_an_empty_cache_fetch_once(monkeypatch, old_key):
    remote = FakeRemote(monkeypatch, {"keys": [old_key[1]]})

    results = await _gather_held(remote, [verify_supabase_jwt(_token(old_key)) for _ in range(CONCURRENCY)])

    assert all(r.user_id == "user-1" for r in results)
    assert remote.calls == 1


async def test_failed_fetch_releases_the_lock_and_leaves_the_cache_alone(monkeypatch, old_key):
    remote = FakeRemote(monkeypatch, RuntimeError("supabase down"), {"keys": [old_key[1]]})
    _seed_cache([old_key[1]], stale=True)
    before = dict(jwks._cache)

    results = await _gather_held(remote, [jwks.get_jwks() for _ in range(CONCURRENCY)])

    # Every caller sees the failure, but only one fetch was made: the rest queued behind
    # it and took its error instead of retrying one after another.
    assert all(isinstance(r, RuntimeError) for r in results)
    assert remote.calls == 1
    assert not jwks._lock.locked()
    assert jwks._cache == before

    # The next request retries, and a success clears the failure.
    assert await jwks.get_jwks() == {"keys": [old_key[1]]}
    assert remote.calls == 2
    assert not jwks._is_stale()
    assert jwks._last_error is None


async def test_failed_fetch_makes_verification_fail_as_before(monkeypatch, old_key):
    FakeRemote(monkeypatch, RuntimeError("supabase down"))
    _seed_cache([old_key[1]], stale=True)

    with pytest.raises(RuntimeError):
        await verify_supabase_jwt(_token(old_key))


async def test_key_rotation_still_refreshes(monkeypatch, old_key, new_key):
    remote = FakeRemote(monkeypatch, {"keys": [old_key[1], new_key[1]]})
    _seed_cache([old_key[1]], stale=False)

    user = await verify_supabase_jwt(_token(new_key))

    assert user.user_id == "user-1"
    assert remote.calls == 1
    assert [k["kid"] for k in jwks._cache["jwks"]["keys"]] == ["old", "new"]


async def test_concurrent_requests_signed_by_a_rotated_key_share_one_refresh(monkeypatch, old_key, new_key):
    remote = FakeRemote(monkeypatch, {"keys": [old_key[1], new_key[1]]})
    _seed_cache([old_key[1]], stale=False)

    results = await _gather_held(remote, [verify_supabase_jwt(_token(new_key)) for _ in range(CONCURRENCY)])

    assert all(r.user_id == "user-1" for r in results)
    assert remote.calls == 1


async def test_unknown_kid_is_still_refused_after_a_refresh(monkeypatch, old_key, new_key):
    remote = FakeRemote(monkeypatch, {"keys": [old_key[1]]})
    _seed_cache([old_key[1]], stale=False)

    with pytest.raises(HTTPException) as exc:
        await verify_supabase_jwt(_token(new_key))

    assert exc.value.detail == "Unknown signing key"
    assert remote.calls == 1


async def test_a_cancelled_fetch_does_not_stop_the_next_caller_fetching(monkeypatch, old_key):
    remote = FakeRemote(monkeypatch, {"keys": [old_key[1]]})
    remote.gate.clear()

    first = asyncio.ensure_future(jwks.get_jwks())
    await asyncio.sleep(0)
    second = asyncio.ensure_future(jwks.get_jwks())
    await asyncio.sleep(0)
    first.cancel()
    remote.gate.set()

    assert await second == {"keys": [old_key[1]]}
    assert first.cancelled()
    assert remote.calls == 2
    assert not jwks._lock.locked()
