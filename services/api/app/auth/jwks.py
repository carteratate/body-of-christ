import asyncio
import time
from typing import Any

import httpx

from app.config import settings

# { "jwks": <raw jwks dict>, "fetched_at": <monotonic float> }
_cache: dict[str, Any] = {}
# Held across the fetch, so one request refreshes and the rest wait for its result.
_lock = asyncio.Lock()
# Bumped when a fetch finishes, whether it succeeded or failed (not when it is cancelled).
# A coroutine that saw a different value before it queued knows a fetch ended while it
# waited, and takes that fetch's outcome instead of fetching again.
_generation = 0
_last_error: Exception | None = None


def _is_stale() -> bool:
    if not _cache:
        return True
    return (time.monotonic() - _cache["fetched_at"]) > settings.supabase_jwks_ttl_seconds


async def _fetch_from_remote() -> dict[str, Any]:
    url = f"{settings.supabase_project_url}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.json()


async def get_jwks(force_refresh: bool = False) -> dict[str, Any]:
    global _generation, _last_error

    # Fast path: no lock needed if cache is warm and no forced refresh.
    if not force_refresh and not _is_stale():
        return _cache["jwks"]

    seen = _generation
    async with _lock:
        # Re-check now that we hold the lock: another coroutine may have refreshed.
        if not force_refresh and not _is_stale():
            return _cache["jwks"]
        if _generation != seen:
            # A fetch finished while we waited. Share a failure rather than retrying in
            # turn behind the lock; after a success, a forced refresh has its fresh keys.
            if _last_error is not None:
                raise _last_error
            return _cache["jwks"]

        try:
            fresh = await _fetch_from_remote()
        except Exception as exc:
            _last_error = exc
            _generation += 1
            raise
        _cache["jwks"] = fresh
        _cache["fetched_at"] = time.monotonic()
        _last_error = None
        _generation += 1
        return fresh
