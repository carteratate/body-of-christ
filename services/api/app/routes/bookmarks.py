import asyncio
import logging
import time
import uuid
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from app import corpus_lifecycle, corpus_schema
from app.db import get_pool
from app.footnotes import fetch_footnotes, has_footnotes
from app.headings import fetch_headings
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.rag.steps import document_facts
from app.reader_access import access_fields, document_access
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
        # Retired rows are joined on purpose and resolved (2.4a): a bookmark whose
        # passage left the corpus is marked, never dropped, and keeps its note.
        async def saved(schema: corpus_schema.CorpusSchema):
            found = await pool.fetch(_list_sql(schema), user.user_id)
            return found, await corpus_lifecycle.resolve_saved(
                pool, found, schema, _BOOKMARK_PASSAGE_SQL)

        rows, (resolutions, targets) = await corpus_schema.run_with_fallback(saved, pool)
        # What each bookmark shows: its own passage, or the one it moved to. A removed
        # passage shows no text, so it takes no notes or facts.
        shown = {}
        for row in rows:
            resolution = resolutions.get(str(row["chunk_id"]), corpus_lifecycle.CURRENT)
            if resolution.status == "removed":
                continue
            target = (targets.get(resolution.redirect.chunk_id)
                      if resolution.status == "moved" else None)
            shown[str(row["chunk_id"])] = target or row
        access = await document_access(
            pool, {row["document_id"] for row in [*rows, *shown.values()]})
    except Exception as exc:
        logger.error("list_bookmarks query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    # Notes and headings (issue #445), each best-effort and bounded, read together.
    notes, marks = await asyncio.gather(
        fetch_footnotes(pool, [
            (str(row["chunk_id"]), row["content"]) for row in shown.values()
            if has_footnotes(row["collection"], row["document_title"])
        ]),
        fetch_headings(pool, [
            (str(row["chunk_id"]), row["content"]) for row in shown.values()
        ]),
    )
    facts, _ = await document_facts.fetch_best_effort(pool, [
        str(row["chunk_id"]) for row in shown.values()
    ])

    def chunk(row, display) -> BookmarkChunk:
        source_row = display if display is not None else row
        passage = facts.get(str(source_row["chunk_id"]))
        card_access = access_fields(
            access, source_row["document_id"], source_row["unit_label"],
            chunk_id=source_row["chunk_id"],
            content=display["content"] if display is not None else None)
        return BookmarkChunk(
            # A removed passage shows no text (Carter, 9 Nov 2026).
            content=display["content"] if display is not None else "",
            footnotes=notes.get(str(display["chunk_id"]), []) if display is not None else [],
            headings=marks.get(str(display["chunk_id"]), []) if display is not None else [],
            source=BookmarkSource(**{
                "collection": source_row["collection"],
                "document_title": source_row["document_title"],
                "author": source_row["author"],
                "reference": source_row["reference"],
                "document_id": str(source_row["document_id"]),
                "anchor": source_row["anchor"],
                "chapter_key": source_row["chapter_key"],
                "unit_label": source_row["unit_label"],
                **card_access,
                # Facts and passage fields (2.4a); their author replaces the row's.
                **(passage.source_fields(card_access["source_credit"]) if passage else {}),
            }),
        )

    bookmarks = []
    for row in rows:
        resolution = resolutions.get(str(row["chunk_id"]), corpus_lifecycle.CURRENT)
        bookmarks.append(BookmarkResponse(
            id=str(row["id"]),
            chunk_id=str(row["chunk_id"]),
            created_at=row["created_at"].isoformat(),
            note=row["note"],
            chunk=chunk(row, shown.get(str(row["chunk_id"]))),
            status=resolution.status,
            tombstone=resolution.tombstone,
            redirect=resolution.redirect,
        ))
    return BookmarkListResponse(bookmarks=bookmarks)


def _list_sql(schema: corpus_schema.CorpusSchema) -> str:
    """The user's bookmarks. With 0042, each row also says whether its passage is
    current; without it, the SQL is today's."""
    current = (",\n                   c.retired_at IS NULL AND d.retired_at IS NULL AS current"
               if schema.lifecycle else "")
    return f"""
            SELECT b.id, b.chunk_id, b.created_at, b.note,
                   {_BOOKMARK_COLUMNS}{current}
            FROM bookmarks b
            JOIN chunks c ON c.id = b.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE b.user_id = $1
            ORDER BY b.created_at DESC, b.id DESC
            """


_BOOKMARK_COLUMNS = """c.content, c.reference, c.anchor, c.chapter_key, c.unit_label,
                   c.document_id,
                   d.collection, d.title AS document_title, d.author"""

# The passages moved bookmarks now point at (2.4a).
_BOOKMARK_PASSAGE_SQL = f"""
    SELECT c.id AS chunk_id, {_BOOKMARK_COLUMNS}
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.id = ANY($1::uuid[])
"""


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
