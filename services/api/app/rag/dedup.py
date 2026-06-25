"""Position+cosine dedup and per-title cap for post-scoring results.

apply_dedup(ranked) drops the lower-scorer in any pair from the same document
where abs(position_a - position_b) <= 2 AND cosine_similarity > 0.9, then
caps results at 2 per document_title. Input must already be sorted descending
by reranker_score (the pipeline's global sort precedes this call).
"""
from __future__ import annotations

import logging
import math

from app.rag.qdrant_client import QDRANT_COLLECTION, get_qdrant_client
from app.rag.rerank import RankedChunk

logger = logging.getLogger(__name__)

_COSINE_THRESHOLD = 0.9
_POSITION_PROXIMITY = 2
_PER_TITLE_CAP = 2


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


async def apply_dedup(ranked: list[RankedChunk]) -> list[RankedChunk]:
    """Drop cosine-close adjacent duplicates and apply per-title cap.

    Assumes `ranked` is already sorted descending by reranker_score.
    """
    # 1. Find pairs within _POSITION_PROXIMITY in the same document
    by_doc: dict[str, list[RankedChunk]] = {}
    for chunk in ranked:
        if chunk.include:
            by_doc.setdefault(chunk.document_id, []).append(chunk)

    close_pairs: list[tuple[str, str]] = []
    for chunks in by_doc.values():
        for i, a in enumerate(chunks):
            for b in chunks[i + 1:]:
                if (
                    a.position is not None
                    and b.position is not None
                    and abs(a.position - b.position) <= _POSITION_PROXIMITY
                ):
                    close_pairs.append((a.chunk_id, b.chunk_id))

    # 2. Fetch vectors for close pairs and compute cosine similarity
    to_drop: set[str] = set()
    if close_pairs:
        close_ids = {cid for pair in close_pairs for cid in pair}
        client = get_qdrant_client()
        if client is not None:
            try:
                points = await client.retrieve(
                    collection_name=QDRANT_COLLECTION,
                    ids=list(close_ids),
                    with_vectors=True,
                )
                vec_map: dict[str, list[float]] = {
                    str(p.id): p.vector
                    for p in points
                    if p.vector is not None
                }
                score_map = {r.chunk_id: r.reranker_score for r in ranked}
                for id_a, id_b in close_pairs:
                    if id_a in to_drop or id_b in to_drop:
                        continue
                    vec_a = vec_map.get(id_a)
                    vec_b = vec_map.get(id_b)
                    if vec_a is None or vec_b is None:
                        continue
                    if _cosine_sim(vec_a, vec_b) > _COSINE_THRESHOLD:
                        drop = (
                            id_a if score_map.get(id_a, 0.0) < score_map.get(id_b, 0.0) else id_b
                        )
                        to_drop.add(drop)
            except Exception as exc:
                logger.warning("apply_dedup: Qdrant vector fetch failed, skipping cosine check: %s", exc)

    # 3. Apply cosine dedup + per-title cap in one pass (input already score-sorted)
    title_counts: dict[str, int] = {}
    final: list[RankedChunk] = []
    for chunk in ranked:
        if not chunk.include or chunk.chunk_id in to_drop:
            continue
        count = title_counts.get(chunk.document_title, 0)
        if count < _PER_TITLE_CAP:
            title_counts[chunk.document_title] = count + 1
            final.append(chunk)
    return final
