"""Minimum-results floor — last-resort fallback when scoring excludes everything.

Called only when the normal pipeline (rerank -> dedup -> collection_guarantee ->
quota_cap) produced zero results. Without this, a borderline query where the
reranker scores every candidate below the include threshold returns a silent
"no results" screen. Surfacing the best-effort top candidates (with their real,
low scores shown in the UI) is strictly better than an empty result.
"""
from __future__ import annotations

import logging

from app.rag.dedup import chapter_grain_collections, source_key
from app.rag.steps.types import RankedChunk

logger = logging.getLogger(__name__)

_FLOOR_N = 5


def run(ranked: list[RankedChunk], quota: int) -> list[RankedChunk]:
    """Return up to min(quota, _FLOOR_N) best-scoring chunks, spread across sources.

    `ranked` is the full scored list from the reranker, already sorted descending
    by reranker_score. `include` is intentionally ignored here — the whole point is
    to surface candidates the reranker excluded, since nothing else survived.

    Two passes, because the floor's goal is the OPPOSITE of the per-source cap's.
    The cap limits repetition *within* a source; the floor maximises spread *across*
    sources on the "nothing scored well" screen. Using the cap's grain directly
    would let one collection own the whole floor: the Summa has 3,120 chapter keys,
    so five Summa articles would fill every slot and no other collection would
    appear at all — strictly worse than what this replaced.

    Pass 1 takes one chunk per work (the coarsest grain — `source_key` with an
    empty chapter grain, which forces its title branch). Note this spreads across
    WORKS, not collections: a multi-document collection can still own the whole
    floor if its works outscore everything else, exactly as before this change.
    Spreading across works is what keeps a single-document collection from doing
    so, which is the case that regressed here.

    Pass 2 then fills any slots pass 1 could not, using the finer chapter grain, so
    a search over a single chaptered collection still fills the floor from distinct
    articles instead of returning one lone result.
    """
    limit = min(quota, _FLOOR_N)
    chapter_grain = chapter_grain_collections(ranked)
    floored: list[RankedChunk] = []
    seen_fine: set[tuple[str, ...]] = set()
    seen_works: set[tuple[str, ...]] = set()

    # Pass 1 — one per work (see docstring: works, not collections).
    for chunk in ranked:  # already sorted desc by reranker_score
        if len(floored) >= limit:
            break
        work = source_key(chunk, frozenset())
        if work in seen_works:
            continue
        seen_works.add(work)
        seen_fine.add(source_key(chunk, chapter_grain))
        floored.append(chunk)

    # Pass 2 — fill remaining slots from distinct chapters of works already seen.
    if len(floored) < limit:
        taken = {chunk.chunk_id for chunk in floored}
        for chunk in ranked:
            if len(floored) >= limit:
                break
            if chunk.chunk_id in taken:
                continue
            fine = source_key(chunk, chapter_grain)
            if fine in seen_fine:
                continue
            seen_fine.add(fine)
            floored.append(chunk)
        # Pass 2 can add a chunk outscoring a pass-1 pick, and both the SSE stream
        # and persistence assume score-descending order.
        floored.sort(key=lambda chunk: chunk.reranker_score, reverse=True)

    if floored:
        logger.info(
            "min_floor: normal pipeline empty; surfacing %d best-effort chunk(s) "
            "(top_score=%.2f)",
            len(floored),
            floored[0].reranker_score,
        )
    return floored
