"""Inject best chunk for any selected collection absent after dedup."""
from __future__ import annotations

from app.rag.steps.types import RankedChunk

_GUARANTEE_MIN_SCORE = 0.25


def run(
    deduped: list[RankedChunk],
    all_scored: list[RankedChunk],
    collections: list[str],
) -> list[RankedChunk]:
    """Ensure each selected collection has at least one result if it scored above threshold.

    For any collection that is absent from `deduped`, inject the highest-scoring
    chunk from `all_scored` whose reranker_score >= _GUARANTEE_MIN_SCORE.
    """
    represented = {r.collection for r in deduped}
    result = list(deduped)
    for col in collections:
        if col not in represented:
            best = next(
                (
                    r
                    for r in all_scored
                    if r.collection == col and r.reranker_score >= _GUARANTEE_MIN_SCORE
                ),
                None,
            )
            if best:
                result.append(best)
    return result
