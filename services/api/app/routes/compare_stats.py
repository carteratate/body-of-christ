# services/api/app/routes/compare_stats.py
"""GET /v1/search/compare/stats — per-pipeline percentile aggregates from compare_runs."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()

_STATS_SQL = """
SELECT
    pipeline,
    COUNT(*)                                                                            AS run_count,
    ROUND(AVG(total_duration_s)::numeric, 3)                                            AS avg_duration_s,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_duration_s)::numeric, 3)  AS p50_duration_s,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_duration_s)::numeric, 3)  AS p95_duration_s,
    ROUND(AVG(total_cost)::numeric, 6)                                                  AS avg_cost,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_cost)::numeric, 6)        AS p50_cost,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_cost)::numeric, 6)        AS p95_cost,
    ROUND(AVG(chunk_count)::numeric, 1)                                                 AS avg_chunks
FROM compare_runs
GROUP BY pipeline
ORDER BY pipeline
"""


@router.get("/search/compare/stats")
async def compare_stats(
    _user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return per-pipeline timing and cost percentile stats across all compare runs."""
    pool = get_pool()
    if pool is None:
        return {"pipelines": []}

    async with pool.acquire() as conn:
        rows = await conn.fetch(_STATS_SQL)

    return {
        "pipelines": [
            {
                "pipeline": r["pipeline"],
                "run_count": r["run_count"],
                "avg_duration_s": float(r["avg_duration_s"] or 0),
                "p50_duration_s": float(r["p50_duration_s"] or 0),
                "p95_duration_s": float(r["p95_duration_s"] or 0),
                "avg_cost": float(r["avg_cost"] or 0),
                "p50_cost": float(r["p50_cost"] or 0),
                "p95_cost": float(r["p95_cost"] or 0),
                "avg_chunks": float(r["avg_chunks"] or 0),
            }
            for r in rows
        ]
    }
