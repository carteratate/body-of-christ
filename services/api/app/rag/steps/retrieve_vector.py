"""Qdrant vector search per collection across all HyDE + query vectors."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db import get_pool
from app.rag.qdrant_client import QDRANT_COLLECTION, get_qdrant_client

logger = logging.getLogger(__name__)

_MAX_COSINE_DISTANCE = 0.50
_QDRANT_SCORE_THRESHOLD = 1.0 - _MAX_COSINE_DISTANCE


async def _get_excluded_ids(user_id: str) -> list[str]:
    pool = get_pool()
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            "SELECT chunk_id::text FROM chunk_feedback WHERE user_id = $1 AND feedback = 'down'",
            user_id,
        )
        return [r["chunk_id"] for r in rows]
    except Exception as exc:
        logger.warning("retrieve_vector: _get_excluded_ids failed: %s", exc)
        return []


async def _search_vector(
    collection: str,
    vec: list[float],
    limit: int,
    label: str,
    excluded_ids: list[str],
) -> list[dict]:
    from qdrant_client.models import FieldCondition, Filter, HasIdCondition, MatchValue

    client = get_qdrant_client()
    if client is None:
        raise RuntimeError("Qdrant client not initialised")

    must_not = [HasIdCondition(has_id=excluded_ids)] if excluded_ids else None
    response = await client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vec,
        query_filter=Filter(
            must=[FieldCondition(key="collection", match=MatchValue(value=collection))],
            must_not=must_not,
        ),
        limit=limit,
        with_payload=True,
        score_threshold=_QDRANT_SCORE_THRESHOLD,
    )
    return [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "reference": r.payload.get("reference"),
            "collection": r.payload["collection"],
            "document_id": r.payload["document_id"],
            "document_title": r.payload["document_title"],
            "author": r.payload.get("author"),
            "anchor": r.payload.get("anchor"),
            "position": None,
            "annotation": None,
        }
        for r in response.points
    ]


async def run(
    query_vec: list[float],
    hyde_vecs: dict[str, list[list[float]]],
    collections: list[str],
    quota: int,
    user_id: str | None,
) -> dict[str, list[list[dict]]]:
    """Run all Qdrant vector searches per collection.

    hyde_vecs may be {} (S4/hyde_none) — falls back to query_vec only.
    Returns col → list of per-strategy result lists (input to rrf.run).
    """
    excluded_ids: list[str] = []
    if user_id is not None:
        excluded_ids = await _get_excluded_ids(user_id)

    n = quota * settings.candidate_multiplier

    async def _search_collection(col: str) -> tuple[str, list[list[dict]]]:
        col_vecs = hyde_vecs.get(col, [])
        coros = []
        labels = []
        for i, vec in enumerate(col_vecs):
            label = "hyde" if i == 0 else f"hyde_{i}"
            coros.append(_search_vector(col, vec, n, label, excluded_ids))
            labels.append(label)
        coros.append(_search_vector(col, query_vec, n, "query", excluded_ids))
        labels.append("query")

        raw = await asyncio.gather(*coros, return_exceptions=True)
        strategy_lists = []
        for label, result in zip(labels, raw):
            if isinstance(result, BaseException):
                logger.warning("retrieve_vector: %s/%s failed: %s", col, label, result)
            else:
                strategy_lists.append(result)
        return col, strategy_lists

    results = await asyncio.gather(
        *[_search_collection(col) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[list[dict]]] = {}
    for item in results:
        if isinstance(item, BaseException):
            logger.warning("retrieve_vector: collection search failed: %s", item)
            continue
        col, strategy_lists = item
        if strategy_lists:
            output[col] = strategy_lists
    return output
