"""Apply per-collection quota cap to final ranked results."""
from __future__ import annotations

from app.rag.steps.types import RankedChunk


def run(chunks: list[RankedChunk], quota: int) -> list[RankedChunk]:
    """Keep at most `quota` chunks per collection.

    Iterates chunks in order (assumed score-sorted descending); the first
    `quota` chunks seen for each collection are kept, the rest are dropped.
    """
    col_counts: dict[str, int] = {}
    final: list[RankedChunk] = []
    for chunk in chunks:
        col_counts[chunk.collection] = col_counts.get(chunk.collection, 0) + 1
        if col_counts[chunk.collection] <= quota:
            final.append(chunk)
    return final
