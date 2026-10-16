import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.reader_access import document_access, restricted_error
from app.models.reading_progress import (
    ReadingProgressItem,
    ReadingProgressListResponse,
    ReadingProgressUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Excerpt-only documents (issue #265) have no reader, so their progress is neither
# listed nor written. The list over-fetches by this many rows so hidden ones do not
# shorten it.
_RESTRICTED_SLACK = 40


def _item(row) -> ReadingProgressItem:
    return ReadingProgressItem(
        document_id=str(row["document_id"]),
        chapter_key=row["chapter_key"],
        chapter_label=row["chapter_label"],
        anchor=row["anchor"],
        updated_at=row["updated_at"].isoformat(),
        collection=row["collection"],
        document_title=row["document_title"],
        author=row["author"],
    )


_SELECT_BASE = """
    SELECT rp.document_id, rp.chapter_key, rp.anchor, rp.updated_at,
           d.collection, d.title AS document_title, d.author,
           chapter.chapter_label
    FROM reading_progress rp
    JOIN documents d ON d.id = rp.document_id
    JOIN LATERAL (
        SELECT c.chapter_label
        FROM chunks c
        WHERE c.document_id = rp.document_id
          AND c.chapter_key = rp.chapter_key
        ORDER BY c.position
        LIMIT 1
    ) chapter ON true
"""


@router.get("/reading-progress", response_model=ReadingProgressListResponse)
async def list_reading_progress(
    limit: int = Query(default=6, ge=1, le=10),
    user: AuthUser = Depends(get_current_user),
) -> ReadingProgressListResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        rows = await pool.fetch(
            _SELECT_BASE + " WHERE rp.user_id = $1 ORDER BY rp.updated_at DESC LIMIT $2",
            user.user_id,
            limit + _RESTRICTED_SLACK,
        )
        access = await document_access(pool, [row["document_id"] for row in rows])
    except Exception as exc:
        logger.error("list_reading_progress failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    readable = [row for row in rows if not _restricted(access, row["document_id"])]
    return ReadingProgressListResponse(items=[_item(row) for row in readable[:limit]])


def _restricted(access, document_id) -> bool:
    entry = access.get(str(document_id))
    return entry is not None and entry.reader_access == "excerpt"


@router.get("/reading-progress/{doc_id}", response_model=ReadingProgressItem)
async def get_reading_progress(
    doc_id: str,
    user: AuthUser = Depends(get_current_user),
) -> ReadingProgressItem:
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        row = await pool.fetchrow(
            _SELECT_BASE + " WHERE rp.user_id = $1 AND rp.document_id = $2",
            user.user_id,
            doc_uuid,
        )
        access = await document_access(pool, [doc_uuid]) if row is not None else {}
    except Exception as exc:
        logger.error("get_reading_progress failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    if row is None or _restricted(access, doc_uuid):
        raise HTTPException(status_code=404, detail="Reading progress not found")
    return _item(row)


@router.put("/reading-progress/{doc_id}", response_model=ReadingProgressItem)
async def put_reading_progress(
    doc_id: str,
    body: ReadingProgressUpdate,
    user: AuthUser = Depends(get_current_user),
) -> ReadingProgressItem:
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        access = (await document_access(pool, [doc_uuid])).get(str(doc_uuid))
    except Exception as exc:
        logger.error("put_reading_progress access check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    if access is not None and access.reader_access == "excerpt":
        raise restricted_error(access.source_url)

    try:
        location = await pool.fetchrow(
            """
            SELECT c.chapter_label
            FROM chunks c
            WHERE c.document_id = $1 AND c.chapter_key = $2
              AND ($3::text IS NULL OR c.anchor = $3)
            ORDER BY c.position
            LIMIT 1
            """,
            doc_uuid,
            body.chapter_key,
            body.anchor,
        )
    except Exception as exc:
        logger.error("put_reading_progress validation failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    if location is None:
        raise HTTPException(status_code=404, detail="Document reading location not found")

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (user_id, document_id) DO UPDATE SET
                chapter_key = EXCLUDED.chapter_key,
                anchor = EXCLUDED.anchor,
                updated_at = now()
            RETURNING document_id, chapter_key, anchor, updated_at
            """,
            user.user_id,
            doc_uuid,
            body.chapter_key,
            body.anchor,
        )
        document = await pool.fetchrow(
            "SELECT collection, title AS document_title, author FROM documents WHERE id = $1",
            doc_uuid,
        )
    except Exception as exc:
        logger.error("put_reading_progress upsert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row is None or document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return ReadingProgressItem(
        document_id=str(row["document_id"]),
        chapter_key=row["chapter_key"],
        chapter_label=location["chapter_label"],
        anchor=row["anchor"],
        updated_at=row["updated_at"].isoformat(),
        collection=document["collection"],
        document_title=document["document_title"],
        author=document["author"],
    )
