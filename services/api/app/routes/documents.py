import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.documents import DocumentResponse, ReaderChunk, ReaderResponse

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


@router.get("/documents/{doc_id}/reader", response_model=ReaderResponse)
async def get_document_reader(
    doc_id: str,
    chunk_id: str = Query(..., description="UUID of the chunk to highlight"),
    context: int = Query(default=10, ge=1, le=50, description="Chunks to show on each side of the target"),
    user: AuthUser = Depends(get_current_user),
) -> ReaderResponse:
    """Return a context window of chunks around a target chunk for the reader view."""
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")

    try:
        chunk_uuid = uuid.UUID(chunk_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid chunk_id: must be a UUID")

    # context range enforced by Query(ge=1, le=50) above

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Fetch document metadata
    try:
        doc_row = await pool.fetchrow(
            "SELECT id, collection, title, author, year, metadata FROM documents WHERE id = $1",
            doc_uuid,
        )
    except Exception as exc:
        logger.error("get_document_reader doc query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if doc_row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get the target chunk's position
    try:
        target_row = await pool.fetchrow(
            "SELECT position FROM chunks WHERE id = $1 AND document_id = $2",
            chunk_uuid,
            doc_uuid,
        )
    except Exception as exc:
        logger.error("get_document_reader chunk position query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if target_row is None:
        raise HTTPException(status_code=404, detail="Chunk not found in this document")

    position = target_row["position"]

    # Fetch chunks within ±context window
    try:
        chunk_rows = await pool.fetch(
            """
            SELECT id, position, reference, content
            FROM chunks
            WHERE document_id = $1 AND position BETWEEN $2 AND $3
            ORDER BY position ASC
            """,
            doc_uuid,
            position - context,
            position + context,
        )
    except Exception as exc:
        logger.error("get_document_reader context query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    # Count total chunks for the document metadata
    try:
        chunk_count_row = await pool.fetchrow(
            "SELECT count(*) AS cnt FROM chunks WHERE document_id = $1",
            doc_uuid,
        )
    except Exception as exc:
        logger.error("get_document_reader chunk_count query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    document = DocumentResponse(
        id=str(doc_row["id"]),
        collection=doc_row["collection"],
        title=doc_row["title"],
        author=doc_row["author"],
        year=doc_row["year"],
        metadata=doc_row["metadata"],
        chunk_count=chunk_count_row["cnt"],
    )

    chunks = [
        ReaderChunk(
            id=str(r["id"]),
            position=r["position"],
            reference=r["reference"],
            content=r["content"],
        )
        for r in chunk_rows
    ]

    # Nav pivot IDs for non-overlapping Prev/Next pages.
    # Next pivot = last_visible_pos + context + 1 (centers the next page just after the window)
    # Prev pivot = first_visible_pos - context - 1 (centers the prev page just before the window)
    actual_first_pos = chunk_rows[0]["position"] if chunk_rows else position
    actual_last_pos = chunk_rows[-1]["position"] if chunk_rows else position
    try:
        next_nav_row = await pool.fetchrow(
            "SELECT id FROM chunks WHERE document_id = $1 AND position = $2",
            doc_uuid,
            actual_last_pos + context + 1,
        )
        prev_nav_row = await pool.fetchrow(
            "SELECT id FROM chunks WHERE document_id = $1 AND position = $2",
            doc_uuid,
            actual_first_pos - context - 1,
        )
    except Exception as exc:
        logger.warning("get_document_reader nav query failed (%s)", exc.__class__.__name__)
        next_nav_row = None
        prev_nav_row = None

    return ReaderResponse(
        document=document,
        chunks=chunks,
        highlight_chunk_id=chunk_id,
        next_nav_chunk_id=str(next_nav_row["id"]) if next_nav_row else None,
        prev_nav_chunk_id=str(prev_nav_row["id"]) if prev_nav_row else None,
    )
