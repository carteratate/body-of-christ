"""Qdrant vector search per collection across all HyDE + query vectors."""
from __future__ import annotations

import asyncio
import logging
from typing import Mapping

from app.config import settings
from app.rag.collection_scope import CollectionScope
from app.rag.qdrant_client import (
    genre_indexed, get_qdrant_client, read_collection, searchable_indexed,
)
from app.rag.steps import degradation
from app.rag.steps.types import RetrievalPath

logger = logging.getLogger(__name__)

_MAX_COSINE_DISTANCE = 0.50
_QDRANT_SCORE_THRESHOLD = 1.0 - _MAX_COSINE_DISTANCE


async def _search_vector(
    scope: CollectionScope,
    vec: list[float],
    limit: int,
    label: str,
) -> list[dict]:
    from qdrant_client.models import FieldCondition, MatchValue

    collection = scope.collection

    client = get_qdrant_client()
    if client is None:
        raise RuntimeError("Qdrant client not initialised")

    # Only an explicit `searchable = false` hides a point (corpus cleanup 2.2b). A point
    # without the field does not match `must_not`, so it stays searchable; retired
    # passages are absent from a published collection. Strict mode refuses the filter
    # until the field is indexed, so it waits for the index.
    must_not = (
        [FieldCondition(key="searchable", match=MatchValue(value=False))]
        if await searchable_indexed() else None
    )
    response = await client.query_points(
        collection_name=read_collection(),
        query=vec,
        query_filter=scope.to_qdrant_filter(must_not, genre_indexed=await genre_indexed()),
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
            # The key searched, not the stored value (5.1b.1), so results come back in
            # the vocabulary the request used.
            "collection": collection,
            "document_id": payload["document_id"],
            "document_title": payload["document_title"],
            "author": payload.get("author"),
            "anchor": payload.get("anchor"),
            "chapter_key": payload.get("chapter_key"),
            # Present only for collections the payload reconcile has run for;
            # fetch_positions backfills it from Postgres for the rest.
            "unit_label": payload.get("unit_label"),
            # Written by 2.2w on every point; fetch_positions backfills a point without it.
            "voice": payload.get("voice"),
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
    scopes: Mapping[str, CollectionScope] | None = None,
) -> dict[str, list[RetrievalPath]]:
    """Run all Qdrant vector searches per collection.

    hyde_vecs may be {} (S4/hyde_none) — falls back to query_vec only.
    scopes narrows a collection to some genres or issuers (5.1a); a collection
    without one is searched whole.
    Returns col → ranked paths labeled as HyDE or original query.
    user_id is accepted but unused (retained for caller compatibility).
    """
    # Pipelines supply k from budget.retrieval_k(); None, for direct callers, falls
    # back to quota * candidate_multiplier.
    n = k if k is not None else quota * settings.candidate_multiplier

    async def _search_collection(col: str) -> tuple[str, list[RetrievalPath]]:
        scope = (scopes or {}).get(col) or CollectionScope(col)
        col_vecs = hyde_vecs.get(col, [])
        coros = []
        labels = []
        for i, vec in enumerate(col_vecs):
            label = "hyde" if i == 0 else f"hyde_{i}"
            coros.append(_search_vector(scope, vec, n, label))
            labels.append(label)
        coros.append(_search_vector(scope, query_vec, n, "query"))
        labels.append("query")

        raw = await asyncio.gather(*coros, return_exceptions=True)
        strategy_lists: list[RetrievalPath] = []
        for label, result in zip(labels, raw):
            if isinstance(result, BaseException):
                logger.warning("retrieve_vector: %s/%s failed: %s", col, label, result)
                degradation.record(
                    "retrieve_vector", type(result).__name__, "path_omitted",
                    scope=f"{col}/{label}", details={"message": str(result)[:300]},
                )
            else:
                strategy_lists.append(RetrievalPath(
                    family="query" if label == "query" else "hyde", rows=result,
                ))
        return col, strategy_lists

    results = await asyncio.gather(
        *[_search_collection(col) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[RetrievalPath]] = {}
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
