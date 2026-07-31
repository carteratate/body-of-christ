"""Full-text search per collection via Supabase/Postgres."""
from __future__ import annotations

import asyncio
import logging
import random

import asyncpg

from app.config import settings
from app.db import get_pool
from app.rag.steps import degradation

logger = logging.getLogger(__name__)

_SQL = """
    SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.position,
           c.annotation, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE d.collection = $1
      AND c.search_vector @@ plainto_tsquery('english', $2)
    ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $2)) DESC
    LIMIT $3
"""


_TRANSIENT_CONNECTION_ERRORS = (
    asyncpg.PostgresConnectionError,
    ConnectionError,
    TimeoutError,
)


async def _search_fts(collection: str, query_text: str, limit: int) -> list[dict]:
    """Search one collection, reacquiring once after a transient pooler failure.

    A long judge/reranker call can leave the DB pool idle long enough for Supabase's
    pooler to retire its socket. asyncpg discards a broken connection when the first
    fetch fails; the retry therefore acquires a fresh connection. Semantic SQL and
    programming errors are deliberately not retried.
    """
    for attempt in range(2):
        pool = get_pool()
        if pool is None:
            degradation.record(
                "retrieve_fts", "pool_unavailable", "path_omitted",
                scope=collection,
            )
            return []
        try:
            rows = await pool.fetch(_SQL, collection, query_text, limit)
            if attempt:
                logger.info("retrieve_fts: %s recovered on fresh connection", collection)
            return [dict(r) for r in rows]
        except _TRANSIENT_CONNECTION_ERRORS:
            if attempt:
                raise
            # Small independent jitter prevents every collection from immediately
            # stampeding the pool for replacement sockets.
            await asyncio.sleep(0.15 + random.random() * 0.20)
    raise AssertionError("unreachable")


async def run(
    query: str,
    collections: list[str],
    quota: int,
    user_id: str | None = None,
    k: int | None = None,
) -> dict[str, list[dict]]:
    """Run FTS for all collections.

    user_id is accepted but unused (retained for caller compatibility).
    """
    n = k if k is not None else quota * settings.candidate_multiplier

    results = await asyncio.gather(
        *[_search_fts(col, query, n) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[dict]] = {}
    for col, result in zip(collections, results):
        if isinstance(result, BaseException):
            logger.warning("retrieve_fts: %s failed: %s", col, result)
            degradation.record(
                "retrieve_fts", type(result).__name__, "path_omitted",
                scope=col, details={"message": str(result)[:300]},
            )
        elif result:
            output[col] = result
    return output
