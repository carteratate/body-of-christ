# services/api/app/rag/compare/persist.py
"""Persist compare run results to the compare_runs table.

Best-effort — errors are logged but never raised so the compare response
is never blocked by DB issues.
"""
from __future__ import annotations

import json
import logging

from app.db import get_pool
from app.rag.steps.types import PipelineResult
from app.rag.steps.cost_tracker import pricing_snapshot

logger = logging.getLogger(__name__)


async def save_compare_runs(
    query: str,
    collections: list[str],
    quota: int,
    results: list[PipelineResult],
) -> None:
    """Insert one row per pipeline result into compare_runs.

    Best-effort — errors are logged, not raised.
    """
    pool = get_pool()
    if pool is None:
        logger.warning("save_compare_runs: DB pool not available, skipping")
        return

    rows = [
        (
            query,
            collections,
            quota,
            r.pipeline,
            r.total_duration_s,
            r.total_cost,
            len(r.chunks),
            json.dumps(
                [{"step": t.step, "duration_s": t.duration_s} for t in r.step_timings]
            ),
            json.dumps(r.cost_breakdown),
            json.dumps(pricing_snapshot()),
        )
        for r in results
    ]

    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """INSERT INTO compare_runs
                   (query, collections, quota, pipeline, total_duration_s, total_cost,
                    chunk_count, step_timings, cost_breakdown, pricing)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb,
                           $10::jsonb)""",
                rows,
            )
    except Exception as exc:
        logger.error("save_compare_runs failed: %s", exc)
