"""Minimum-results floor — last-resort fallback when scoring excludes everything.

Called only when the normal pipeline (rerank -> dedup -> collection_guarantee ->
quota_cap) produced zero results. Without this, a borderline query where the
reranker scores every candidate below the include threshold returns a silent
"no results" screen. Surfacing the best-effort top candidates (with their real,
low scores shown in the UI) is strictly better than an empty result.
"""
from __future__ import annotations

import logging

from app.rag.steps.types import RankedChunk

logger = logging.getLogger(__name__)

_FLOOR_N = 5


def run(ranked: list[RankedChunk], quota: int) -> list[RankedChunk]:
    """Return up to min(quota, _FLOOR_N) best-scoring chunks, one per document title.

    `ranked` is the full scored list from the reranker, already sorted descending
    by reranker_score. `include` is intentionally ignored here — the whole point is
    to surface candidates the reranker excluded, since nothing else survived.
    """
    limit = min(quota, _FLOOR_N)
    seen_titles: set[str] = set()
    floored: list[RankedChunk] = []
    for chunk in ranked:  # already sorted desc by reranker_score
        if chunk.document_title in seen_titles:
            continue
        seen_titles.add(chunk.document_title)
        floored.append(chunk)
        if len(floored) >= limit:
            break

    if floored:
        logger.info(
            "min_floor: normal pipeline empty; surfacing %d best-effort chunk(s) "
            "(top_score=%.2f)",
            len(floored),
            floored[0].reranker_score,
        )
    return floored
