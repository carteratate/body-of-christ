import logging
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app import corpus_lifecycle, corpus_schema
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
# listed nor written. The filter is in the query, before LIMIT, so hidden rows never
# take the place of readable ones.
_READABLE = " AND d.reader_access <> 'excerpt'"


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


# The chapter label comes from a visible passage (2.4a). A row whose document is
# retired has none, so it drops out of lists; the single-document GET reads it with
# `visible` empty, to say the document was removed.
_SELECT_BASE = """
    SELECT rp.document_id, rp.chapter_key, rp.anchor, rp.updated_at,
           d.collection, d.title AS document_title, d.author,
           chapter.chapter_label{retired}
    FROM reading_progress rp
    JOIN documents d ON d.id = rp.document_id
    JOIN LATERAL (
        SELECT c.chapter_label
        FROM chunks c
        WHERE c.document_id = rp.document_id
          AND c.chapter_key = rp.chapter_key{visible}
        ORDER BY c.position
        LIMIT 1
    ) chapter ON true
"""


def _select(schema: corpus_schema.CorpusSchema, *, hide_retired: bool) -> str:
    return (_SELECT_BASE
            .replace("{retired}", ",\n           d.retired_at IS NOT NULL AS retired"
                     if schema.retired else "")
            .replace("{visible}", schema.visible("c") if hide_retired else ""))


async def _fetch_readable(fetch, where: str, *args, hide_retired: bool = True):
    """Run `_SELECT_BASE + where` with excerpt-only documents filtered out, and with
    retired passages and documents left out unless `hide_retired` is false. On a
    database without 0041 there is no excerpt filter, and without 0042 nothing is
    retired, so the query runs without them."""
    async def run(schema: corpus_schema.CorpusSchema):
        where_ = where.replace("{visible}", schema.visible("d") if hide_retired else "")
        try:
            return await fetch(_select(schema, hide_retired=hide_retired)
                               + where_.replace("{readable}", _READABLE), *args)
        except asyncpg.UndefinedColumnError as exc:
            if "reader_access" not in str(exc):
                raise
            return await fetch(_select(schema, hide_retired=hide_retired)
                               + where_.replace("{readable}", ""), *args)

    return await corpus_schema.run_with_fallback(run, get_pool())


@router.get("/reading-progress", response_model=ReadingProgressListResponse)
async def list_reading_progress(
    limit: int = Query(default=6, ge=1, le=10),
    user: AuthUser = Depends(get_current_user),
) -> ReadingProgressListResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        rows = await _fetch_readable(
            pool.fetch,
            " WHERE rp.user_id = $1{readable}{visible} ORDER BY rp.updated_at DESC LIMIT $2",
            user.user_id,
            limit,
        )
    except Exception as exc:
        logger.error("list_reading_progress failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    return ReadingProgressListResponse(items=[_item(row) for row in rows])


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
        row = await _fetch_readable(
            pool.fetchrow,
            " WHERE rp.user_id = $1 AND rp.document_id = $2{readable}",
            user.user_id,
            doc_uuid,
            hide_retired=False,
        )
        resolution = None
        if row is not None and row.get("retired"):
            # The progress row is kept; its "continue reading" entry shows why the
            # document left (2.4a).
            schema = await corpus_schema.current(pool)
            resolution = await corpus_lifecycle.resolve_document(pool, doc_uuid, schema)
    except Exception as exc:
        logger.error("get_reading_progress failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Reading progress not found")
    item = _item(row)
    if resolution is not None and resolution.status == "removed":
        item = item.model_copy(update={"status": "removed", "tombstone": resolution.tombstone})
    return item


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
        # Only a visible passage is a reading location (2.4a).
        async def find(schema: corpus_schema.CorpusSchema):
            return await pool.fetchrow(
                f"""
            SELECT c.chapter_label
            FROM chunks c
            WHERE c.document_id = $1 AND c.chapter_key = $2
              AND ($3::text IS NULL OR c.anchor = $3){schema.visible("c")}
            ORDER BY c.position
            LIMIT 1
            """,
                doc_uuid,
                body.chapter_key,
                body.anchor,
            )

        location = await corpus_schema.run_with_fallback(find, pool)
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
