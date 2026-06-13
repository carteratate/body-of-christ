"""Candidate chunk retrieval via dual vector search + full-text search with RRF merge."""
import asyncio
import logging
import math
from dataclasses import dataclass

import asyncpg

from app.config import settings
from app.db import get_pool

logger = logging.getLogger(__name__)

_RRF_K = 60              # standard RRF constant
_PER_STRATEGY_TOP_K = 3  # top-K from each strategy guaranteed into reranker candidate set


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vec_to_str(vec: list[float]) -> str:
    """Format a float list as a pgvector literal: [f1,f2,...]"""
    if any(not math.isfinite(v) for v in vec):
        raise ValueError("Embedding vector contains non-finite values")
    return "[" + ",".join(str(v) for v in vec) + "]"


_MAX_COSINE_DISTANCE = 0.50  # filter chunks with cosine similarity below 50%
_HNSW_EF_SEARCH = 150       # wider beam search for better recall (default ~40)


async def _search_vector(
    pool: asyncpg.Pool,
    collection: str,
    user_id: str,
    vec: list[float],
    limit: int,
    label: str,
) -> list[asyncpg.Record]:
    """Cosine-similarity vector search against content_embedding.

    Sets ef_search for better HNSW recall and excludes chunks beyond the
    maximum cosine distance threshold.
    Returns up to *limit* rows ordered by distance ascending (closest first).
    """
    sql = """
        SELECT c.id, c.content, c.reference, c.document_id,
               d.title AS document_title, d.author, d.collection,
               c.content_embedding <=> $3::vector AS distance
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.collection = $1
          AND c.content_embedding IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM chunk_feedback cf
              WHERE cf.chunk_id = c.id
                AND cf.user_id = $2
                AND cf.feedback = 'down'
          )
        ORDER BY c.content_embedding <=> $3::vector
        LIMIT $4
    """
    vec_str = _vec_to_str(vec)
    async with pool.acquire() as conn:
        await conn.execute(f"SET hnsw.ef_search = {_HNSW_EF_SEARCH}")
        rows = await conn.fetch(sql, collection, user_id, vec_str, limit)
    # Drop chunks that are too far from the query vector
    rows = [r for r in rows if r["distance"] < _MAX_COSINE_DISTANCE]
    logger.debug(
        "vector search (%s): collection=%s returned %d rows (after distance filter)",
        label, collection, len(rows),
    )
    return rows


async def _search_fts(
    pool: asyncpg.Pool,
    collection: str,
    user_id: str,
    query_text: str,
    limit: int,
) -> list[asyncpg.Record]:
    """Full-text search against search_vector using plainto_tsquery."""
    query = """
        SELECT c.id, c.content, c.reference, c.document_id,
               d.title AS document_title, d.author, d.collection,
               ts_rank(c.search_vector, plainto_tsquery('english', $3)) AS rank
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
        ORDER BY rank DESC
        LIMIT $4
    """
    rows = await pool.fetch(query, collection, user_id, query_text, limit)
    logger.debug("fts search: collection=%s returned %d rows", collection, len(rows))
    return list(rows)


def _rrf_merge(
    result_lists: list[list[asyncpg.Record]],
    top_n: int,
) -> list[dict]:
    """Apply Reciprocal Rank Fusion across multiple ranked result lists.

    Each list contributes score = 1 / (_RRF_K + rank) for each chunk_id.
    Returns the top_n chunks by RRF score PLUS the top-_PER_STRATEGY_TOP_K from
    each individual strategy, deduplicated and sorted by RRF score descending.

    The per-strategy guarantee prevents RRF's consistency-bias from burying
    passages that rank #1 in one strategy (e.g. the HyDE vector) but score
    only modestly across the others. The reranker sees them and can award them
    correctly.
    """
    scores: dict[str, float] = {}
    # Carry the first occurrence of metadata per chunk_id so we can build
    # ChunkCandidates after merging.
    metadata: dict[str, dict] = {}

    for result_list in result_lists:
        for rank_0, row in enumerate(result_list):
            rank = rank_0 + 1  # 1-based
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
                }

    # Top-N by aggregate RRF score
    sorted_by_rrf = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    selected_ids: set[str] = set(sorted_by_rrf[:top_n])

    # Per-strategy champions: guarantee top-K from each individual ranked list
    # reaches the reranker regardless of cross-strategy aggregate score.
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
    search strategies (HyDE, query, expanded queries, full-text), then
    merge with Reciprocal Rank Fusion.

    Args:
        query_text:  Raw user query string (used for full-text search).
        query_vec:   Embedding of the raw query.
        hyde_vec:    Embedding of the HyDE hypothetical passage, or None to skip.
        extra_vecs:  Embeddings of expanded query variants (may be empty).
        collection:  The documents.collection value to filter by.
        quota:       Final desired chunk count (re-ranker will trim to this).
                     This function returns up to quota * settings.candidate_multiplier
                     candidates.
        user_id:     Authenticated user — chunks with 'down' feedback are excluded.

    Returns:
        List of ChunkCandidate sorted by RRF score descending.
    """
    pool = get_pool()
    if pool is None:
        logger.error("retrieve_candidates called before DB pool was initialised")
        return []

    n = quota * settings.candidate_multiplier

    # Build coroutines. HyDE and expanded-query paths are skipped when unavailable.
    coros: list = []
    labels: list[str] = []

    if hyde_vec is not None:
        coros.append(_search_vector(pool, collection, user_id, hyde_vec, n, "hyde"))
        labels.append("hyde")

    coros.append(_search_vector(pool, collection, user_id, query_vec, n, "query"))
    labels.append("query")

    for i, ev in enumerate(extra_vecs):
        coros.append(_search_vector(pool, collection, user_id, ev, n, f"expand_{i}"))
        labels.append(f"expand_{i}")

    coros.append(_search_fts(pool, collection, user_id, query_text, n))
    labels.append("fts")

    raw_results = await asyncio.gather(*coros, return_exceptions=True)

    # Collect non-error result lists.
    result_lists: list[list[asyncpg.Record]] = []
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
        )
        for entry in merged
    ]

    logger.info(
        "retrieve_candidates: collection=%s quota=%d returning %d candidates",
        collection, quota, len(candidates),
    )

    # Option C: if annotation_embedding data exists for this collection, add a
    # fourth search path here. Check with:
    #   SELECT EXISTS(SELECT 1 FROM chunks c JOIN documents d ON c.document_id=d.id
    #                 WHERE d.collection=$1 AND c.annotation_embedding IS NOT NULL)
    # If True, add annotation_embedding vector search with query_vec and merge into RRF.
    # At V2 launch this will always be False; no code change needed to activate.

    return candidates
