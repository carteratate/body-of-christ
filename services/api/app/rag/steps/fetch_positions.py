"""Batch-fetch chunk positions from DB for Qdrant-sourced candidates."""
from __future__ import annotations

import logging

from app.db import get_pool
from app.rag.steps.types import ChunkCandidate

logger = logging.getLogger(__name__)


async def run(
    candidates: dict[str, list[ChunkCandidate]],
) -> dict[str, list[ChunkCandidate]]:
    """Fill in position=None candidates by querying Postgres.

    Qdrant payloads omit position; FTS rows already have it.
    Mutates the ChunkCandidate objects in place and returns the same dict.
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

    try:
        rows = await pool.fetch(
            "SELECT id::text, position FROM chunks WHERE id::text = ANY($1)",
            missing_ids,
        )
        pos_map = {r["id"]: r["position"] for r in rows}
    except Exception as exc:
        logger.warning("fetch_positions: batch lookup failed: %s", exc)
        return candidates

    for col_list in candidates.values():
        for c in col_list:
            if c.position is None and c.chunk_id in pos_map:
                c.position = pos_map[c.chunk_id]

    return candidates
