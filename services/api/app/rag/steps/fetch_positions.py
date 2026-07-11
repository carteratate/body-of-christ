"""Batch-fetch chunk positions from DB for Qdrant-sourced candidates."""
from __future__ import annotations

import logging
import time

from app.db import get_pool
from app.rag.steps.types import ChunkCandidate

logger = logging.getLogger(__name__)


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
                "SELECT id::text, position FROM chunks WHERE id = ANY($1::uuid[])",
                missing_ids,
            )
            t_queried = time.perf_counter()
        pos_map = {r["id"]: r["position"] for r in rows}
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
        return candidates

    # Any looked-up id NOT returned by the query has no chunks row → orphan.
    present_ids = set(pos_map)
    filtered: dict[str, list[ChunkCandidate]] = {}
    dropped = 0
    for col, col_list in candidates.items():
        kept: list[ChunkCandidate] = []
        for c in col_list:
            if c.position is None:
                if c.chunk_id not in present_ids:
                    dropped += 1
                    continue
                c.position = pos_map[c.chunk_id]
            kept.append(c)
        filtered[col] = kept

    if dropped:
        logger.warning(
            "fetch_positions: dropped %d orphaned candidate(s) absent from chunks "
            "table (stale Qdrant vectors)",
            dropped,
        )

    return filtered
