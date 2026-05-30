import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.bookmarks import (
    BookmarkChunk,
    BookmarkCreate,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkSource,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Verify chunk exists
    try:
        chunk_row = await pool.fetchrow(
            "SELECT id FROM chunks WHERE id = $1",
            chunk_uuid,
        )
    except Exception as exc:
        logger.error("create_bookmark chunk check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if chunk_row is None:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Insert bookmark; silently handle duplicate
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO bookmarks (user_id, chunk_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, chunk_id) DO NOTHING
            RETURNING id, created_at
            """,
            user.user_id,
            chunk_uuid,
        )
    except Exception as exc:
        logger.error("create_bookmark insert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row is None:
        # Already bookmarked — fetch the existing record
        try:
            row = await pool.fetchrow(
                "SELECT id, created_at FROM bookmarks WHERE user_id = $1 AND chunk_id = $2",
                user.user_id,
                chunk_uuid,
            )
        except Exception as exc:
            logger.error("create_bookmark fetch existing failed (%s)", exc.__class__.__name__)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return BookmarkResponse(
        id=str(row["id"]),
        chunk_id=body.chunk_id,
        created_at=row["created_at"].isoformat(),
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
            SELECT b.id, b.chunk_id, b.created_at,
                   c.content, c.reference,
                   d.collection, d.title AS document_title, d.author
            FROM bookmarks b
            JOIN chunks c ON c.id = b.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE b.user_id = $1
            ORDER BY b.created_at DESC
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
                chunk=BookmarkChunk(
                    content=row["content"],
                    source=BookmarkSource(
                        collection=row["collection"],
                        document_title=row["document_title"],
                        author=row["author"],
                        reference=row["reference"],
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
