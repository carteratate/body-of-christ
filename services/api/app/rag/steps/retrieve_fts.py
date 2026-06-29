"""Full-text search per collection via Supabase/Postgres."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db import get_pool

logger = logging.getLogger(__name__)


async def _search_fts(
    collection: str,
    query_text: str,
    user_id: str | None,
    limit: int,
) -> list[dict]:
    pool = get_pool()
    if pool is None:
        return []

    if user_id is not None:
        sql = """
            SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.position,
                   c.annotation, c.document_id::text AS document_id,
                   d.title AS document_title, d.author, d.collection
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.collection = $1
              AND c.search_vector @@ plainto_tsquery('english', $3)
              AND NOT EXISTS (
                  SELECT 1 FROM chunk_feedback cf
                  WHERE cf.chunk_id = c.id AND cf.user_id = $2 AND cf.feedback = 'down'
              )
            ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $3)) DESC
            LIMIT $4
        """
        rows = await pool.fetch(sql, collection, user_id, query_text, limit)
    else:
        sql = """
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
        rows = await pool.fetch(sql, collection, query_text, limit)

    return [dict(r) for r in rows]


async def run(
    query: str,
    collections: list[str],
    quota: int,
    user_id: str | None,
) -> dict[str, list[dict]]:
    """Run FTS for all collections. user_id=None skips downvote exclusion."""
    n = quota * settings.candidate_multiplier

    results = await asyncio.gather(
        *[_search_fts(col, query, user_id, n) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[dict]] = {}
    for col, result in zip(collections, results):
        if isinstance(result, BaseException):
            logger.warning("retrieve_fts: %s failed: %s", col, result)
        elif result:
            output[col] = result
    return output
