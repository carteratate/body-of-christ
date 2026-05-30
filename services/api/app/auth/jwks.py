import asyncio
import time
from typing import Any

import httpx

from app.config import settings

# { "jwks": <raw jwks dict>, "fetched_at": <monotonic float> }
_cache: dict[str, Any] = {}
_lock = asyncio.Lock()


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
    # Fast path: no lock needed if cache is warm and no forced refresh.
    if not force_refresh and not _is_stale():
        return _cache["jwks"]

    # Slow path: fetch outside the lock to avoid blocking concurrent requests,
    # then re-acquire to write (another coroutine may have beaten us to it).
    fresh = await _fetch_from_remote()
    async with _lock:
        _cache["jwks"] = fresh
        _cache["fetched_at"] = time.monotonic()
    return _cache["jwks"]
