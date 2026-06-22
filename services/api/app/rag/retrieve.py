"""Candidate chunk retrieval via Qdrant vector search + Supabase FTS with RRF merge."""
import asyncio
import logging
import math
from dataclasses import dataclass

import asyncpg

from app.config import settings
from app.db import get_pool
from app.rag.qdrant_client import QDRANT_COLLECTION, get_qdrant_client

logger = logging.getLogger(__name__)

_RRF_K = 60              # standard RRF constant
_PER_STRATEGY_TOP_K = 3  # top-K from each strategy guaranteed into reranker candidate set

_MAX_COSINE_DISTANCE = 0.50
# Qdrant scores are cosine similarity (1=identical); threshold is the mirror of distance
_QDRANT_SCORE_THRESHOLD = 1.0 - _MAX_COSINE_DISTANCE  # 0.50


@dataclass
class ChunkCandidate:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    rrf_score: float
    anchor: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vec_to_str(vec: list[float]) -> str:
    """Format a float list as a pgvector literal: [f1,f2,...] (used by FTS query path)."""
    if any(not math.isfinite(v) for v in vec):
        raise ValueError("Embedding vector contains non-finite values")
    return "[" + ",".join(str(v) for v in vec) + "]"


async def _get_excluded_ids(pool: asyncpg.Pool, user_id: str) -> list[str]:
    """Return chunk IDs the user has thumbs-downed. Empty list if none or on error."""
    try:
        rows = await pool.fetch(
            "SELECT chunk_id::text FROM chunk_feedback WHERE user_id = $1 AND feedback = 'down'",
            user_id,
        )
        return [r["chunk_id"] for r in rows]
    except Exception as exc:
        logger.warning("_get_excluded_ids failed: %s", exc)
        return []


async def _search_vector(
    collection: str,
    vec: list[float],
    limit: int,
    label: str,
    excluded_ids: list[str],
) -> list[dict]:
    """Cosine-similarity vector search via Qdrant with native collection filtering.

    The collection filter is applied inside the HNSW traversal — only nodes
    belonging to the target collection are visited, eliminating the cross-
    collection post-scan that made pgvector retrieval slow.
    """
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

    rows = [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "reference": r.payload.get("reference"),
            "collection": r.payload["collection"],
            "document_id": r.payload["document_id"],
            "document_title": r.payload["document_title"],
            "author": r.payload.get("author"),
            "anchor": r.payload.get("anchor"),
        }
        for r in response.points
    ]
    logger.debug(
        "vector search (%s): collection=%s returned %d rows",
        label, collection, len(rows),
    )
    return rows


async def _search_fts(
    pool: asyncpg.Pool,
    collection: str,
    user_id: str,
    query_text: str,
    limit: int,
) -> list[dict]:
    """Full-text search against search_vector using plainto_tsquery (Supabase/Postgres)."""
    query = """
        SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.document_id::text AS document_id,
               d.title AS document_title, d.author, d.collection
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.collection = $1
          AND c.search_vector @@ plainto_tsquery('english', $3)
          AND NOT EXISTS (
              SELECT 1 FROM chunk_feedback cf
              WHERE cf.chunk_id = c.id
                AND cf.user_id = $2
                AND cf.feedback = 'down'
          )
        ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $3)) DESC
        LIMIT $4
    """
    rows = await pool.fetch(query, collection, user_id, query_text, limit)
    logger.debug("fts search: collection=%s returned %d rows", collection, len(rows))
    return [dict(r) for r in rows]


def _rrf_merge(result_lists: list[list[dict]], top_n: int) -> list[dict]:
    """Apply Reciprocal Rank Fusion across multiple ranked result lists.

    Each list contributes score = 1 / (_RRF_K + rank) for each chunk_id.
    Returns the top_n chunks by RRF score PLUS the top-_PER_STRATEGY_TOP_K from
    each individual strategy, deduplicated and sorted by RRF score descending.

    The per-strategy guarantee prevents RRF's consistency-bias from burying
    passages that rank #1 in one strategy but score only modestly across others.
    """
    scores: dict[str, float] = {}
    metadata: dict[str, dict] = {}

    for result_list in result_lists:
        for rank_0, row in enumerate(result_list):
            rank = rank_0 + 1
            chunk_id = str(row["id"])
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
            if chunk_id not in metadata:
                metadata[chunk_id] = {
                    "chunk_id": chunk_id,
                    "content": row["content"],
                    "reference": row["reference"],
                    "collection": row["collection"],
                    "document_id": str(row["document_id"]),
                    "document_title": row["document_title"],
                    "author": row["author"],
                    "anchor": row.get("anchor"),
                }

    sorted_by_rrf = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    selected_ids: set[str] = set(sorted_by_rrf[:top_n])

    for result_list in result_lists:
        for row in result_list[:_PER_STRATEGY_TOP_K]:
            selected_ids.add(str(row["id"]))

    final_sorted = sorted(selected_ids, key=lambda cid: scores.get(cid, 0.0), reverse=True)
    merged = []
    for cid in final_sorted:
        entry = dict(metadata[cid])
        entry["rrf_score"] = scores[cid]
        merged.append(entry)
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def retrieve_candidates(
    query_text: str,
    query_vec: list[float],
    hyde_vec: list[float] | None,
    extra_vecs: list[list[float]],
    collection: str,
    quota: int,
    user_id: str,
) -> list[ChunkCandidate]:
    """Retrieve candidate chunks for a single collection using parallel
    search strategies (HyDE + query vector search via Qdrant, full-text via
    Supabase), then merge with Reciprocal Rank Fusion.

    Args:
        query_text:  Raw user query string (used for full-text search).
        query_vec:   Embedding of the raw query.
        hyde_vec:    Embedding of the HyDE hypothetical passage, or None to skip.
        extra_vecs:  Embeddings of additional per-collection HyDE passages (e.g. bible genres).
        collection:  The collection name to filter by.
        quota:       Final desired chunk count; returns up to quota * candidate_multiplier.
        user_id:     Authenticated user — chunks with 'down' feedback are excluded.
    """
    pool = get_pool()
    n = quota * settings.candidate_multiplier

    # Single query for all downvoted chunk IDs — applied to every Qdrant search.
    excluded_ids: list[str] = []
    if pool is not None:
        excluded_ids = await _get_excluded_ids(pool, user_id)

    coros: list = []
    labels: list[str] = []

    if hyde_vec is not None:
        coros.append(_search_vector(collection, hyde_vec, n, "hyde", excluded_ids))
        labels.append("hyde")

    coros.append(_search_vector(collection, query_vec, n, "query", excluded_ids))
    labels.append("query")

    for i, ev in enumerate(extra_vecs):
        coros.append(_search_vector(collection, ev, n, f"extra_{i}", excluded_ids))
        labels.append(f"extra_{i}")

    if pool is not None:
        coros.append(_search_fts(pool, collection, user_id, query_text, n))
        labels.append("fts")
    else:
        logger.warning(
            "retrieve_candidates: no DB pool — skipping FTS for collection '%s'", collection
        )

    raw_results = await asyncio.gather(*coros, return_exceptions=True)

    result_lists: list[list[dict]] = []
    for label, result in zip(labels, raw_results):
        if isinstance(result, BaseException):
            logger.warning(
                "retrieve_candidates: search '%s' failed for collection '%s': %s",
                label, collection, result,
            )
        else:
            result_lists.append(result)

    if not result_lists:
        logger.warning(
            "retrieve_candidates: all searches failed for collection '%s'", collection
        )
        return []

    merged = _rrf_merge(result_lists, top_n=n)

    candidates = [
        ChunkCandidate(
            chunk_id=entry["chunk_id"],
            content=entry["content"],
            reference=entry["reference"],
            collection=entry["collection"],
            document_id=entry["document_id"],
            document_title=entry["document_title"],
            author=entry["author"],
            rrf_score=entry["rrf_score"],
            anchor=entry.get("anchor"),
        )
        for entry in merged
    ]

    logger.info(
        "retrieve_candidates: collection=%s quota=%d returning %d candidates",
        collection, quota, len(candidates),
    )
    return candidates
