import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter()


class SourceDocument(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    chunk_count: int


class SourcesResponse(BaseModel):
    sources: list[SourceDocument]


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(
    user: AuthUser = Depends(get_current_user),
) -> SourcesResponse:
    """Return all documents in the corpus with passage counts, ordered by collection then year."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        rows = await pool.fetch(
            """
            SELECT d.id, d.collection, d.title, d.author, d.year,
                   NULLIF(d.translation, '') AS translation,
                   COUNT(c.id)::int AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.collection, d.year NULLS LAST, d.title
            """,
        )
    except Exception as exc:
        logger.error("get_sources query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return SourcesResponse(
        sources=[
            SourceDocument(
                id=str(row["id"]),
                collection=row["collection"],
                title=row["title"],
                author=row["author"] or None,
                year=row["year"],
                translation=row["translation"],
                chunk_count=row["chunk_count"],
            )
            for row in rows
        ]
    )
