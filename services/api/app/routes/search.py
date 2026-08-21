import base64
import binascii
import datetime
import json
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
from app.rag.constants import VALID_COLLECTIONS as _VALID_COLLECTIONS
from app.rag.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_TRANSLATIONS = {"CPDV", "douay-rheims"}


# ── Rate limit dependency ─────────────────────────────────────────────────────

async def _validate_collections(body: SearchRequest) -> list[str]:
    """Validate collection names and return the allowed subset.

    Declared as a dependency so that requests with only invalid collections
    are rejected before the rate-limit counter is incremented.
    """
    valid = [c for c in body.filters.collections if c in _VALID_COLLECTIONS]
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"No valid collections specified. Valid values: {sorted(_VALID_COLLECTIONS)}",
        )
    return valid


async def check_search_rate_limit(
    user: AuthUser = Depends(get_current_user),
    _valid: list[str] = Depends(_validate_collections),
) -> None:
    """Rate limit for V2 search endpoints (stricter than V1 chat).

    Depends on _validate_collections so that invalid-collection requests
    are rejected with 400 before the counter is incremented.

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
        now = datetime.datetime.now(datetime.timezone.utc)
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        retry_after = str(max(1, int((midnight - now).total_seconds())))
        raise HTTPException(
            status_code=429,
            detail="Daily search limit reached. Try again tomorrow.",
            headers={"Retry-After": retry_after},
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(
    body: SearchRequest,
    user: AuthUser = Depends(get_current_user),
    valid_collections: list[str] = Depends(_validate_collections),
    _: None = Depends(check_search_rate_limit),
) -> StreamingResponse:
    """Stream RAG search results as Server-Sent Events."""
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
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _encode_history_cursor(created_at: datetime.datetime, search_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{search_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_history_cursor(cursor: str) -> tuple[datetime.datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        created_at_raw, search_id_raw = raw.rsplit("|", 1)
        created_at = datetime.datetime.fromisoformat(created_at_raw)
        if created_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return created_at, uuid.UUID(search_id_raw)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Invalid history cursor") from exc


@router.get("/searches", response_model=SearchHistoryResponse)
async def list_searches(
    limit: int = Query(default=50, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=256),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    user: AuthUser = Depends(get_current_user),
) -> SearchHistoryResponse:
    """Return one cursor-paginated page of the user's search history."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    cursor_values = _decode_history_cursor(cursor) if cursor else None
    cursor_created_at = cursor_values[0] if cursor_values else None
    cursor_id = cursor_values[1] if cursor_values else None
    normalized_query = q.strip() if q else None
    try:
        rows = await pool.fetch(
            """
            SELECT id, query, filters, result_count, created_at
            FROM searches
            WHERE user_id = $1
              AND ($2::timestamptz IS NULL OR (created_at, id) < ($2, $3::uuid))
              AND ($4::text IS NULL OR strpos(lower(query), lower($4)) > 0)
            ORDER BY created_at DESC, id DESC
            LIMIT $5
            """,
            user.user_id,
            cursor_created_at,
            cursor_id,
            normalized_query,
            limit + 1,
        )
    except Exception as exc:
        logger.error("list_searches query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    def _parse_filters(raw) -> dict | None:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception:
            return None

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_history_cursor(last["created_at"], last["id"])

    return SearchHistoryResponse(
        searches=[
            SearchSummary(
                id=str(row["id"]),
                query=row["query"],
                filters=_parse_filters(row["filters"]),
                result_count=row["result_count"],
                created_at=row["created_at"].isoformat(),
            )
            for row in page_rows
        ],
        next_cursor=next_cursor,
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
        async with asyncio.timeout(8):
            # Keep the server bound below the browser timeout. A saturated pool
            # or stalled database must not leave History loading indefinitely.
            search_row = await pool.fetchrow(
                "SELECT id, query, filters, result_count FROM searches WHERE id = $1 AND user_id = $2",
                search_uuid,
                user.user_id,
            )
            if search_row is None:
                raise HTTPException(status_code=404, detail="Search not found")
            rows = await pool.fetch(
                """
                SELECT r.rank, r.reranker_score, r.explanation,
                       c.id AS chunk_id, c.content, c.reference, c.position, c.anchor, c.chapter_key,
                       c.unit_label,
                       d.collection, d.title AS document_title, d.author, d.id AS document_id
                FROM retrievals r
                JOIN chunks c ON c.id = r.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE r.search_id = $1
                ORDER BY r.rank ASC
                """,
                search_uuid,
            )
    except HTTPException:
        raise
    except TimeoutError as exc:
        logger.warning("get_search_results timed out: search=%s", search_id)
        raise HTTPException(status_code=504, detail="Saved search took too long to load") from exc
    except Exception as exc:
        logger.error("get_search_results query failed (%s)", exc.__class__.__name__)
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
                anchor=row["anchor"],
                chapter_key=row["chapter_key"],
                unit_label=row["unit_label"],
            ),
            reranker_score=row["reranker_score"],
            explanation=row["explanation"],
        )
        for row in rows
    ]

    expected_count = int(search_row["result_count"] or 0)
    restore_status = (
        "complete"
        if len(results) == expected_count
        else "results_unavailable"
    )
    if restore_status != "complete":
        logger.warning(
            "restore incomplete: search=%s expected=%d available=%d",
            search_id,
            expected_count,
            len(results),
        )

    return SearchResultsResponse(
        search_id=search_id,
        query=search_row["query"],
        filters=(
            search_row.get("filters")
            if isinstance(search_row.get("filters"), dict)
            else json.loads(search_row.get("filters"))
            if search_row.get("filters")
            else None
        ),
        results=results,
        restore_status=restore_status,
        expected_result_count=expected_count,
    )


@router.delete("/searches/{search_id}", status_code=204)
async def delete_search(
    search_id: str,
    user: AuthUser = Depends(get_current_user),
) -> Response:
    """Delete a search (and its retrievals, via cascade) owned by the user."""
    try:
        search_uuid = uuid.UUID(search_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid search_id: must be a UUID")

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        result = await pool.execute(
            "DELETE FROM searches WHERE id = $1 AND user_id = $2",
            search_uuid,
            user.user_id,
        )
    except Exception as exc:
        logger.error("delete_search query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    # asyncpg returns "DELETE N" where N is the number of rows deleted
    deleted_count = int(result.split()[-1])
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Search not found")

    return Response(status_code=204)
