"""Thin wrapper around app.rag.dedup for the steps interface."""
from __future__ import annotations

from app.rag.steps.types import RankedChunk


async def run(ranked: list[RankedChunk]) -> list[RankedChunk]:
    """Apply position+cosine dedup and per-title cap.

    Delegates to the canonical implementation in app.rag.dedup.
    Input must already be sorted descending by reranker_score.
    """
    from app.rag.dedup import apply_dedup
    return await apply_dedup(ranked)


# Backward-compat alias so any future import from this module works uniformly.
apply_dedup = run
