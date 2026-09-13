"""Thin wrapper around app.rag.dedup for the steps interface."""
from __future__ import annotations

from app.rag.steps.types import RankedChunk


async def run(
    ranked: list[RankedChunk], *, per_source_cap: int = 2,
    per_document_cap: int | None = None,
) -> list[RankedChunk]:
    """Apply position+cosine dedup and the per-source cap.

    Delegates to the canonical implementation in app.rag.dedup.
    Input must already be sorted descending by reranker_score.
    """
    from app.rag.dedup import apply_dedup
    return await apply_dedup(
        ranked,
        per_source_cap=per_source_cap,
        per_document_cap=per_document_cap,
    )


# Backward-compat alias so any future import from this module works uniformly.
apply_dedup = run
