"""Full-text search per collection via Supabase/Postgres."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db import get_pool

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


async def _search_fts(collection: str, query_text: str, limit: int) -> list[dict]:
    pool = get_pool()
    if pool is None:
        return []
    rows = await pool.fetch(_SQL, collection, query_text, limit)
    return [dict(r) for r in rows]


async def run(
    query: str,
    collections: list[str],
    quota: int,
    user_id: str | None = None,
) -> dict[str, list[dict]]:
    """Run FTS for all collections.

    user_id is accepted but unused (retained for caller compatibility).
    """
    n = quota * settings.candidate_multiplier

    results = await asyncio.gather(
        *[_search_fts(col, query, n) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[dict]] = {}
    for col, result in zip(collections, results):
        if isinstance(result, BaseException):
            logger.warning("retrieve_fts: %s failed: %s", col, result)
        elif result:
            output[col] = result
    return output
