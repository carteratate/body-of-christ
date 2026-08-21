"""Qdrant vector search per collection across all HyDE + query vectors."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.rag.qdrant_client import QDRANT_COLLECTION, get_qdrant_client
from app.rag.steps import degradation

logger = logging.getLogger(__name__)

_MAX_COSINE_DISTANCE = 0.50
_QDRANT_SCORE_THRESHOLD = 1.0 - _MAX_COSINE_DISTANCE


async def _search_vector(
    collection: str,
    vec: list[float],
    limit: int,
    label: str,
) -> list[dict]:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_qdrant_client()
    if client is None:
        raise RuntimeError("Qdrant client not initialised")

    response = await client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vec,
        query_filter=Filter(
            must=[FieldCondition(key="collection", match=MatchValue(value=collection))],
        ),
        limit=limit,
        with_payload=True,
        score_threshold=_QDRANT_SCORE_THRESHOLD,
    )
    results: list[dict] = []
    for r in response.points:
        payload = r.payload or {}
        # Drop only a malformed point (missing required field), not the whole
        # strategy result — a single bad Qdrant payload shouldn't erase recall.
        if any(payload.get(k) is None for k in ("content", "collection", "document_id", "document_title")):
            logger.warning("retrieve_vector: skipping point %s with incomplete payload", r.id)
            degradation.record(
                "retrieve_vector", "incomplete_payload", "candidate_omitted",
                scope=collection, details={"point_id": str(r.id), "strategy": label},
            )
            continue
        results.append({
            "id": str(r.id),
            "content": payload["content"],
            "reference": payload.get("reference"),
            "collection": payload["collection"],
            "document_id": payload["document_id"],
            "document_title": payload["document_title"],
            "author": payload.get("author"),
            "anchor": payload.get("anchor"),
            "chapter_key": payload.get("chapter_key"),
            # Present only for collections the payload reconcile has run for;
            # fetch_positions backfills it from Postgres for the rest.
            "unit_label": payload.get("unit_label"),
            "position": None,
            "annotation": None,
        })
    return results


async def run(
    query_vec: list[float],
    hyde_vecs: dict[str, list[list[float]]],
    collections: list[str],
    quota: int,
    user_id: str | None = None,
    k: int | None = None,
) -> dict[str, list[list[dict]]]:
    """Run all Qdrant vector searches per collection.

    hyde_vecs may be {} (S4/hyde_none) — falls back to query_vec only.
    Returns col → list of per-strategy result lists (input to rrf.run).
    user_id is accepted but unused (retained for caller compatibility).
    """
    # k is supplied by budget.retrieval_k() in dynamic modes; None keeps the
    # historical sizing that llm_only depends on for A/B comparability.
    n = k if k is not None else quota * settings.candidate_multiplier

    async def _search_collection(col: str) -> tuple[str, list[list[dict]]]:
        col_vecs = hyde_vecs.get(col, [])
        coros = []
        labels = []
        for i, vec in enumerate(col_vecs):
            label = "hyde" if i == 0 else f"hyde_{i}"
            coros.append(_search_vector(col, vec, n, label))
            labels.append(label)
        coros.append(_search_vector(col, query_vec, n, "query"))
        labels.append("query")

        raw = await asyncio.gather(*coros, return_exceptions=True)
        strategy_lists = []
        for label, result in zip(labels, raw):
            if isinstance(result, BaseException):
                logger.warning("retrieve_vector: %s/%s failed: %s", col, label, result)
                degradation.record(
                    "retrieve_vector", type(result).__name__, "path_omitted",
                    scope=f"{col}/{label}", details={"message": str(result)[:300]},
                )
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
            degradation.record(
                "retrieve_vector", type(item).__name__, "collection_omitted",
                details={"message": str(item)[:300]},
            )
            continue
        col, strategy_lists = item
        if strategy_lists:
            output[col] = strategy_lists
    return output
