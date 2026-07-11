"""Guest search — one free SSE search per IP per 24 hours. No JWT required."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
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

    @field_validator("collections")
    @classmethod
    def validate_collections(cls, collections: list[str]) -> list[str]:
        if not collections:
            raise ValueError("At least one collection is required")
        invalid = sorted(set(collections) - VALID_COLLECTIONS)
        if invalid:
            raise ValueError(f"Invalid collections: {invalid}")
        return collections


class GuestSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    filters: GuestSearchFilters
    quota: int = _GUEST_QUOTA

    @field_validator("query")
    @classmethod
    def normalize_query(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be blank")
        return query


def _get_client_ip(request: Request) -> str:
    # The browser cannot set this header: the Vercel proxy derives it from a
    # platform-controlled forwarding header and authenticates the hop with the
    # same internal secret required by the API middleware. Never trust raw XFF
    # at Railway, since direct callers can spoof it.
    proxy_ip = request.headers.get("x-theocorpus-client-ip")
    supplied_secret = request.headers.get("x-internal-secret")
    if settings.internal_api_secret and supplied_secret == settings.internal_api_secret and proxy_ip:
        try:
            return str(ipaddress.ip_address(proxy_ip.strip()))
        except ValueError:
            logger.warning("trusted proxy supplied invalid client IP")
    return request.client.host or "unknown"


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


async def _try_record_trial(ip_hash: str) -> bool:
    """Atomically insert a trial record if no trial exists for this IP in the last 24h.
    Returns True if the slot was taken (search allowed), False if already used."""
    pool = get_pool()
    if pool is None:
        return True  # fail open on DB unavailability
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Serialize claims for one hash while retaining a rolling 24h
                # window (which cannot be represented by a static UNIQUE key).
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    ip_hash,
                )
                row = await conn.fetchrow(
                    """
                    INSERT INTO guest_trials (ip_hash)
                    SELECT $1
                    WHERE NOT EXISTS (
                        SELECT 1 FROM guest_trials
                        WHERE ip_hash = $1
                          AND created_at > NOW() - INTERVAL '24 hours'
                    )
                    RETURNING id
                    """,
                    ip_hash,
                )
                return row is not None
    except Exception:
        logger.warning("guest trial record failed")
        return True  # fail open


@router.post("/search/guest")
async def guest_search(body: GuestSearchRequest, request: Request) -> StreamingResponse:
    ip_hash = _hash_ip(_get_client_ip(request))

    if not await _try_record_trial(ip_hash):
        raise HTTPException(status_code=429, detail="trial_exhausted")

    collections = body.filters.collections

    translation = body.filters.translation if body.filters.translation in _VALID_TRANSLATIONS else "CPDV"
    quota = max(1, min(body.quota, _GUEST_QUOTA))

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
