import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.search import (
    ChunkResult,
    ChunkSource,
    SearchHistoryResponse,
    SearchRequest,
    SearchResultsResponse,
    SearchSummary,
)
from app.rag.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "saints"}
_VALID_TRANSLATIONS = {"CPDV", "douay-rheims"}


# ── Rate limit dependency ─────────────────────────────────────────────────────

async def check_search_rate_limit(
    user: AuthUser = Depends(get_current_user),
) -> None:
    """Rate limit for V2 search endpoints (stricter than V1 chat).

    TODO: Currently shares the same user_usage counters (rate_count / quota_count)
    as V1 chat. Add search_rate_count / search_quota_count columns in a future
    migration so that chat and search quotas are tracked independently.
    """
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO user_usage (user_id, rate_window_start, rate_count, quota_date, quota_count)
            VALUES ($1, now(), 1, current_date, 1)
            ON CONFLICT (user_id) DO UPDATE SET
                rate_window_start = CASE
                    WHEN now() - user_usage.rate_window_start >= INTERVAL '60 seconds'
                    THEN now() ELSE user_usage.rate_window_start END,
                rate_count = CASE
                    WHEN now() - user_usage.rate_window_start >= INTERVAL '60 seconds'
                    THEN 1 ELSE user_usage.rate_count + 1 END,
                quota_date = current_date,
                quota_count = CASE
                    WHEN user_usage.quota_date < current_date
                    THEN 1 ELSE user_usage.quota_count + 1 END
            RETURNING rate_count, quota_count
            """,
            user.user_id,
        )
    except Exception as exc:
        logger.error("search rate_limit check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row["rate_count"] > settings.rate_limit_search_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Search rate limit reached. Try again in a moment.",
            headers={"Retry-After": "60"},
        )
    if row["quota_count"] > settings.daily_search_quota:
        raise HTTPException(
            status_code=429,
            detail="Daily search limit reached. Try again tomorrow.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(
    body: SearchRequest,
    user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_search_rate_limit),
) -> StreamingResponse:
    """Stream RAG search results as Server-Sent Events."""
    # Filter out invalid collection values; reject if none remain
    valid_collections = [c for c in body.filters.collections if c in _VALID_COLLECTIONS]
    if not valid_collections:
        raise HTTPException(
            status_code=400,
            detail=f"No valid collections specified. Valid values: {sorted(_VALID_COLLECTIONS)}",
        )

    # Validate translation; default to "CPDV" if invalid (non-fatal)
    translation = body.filters.translation if body.filters.translation in _VALID_TRANSLATIONS else "CPDV"

    async def event_stream():
        async for event in run_search_pipeline(
            query=body.query,
            collections=valid_collections,
            translation=translation,
            quota=body.quota,
            user_id=user.user_id,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/searches", response_model=SearchHistoryResponse)
async def list_searches(
    user: AuthUser = Depends(get_current_user),
) -> SearchHistoryResponse:
    """Return the last 50 searches for the authenticated user."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        rows = await pool.fetch(
            """
            SELECT id, query, filters, result_count, created_at
            FROM searches
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 50
            """,
            user.user_id,
        )
    except Exception as exc:
        logger.error("list_searches query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return SearchHistoryResponse(
        searches=[
            SearchSummary(
                id=str(row["id"]),
                query=row["query"],
                filters=row["filters"],
                result_count=row["result_count"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )


@router.get("/searches/{search_id}/results", response_model=SearchResultsResponse)
async def get_search_results(
    search_id: str,
    user: AuthUser = Depends(get_current_user),
) -> SearchResultsResponse:
    """Return stored chunk results for a completed search."""
    # Validate that search_id is a well-formed UUID
    try:
        search_uuid = uuid.UUID(search_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid search_id: must be a UUID")

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        # Verify the search exists and belongs to this user
        search_row = await pool.fetchrow(
            "SELECT id, query FROM searches WHERE id = $1 AND user_id = $2",
            search_uuid,
            user.user_id,
        )
    except Exception as exc:
        logger.error("get_search_results ownership check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if search_row is None:
        raise HTTPException(status_code=404, detail="Search not found")

    try:
        rows = await pool.fetch(
            """
            SELECT r.rank, r.reranker_score, r.explanation,
                   c.id AS chunk_id, c.content, c.reference, c.position,
                   d.collection, d.title AS document_title, d.author, d.id AS document_id
            FROM retrievals r
            JOIN chunks c ON c.id = r.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE r.search_id = $1
            ORDER BY r.rank ASC
            """,
            search_uuid,
        )
    except Exception as exc:
        logger.error("get_search_results retrieval query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    results = [
        ChunkResult(
            chunk_id=str(row["chunk_id"]),
            content=row["content"],
            source=ChunkSource(
                collection=row["collection"],
                document_title=row["document_title"],
                author=row["author"],
                reference=row["reference"],
                document_id=str(row["document_id"]),
                position=row["position"],
            ),
            reranker_score=row["reranker_score"],
            explanation=row["explanation"],
        )
        for row in rows
    ]

    return SearchResultsResponse(
        search_id=search_id,
        query=search_row["query"],
        results=results,
    )
