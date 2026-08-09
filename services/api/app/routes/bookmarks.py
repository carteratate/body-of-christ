import logging
import time
import uuid
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.bookmarks import (
    BookmarkChunk,
    BookmarkCreate,
    BookmarkListResponse,
    BookmarkNoteUpdate,
    BookmarkResponse,
    BookmarkSource,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Best-effort guard against accidental/repeated writes within one API process.
# Bookmark writes are cheap, user-scoped, and idempotent; this is not treated as
# a security boundary. A bounded sweep prevents inactive user keys accumulating.
_write_rate_timestamps: dict[str, list[float]] = defaultdict(list)
_WRITE_RATE_LIMIT = 20
_write_rate_check_count = 0


def _check_write_rate_limit(user_id: str) -> None:
    global _write_rate_check_count
    now = time.time()
    _write_rate_check_count += 1
    if _write_rate_check_count % 100 == 0:
        stale_users = [
            key for key, timestamps in _write_rate_timestamps.items()
            if not timestamps or now - timestamps[-1] >= 60
        ]
        for key in stale_users:
            _write_rate_timestamps.pop(key, None)
    window = [t for t in _write_rate_timestamps[user_id] if now - t < 60]
    _write_rate_timestamps[user_id] = window
    if len(window) >= _WRITE_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again in a moment.",
            headers={"Retry-After": "60"},
        )
    _write_rate_timestamps[user_id].append(now)


@router.post("/bookmarks", response_model=BookmarkResponse, status_code=201)
async def create_bookmark(
    body: BookmarkCreate,
    user: AuthUser = Depends(get_current_user),
) -> BookmarkResponse:
    """Bookmark a chunk for the authenticated user."""
    try:
        chunk_uuid = uuid.UUID(body.chunk_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid chunk_id: must be a UUID")

    started = time.perf_counter()
    _check_write_rate_limit(str(user.user_id))
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    acquired = time.perf_counter()
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO bookmarks (user_id, chunk_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, chunk_id)
            DO UPDATE SET chunk_id = EXCLUDED.chunk_id
            RETURNING id, created_at
            """,
            user.user_id,
            chunk_uuid,
        )
    except Exception as exc:
        if exc.__class__.__name__ == "ForeignKeyViolationError":
            raise HTTPException(status_code=404, detail="Chunk not found") from exc
        logger.error("create_bookmark insert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    completed = time.perf_counter()
    logger.info(
        "create_bookmark timing: setup=%.3fs sql=%.3fs total=%.3fs",
        acquired - started, completed - acquired, completed - started,
    )

    return BookmarkResponse(
        id=str(row["id"]),
        chunk_id=body.chunk_id,
        created_at=row["created_at"].isoformat(),
    )


@router.patch("/bookmarks/{bookmark_id}", response_model=BookmarkResponse)
async def update_bookmark_note(
    bookmark_id: str,
    body: BookmarkNoteUpdate,
    user: AuthUser = Depends(get_current_user),
) -> BookmarkResponse:
    """Update the personal note on a bookmark owned by the authenticated user."""
    try:
        bookmark_uuid = uuid.UUID(bookmark_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid bookmark_id: must be a UUID")

    _check_write_rate_limit(str(user.user_id))

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            UPDATE bookmarks
            SET note = $1
            WHERE id = $2 AND user_id = $3
            RETURNING id, chunk_id, created_at, note
            """,
            body.note,
            bookmark_uuid,
            user.user_id,
        )
    except Exception as exc:
        logger.error("update_bookmark_note failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return BookmarkResponse(
        id=str(row["id"]),
        chunk_id=str(row["chunk_id"]),
        created_at=row["created_at"].isoformat(),
        note=row["note"],
    )


@router.get("/bookmarks", response_model=BookmarkListResponse)
async def list_bookmarks(
    user: AuthUser = Depends(get_current_user),
) -> BookmarkListResponse:
    """Return all bookmarks for the authenticated user."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        rows = await pool.fetch(
            """
            SELECT b.id, b.chunk_id, b.created_at, b.note,
                   c.content, c.reference, c.anchor, c.chapter_key, c.document_id,
                   d.collection, d.title AS document_title, d.author
            FROM bookmarks b
            JOIN chunks c ON c.id = b.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE b.user_id = $1
            ORDER BY b.created_at DESC, b.id DESC
            """,
            user.user_id,
        )
    except Exception as exc:
        logger.error("list_bookmarks query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return BookmarkListResponse(
        bookmarks=[
            BookmarkResponse(
                id=str(row["id"]),
                chunk_id=str(row["chunk_id"]),
                created_at=row["created_at"].isoformat(),
                note=row["note"],
                chunk=BookmarkChunk(
                    content=row["content"],
                    source=BookmarkSource(
                        collection=row["collection"],
                        document_title=row["document_title"],
                        author=row["author"],
                        reference=row["reference"],
                        document_id=str(row["document_id"]),
                        anchor=row["anchor"],
                        chapter_key=row["chapter_key"],
                    ),
                ),
            )
            for row in rows
        ]
    )


@router.delete("/bookmarks/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: str,
    user: AuthUser = Depends(get_current_user),
) -> Response:
    """Delete a bookmark owned by the authenticated user."""
    try:
        bookmark_uuid = uuid.UUID(bookmark_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid bookmark_id: must be a UUID")

    _check_write_rate_limit(str(user.user_id))
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        result = await pool.execute(
            "DELETE FROM bookmarks WHERE id = $1 AND user_id = $2",
            bookmark_uuid,
            user.user_id,
        )
    except Exception as exc:
        logger.error("delete_bookmark query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    # asyncpg returns "DELETE N" where N is the number of rows deleted
    deleted_count = int(result.split()[-1])
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return Response(status_code=204)
