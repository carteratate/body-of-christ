"""Batch-fetch chunk positions from DB for Qdrant-sourced candidates."""
from __future__ import annotations

import logging
import time

from app.db import get_pool
from app.rag.steps import degradation
from app.rag.steps.types import ChunkCandidate

logger = logging.getLogger(__name__)


def _collections_missing_positions(
    candidates: dict[str, list[ChunkCandidate]],
) -> list[str]:
    return [
        collection
        for collection, values in candidates.items()
        if any(candidate.position is None for candidate in values)
    ]


async def run(
    candidates: dict[str, list[ChunkCandidate]],
) -> dict[str, list[ChunkCandidate]]:
    """Fill in position=None candidates by querying Postgres, and drop orphans.

    Qdrant payloads omit position; FTS rows already have it. A position=None
    candidate whose id is absent from the `chunks` table is an orphaned Qdrant
    vector (stale from a prior ingest). Such candidates are dropped here: they
    have no `chunks` row, so surfacing them would break the reader, and
    persisting them fails the retrievals/bookmarks/feedback FK on chunks.id —
    aborting the whole search. Fills positions in place; returns a filtered dict.
    """
    pool = get_pool()
    if pool is None:
        for collection in _collections_missing_positions(candidates):
            degradation.record(
                "fetch_positions", "pool_unavailable", "enrichment_skipped",
                scope=collection,
            )
        return candidates

    missing_ids = [
        c.chunk_id
        for col_list in candidates.values()
        for c in col_list
        if c.position is None
    ]
    if not missing_ids:
        return candidates

    t0 = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            t_acquired = time.perf_counter()
            rows = await conn.fetch(
                "SELECT id::text, position, annotation FROM chunks WHERE id = ANY($1::uuid[])",
                missing_ids,
            )
            t_queried = time.perf_counter()
        pos_map = {r["id"]: r["position"] for r in rows}
        # .get() so a caller mocking this pool need not model every selected
        # column; test_fetch_positions_populates_annotation covers the real path.
        ann_map = {r["id"]: r.get("annotation") for r in rows}
        logger.info(
            "fetch_positions: ids=%d acquire=%.3fs query=%.3fs total=%.3fs",
            len(missing_ids),
            t_acquired - t0,
            t_queried - t_acquired,
            time.perf_counter() - t0,
        )
    except Exception as exc:
        logger.warning(
            "fetch_positions: batch lookup failed after %.3fs: %s",
            time.perf_counter() - t0,
            exc,
        )
        for collection in _collections_missing_positions(candidates):
            degradation.record(
                "fetch_positions", type(exc).__name__, "enrichment_skipped",
                scope=collection,
                details={"message": str(exc)[:300], "candidate_count": len(missing_ids)},
            )
        return candidates

    # Any looked-up id NOT returned by the query has no chunks row → orphan.
    present_ids = set(pos_map)
    filtered: dict[str, list[ChunkCandidate]] = {}
    dropped = 0
    dropped_by_collection: dict[str, int] = {}
    for col, col_list in candidates.items():
        kept: list[ChunkCandidate] = []
        for c in col_list:
            if c.position is None:
                if c.chunk_id not in present_ids:
                    dropped += 1
                    dropped_by_collection[col] = dropped_by_collection.get(col, 0) + 1
                    continue
                c.position = pos_map[c.chunk_id]
                # Qdrant payloads carry no annotation; FTS rows already have one
                # (retrieve_fts selects it), which is why this mirrors the
                # position filter rather than looking up every candidate.
                if c.annotation is None:
                    c.annotation = ann_map.get(c.chunk_id)
            kept.append(c)
        filtered[col] = kept

    if dropped:
        logger.warning(
            "fetch_positions: dropped %d orphaned candidate(s) absent from chunks "
            "table (stale Qdrant vectors)",
            dropped,
        )
        for collection, count in dropped_by_collection.items():
            degradation.record(
                "fetch_positions", "orphaned_candidates", "candidates_omitted",
                scope=collection,
                details={"count": count},
            )

    return filtered
