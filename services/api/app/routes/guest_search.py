"""Guest search — one free SSE search per IP per 24 hours. No JWT required."""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import get_pool
from app.rag.constants import VALID_COLLECTIONS
from app.rag.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()

_GUEST_QUOTA = 3
_VALID_TRANSLATIONS = {"CPDV", "douay-rheims"}


class GuestSearchFilters(BaseModel):
    collections: list[str]
    translation: str = "CPDV"


class GuestSearchRequest(BaseModel):
    query: str
    filters: GuestSearchFilters
    quota: int = _GUEST_QUOTA


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host or "unknown"


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


async def _has_used_trial(ip_hash: str) -> bool:
    pool = get_pool()
    if pool is None:
        return False  # DB unavailable — fail open so guests aren't silently blocked
    row = await pool.fetchrow(
        """
        SELECT 1 FROM guest_trials
        WHERE ip_hash = $1
          AND created_at > now() - INTERVAL '24 hours'
        LIMIT 1
        """,
        ip_hash,
    )
    return row is not None


async def _record_trial(ip_hash: str) -> None:
    pool = get_pool()
    if pool is None:
        return
    await pool.execute(
        "INSERT INTO guest_trials (ip_hash) VALUES ($1)",
        ip_hash,
    )


@router.post("/search/guest")
async def guest_search(body: GuestSearchRequest, request: Request) -> StreamingResponse:
    ip_hash = _hash_ip(_get_client_ip(request))

    if await _has_used_trial(ip_hash):
        raise HTTPException(status_code=429, detail="trial_exhausted")

    collections = [c for c in body.filters.collections if c in VALID_COLLECTIONS]
    if not collections:
        raise HTTPException(
            status_code=400,
            detail=f"No valid collections. Valid: {sorted(VALID_COLLECTIONS)}",
        )

    translation = body.filters.translation if body.filters.translation in _VALID_TRANSLATIONS else "CPDV"
    quota = max(1, min(body.quota, _GUEST_QUOTA))

    # Record before the pipeline starts to block parallel duplicate requests
    await _record_trial(ip_hash)

    async def event_stream():
        async for event in run_search_pipeline(
            query=body.query,
            collections=collections,
            translation=translation,
            quota=quota,
            user_id=None,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
