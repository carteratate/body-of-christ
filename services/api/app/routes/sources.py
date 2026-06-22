import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)
router = APIRouter()

_sources_cache: "SourcesResponse | None" = None
_sources_cache_ts: float = 0.0
_SOURCES_TTL: float = 3600.0


class SourceDocument(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    metadata: Optional[dict] = None
    chunk_count: int


class SourcesResponse(BaseModel):
    sources: list[SourceDocument]


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(user: AuthUser = Depends(get_current_user)) -> SourcesResponse:
    """Return all documents in the corpus with passage counts.

    Every row carries a real document_id (the reader opens it directly). Bible is
    returned as book-level documents grouped by translation on the frontend.

    Response is cached in-memory for 1 hour since the corpus changes only at
    ingestion time.
    """
    global _sources_cache, _sources_cache_ts

    now = time.monotonic()
    if _sources_cache is not None and (now - _sources_cache_ts) < _SOURCES_TTL:
        return _sources_cache

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        rows = await pool.fetch(
            """
            SELECT d.id::text AS id, d.collection, d.title, d.author, d.year,
                   NULLIF(d.translation, '') AS translation, d.metadata,
                   COUNT(c.id)::int AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.collection, d.year NULLS LAST, d.title
            """
        )
    except Exception as exc:
        logger.error("get_sources query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    sources = [
        SourceDocument(
            id=r["id"], collection=r["collection"], title=r["title"],
            author=r["author"] or None, year=r["year"], translation=r["translation"],
            metadata=dict(r["metadata"]) if r["metadata"] else None,
            chunk_count=r["chunk_count"],
        ) for r in rows
    ]
    response = SourcesResponse(sources=sources)
    _sources_cache = response
    _sources_cache_ts = now
    return response
