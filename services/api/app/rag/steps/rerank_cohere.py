"""Global re-ranking using Cohere Rerank v4.0 Pro."""
from __future__ import annotations

import logging

import cohere

from app.config import settings
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import ChunkCandidate, RankedChunk

logger = logging.getLogger(__name__)

_client: cohere.AsyncClientV2 | None = None


def init_cohere() -> None:
    global _client
    if settings.cohere_api_key:
        _client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)


async def close_cohere() -> None:
    global _client
    _client = None


async def run(
    candidates: dict[str, list[ChunkCandidate]],
    query: str,
    quota: int,
    cost_tracker: CostTracker,
) -> list[RankedChunk]:
    """Rerank all candidates globally using Cohere Rerank v4.0 Pro."""
    if _client is None:
        raise RuntimeError(
            "Cohere client not initialized. Set COHERE_API_KEY environment variable."
        )

    # Flatten candidates with a per-collection cap so HyDE pipelines don't
    # send hundreds of documents to Cohere when extra RRF strategies fire.
    max_per_col = quota * settings.candidate_multiplier
    all_candidates: list[ChunkCandidate] = []
    for col_cands in candidates.values():
        all_candidates.extend(col_cands[:max_per_col])

    if not all_candidates:
        return []

    documents = [
        f"[{c.reference or c.collection}] {c.content}"
        for c in all_candidates
    ]

    response = await _client.rerank(
        model="rerank-v4.0-pro",
        query=query,
        documents=documents,
        top_n=len(all_candidates),
    )

    cost_tracker.record_cohere("rerank_cohere")

    score_map: dict[int, float] = {
        r.index: r.relevance_score for r in response.results
    }

    ranked: list[RankedChunk] = []
    for i, candidate in enumerate(all_candidates):
        score = score_map.get(i, 0.0)
        ranked.append(RankedChunk(
            chunk_id=candidate.chunk_id,
            content=candidate.content,
            reference=candidate.reference,
            collection=candidate.collection,
            document_id=candidate.document_id,
            document_title=candidate.document_title,
            author=candidate.author,
            reranker_score=score,
            include=score >= 0.25,
            anchor=candidate.anchor,
            position=candidate.position,
        ))

    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return ranked
