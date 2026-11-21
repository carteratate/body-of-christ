import logging
import time
from typing import Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import card_notes, corpus_schema
from app.db import POOL_ACQUIRE_TIMEOUT_SECONDS, get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.corpus import OverviewNote
from app.reader_access import source_url

logger = logging.getLogger(__name__)
router = APIRouter()

_sources_cache: "SourcesResponse | None" = None
_sources_cache_ts: float = 0.0
_SOURCES_TTL: float = 3600.0

# chunk_count is precomputed at publication (migration 0037). COALESCE counts chunks
# only for a document with no current outline. Retired documents and passages (0042,
# corpus cleanup 2.4a) are left out; `{visible_c}` and `{visible_d}` are empty without
# 0042. A retirement shows here after the API restart that follows a publish (4.1b).
_SOURCES_SQL = """
    SELECT d.id::text AS id, d.collection, d.title, d.author, d.year,
           NULLIF(d.translation, '') AS translation, d.metadata,
           COALESCE(d.chunk_count,
                    (SELECT count(*) FROM chunks c WHERE c.document_id = d.id{visible_c}))::int AS chunk_count
    FROM documents d WHERE true{visible_d}
    ORDER BY d.collection, d.year NULLS LAST, d.title
"""
# The same on a database without 0037, so the API can deploy before it is applied.
_PRE_OUTLINE_SOURCES_SQL = """
    SELECT d.id::text AS id, d.collection, d.title, d.author, d.year,
           NULLIF(d.translation, '') AS translation, d.metadata,
           (SELECT count(*) FROM chunks c WHERE c.document_id = d.id{visible_c})::int AS chunk_count
    FROM documents d WHERE true{visible_d}
    ORDER BY d.collection, d.year NULLS LAST, d.title
"""


def _visible(sql: str, schema: corpus_schema.CorpusSchema) -> str:
    return (sql.replace("{visible_c}", schema.visible("c"))
               .replace("{visible_d}", schema.visible("d")))


# Excerpt-only documents (issue #265). Read on every request, not cached with the
# list, so a reader-access sync shows here at once instead of after the hour's TTL.
_EXCERPT_SQL = "SELECT id::text AS id FROM documents WHERE reader_access = 'excerpt'"


class SourceDocument(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    metadata: Optional[dict] = None
    chunk_count: int
    # "excerpt": no reader; the Library links to `source_url` instead.
    reader_access: Literal["full", "excerpt"] = "full"
    source_url: Optional[str] = None
    # The document-wide notes (4.4), which the Library row of an excerpt-only document
    # shows, since its overview answers 403. None for a document from before 4.4.
    overview_notes: Optional[list[OverviewNote]] = None


class SourcesResponse(BaseModel):
    sources: list[SourceDocument]


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(user: AuthUser = Depends(get_current_user)) -> SourcesResponse:
    """Return all documents in the corpus with passage counts.

    Every row carries a real document_id (the reader opens it directly). Bible is
    returned as book-level documents grouped by translation on the frontend.

    The document list is cached in-memory for 1 hour since the corpus changes only
    at ingestion time; reader access is read fresh on every request.
    """
    corpus = _cached_corpus()
    pool = get_pool()
    if not pool:
        if corpus is not None:
            return corpus
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS) as conn:
            if corpus is None:
                corpus = await _load_corpus(conn)
            try:
                excerpt_ids = {r["id"] for r in await conn.fetch(_EXCERPT_SQL)}
            except asyncpg.UndefinedColumnError:
                excerpt_ids = set()  # 0041 not applied: every document reads as full
    except Exception as exc:
        if corpus is None:
            logger.error("get_sources query failed (%s)", exc.__class__.__name__)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
        # The cached list still serves; the reader route enforces access on its own.
        logger.warning("reader access read failed (%s); serving the cached Library",
                       exc.__class__.__name__)
        excerpt_ids = set()

    if not excerpt_ids:
        return corpus
    return SourcesResponse(sources=[
        s.model_copy(update={
            "reader_access": "excerpt",
            "source_url": source_url(s.collection, s.metadata),
        }) if s.id in excerpt_ids else s
        for s in corpus.sources
    ])


def _cached_corpus() -> SourcesResponse | None:
    """Every document, cached for an hour: the list changes only at publication."""
    if _sources_cache is not None and (time.monotonic() - _sources_cache_ts) < _SOURCES_TTL:
        return _sources_cache
    return None


async def _load_corpus(conn) -> SourcesResponse:
    global _sources_cache, _sources_cache_ts

    async def load(schema: corpus_schema.CorpusSchema):
        try:
            return await conn.fetch(_visible(_SOURCES_SQL, schema))
        except asyncpg.UndefinedColumnError as exc:
            if "chunk_count" not in str(exc):
                raise
            return await conn.fetch(_visible(_PRE_OUTLINE_SOURCES_SQL, schema))

    rows = await corpus_schema.run_with_fallback(load, conn)
    sources = [
        SourceDocument(
            id=r["id"], collection=r["collection"], title=r["title"],
            author=r["author"] or None, year=r["year"], translation=r["translation"],
            metadata=dict(r["metadata"]) if r["metadata"] else None,
            chunk_count=r["chunk_count"],
            overview_notes=card_notes.overview_notes(r["metadata"]),
        ) for r in rows
    ]
    response = SourcesResponse(sources=sources)
    _sources_cache = response
    _sources_cache_ts = time.monotonic()
    return response
