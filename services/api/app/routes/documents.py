import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.documents import (
    DocumentResponse, ReaderPassage, ReaderChapter, TocEntry, TocResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    user: AuthUser = Depends(get_current_user),
) -> DocumentResponse:
    """Return metadata for a single document."""
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            "SELECT id, collection, title, author, year, metadata FROM documents WHERE id = $1",
            doc_uuid,
        )
    except Exception as exc:
        logger.error("get_document query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        chunk_count_row = await pool.fetchrow(
            "SELECT count(*) AS cnt FROM chunks WHERE document_id = $1",
            doc_uuid,
        )
    except Exception as exc:
        logger.error("get_document chunk_count query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return DocumentResponse(
        id=str(row["id"]),
        collection=row["collection"],
        title=row["title"],
        author=row["author"],
        year=row["year"],
        metadata=row["metadata"],
        chunk_count=chunk_count_row["cnt"],
    )


def _document_response(doc_row) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc_row["id"]), collection=doc_row["collection"], title=doc_row["title"],
        author=doc_row["author"], year=doc_row["year"], metadata=doc_row["metadata"],
        chunk_count=doc_row["cnt"],
    )


@router.get("/documents/{doc_id}/toc", response_model=TocResponse)
async def get_document_toc(
    doc_id: str,
    user: AuthUser = Depends(get_current_user),
) -> TocResponse:
    """Ordered chapter list for the reader's pickers + Contents drawer."""
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        doc_row = await pool.fetchrow(
            """SELECT d.id, d.collection, d.title, d.author, d.year, d.metadata,
                      (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS cnt
               FROM documents d WHERE d.id = $1""",
            doc_uuid,
        )
        if doc_row is None:
            raise HTTPException(status_code=404, detail="Document not found")
        chapter_rows = await pool.fetch(
            """SELECT chapter_key, chapter_label
               FROM chunks WHERE document_id = $1 AND chapter_key IS NOT NULL
               GROUP BY chapter_key, chapter_label
               ORDER BY min(position)""",
            doc_uuid,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_document_toc query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    chapters = [TocEntry(chapter_key=r["chapter_key"], chapter_label=r["chapter_label"])
                for r in chapter_rows]
    return TocResponse(document=_document_response(doc_row), chapters=chapters)


@router.get("/documents/{doc_id}/reader", response_model=ReaderChapter)
async def get_document_reader(
    doc_id: str,
    anchor: str | None = Query(default=None, description="Deep-link passage anchor"),
    chapter: str | None = Query(default=None, description="chapter_key to load directly"),
    user: AuthUser = Depends(get_current_user),
) -> ReaderChapter:
    """Return one chapter section of clean passages, with prev/next chapter keys."""
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        doc_row = await pool.fetchrow(
            """SELECT d.id, d.collection, d.title, d.author, d.year, d.metadata,
                      (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS cnt
               FROM documents d WHERE d.id = $1""",
            doc_uuid,
        )
        if doc_row is None:
            raise HTTPException(status_code=404, detail="Document not found")

        # Resolve target chapter_key (explicit chapter > anchor > first chapter).
        chapter_key = chapter
        if chapter_key is None and anchor:
            row = await pool.fetchrow(
                "SELECT chapter_key FROM chunks WHERE document_id=$1 AND anchor=$2",
                doc_uuid, anchor)
            chapter_key = row["chapter_key"] if row else None
        if chapter_key is None:
            row = await pool.fetchrow(
                "SELECT chapter_key FROM chunks WHERE document_id=$1 AND chapter_key IS NOT NULL "
                "ORDER BY position LIMIT 1", doc_uuid)
            if row is None:
                raise HTTPException(status_code=404, detail="Document has no readable passages")
            chapter_key = row["chapter_key"]

        passage_rows = await pool.fetch(
            """SELECT id, anchor, chapter_key, chapter_label, unit_label, reference, content
               FROM chunks WHERE document_id=$1 AND chapter_key=$2 ORDER BY position""",
            doc_uuid, chapter_key,
        )
        if not passage_rows:
            raise HTTPException(status_code=404, detail="Chapter not found")

        key_rows = await pool.fetch(
            """SELECT chapter_key FROM chunks WHERE document_id=$1 AND chapter_key IS NOT NULL
               GROUP BY chapter_key ORDER BY min(position)""",
            doc_uuid,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_document_reader query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    keys = [r["chapter_key"] for r in key_rows]
    idx = keys.index(chapter_key) if chapter_key in keys else 0
    prev_key = keys[idx - 1] if idx > 0 else None
    next_key = keys[idx + 1] if idx + 1 < len(keys) else None

    passages = [
        ReaderPassage(
            id=str(r["id"]), anchor=r["anchor"], chapter_key=r["chapter_key"],
            chapter_label=r["chapter_label"], unit_label=r["unit_label"],
            reference=r["reference"], content=r["content"],
        ) for r in passage_rows
    ]
    return ReaderChapter(
        document=_document_response(doc_row), chapter_key=chapter_key,
        chapter_label=passage_rows[0]["chapter_label"], passages=passages,
        prev_chapter_key=prev_key, next_chapter_key=next_key, highlight_anchor=anchor,
    )
