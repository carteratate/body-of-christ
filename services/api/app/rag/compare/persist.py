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
from app.rag.compare.methodology import fingerprint, snapshot
from app.config import settings

logger = logging.getLogger(__name__)


def _persisted_pipeline_key(result: PipelineResult) -> str:
    """Segment stored evaluations by the complete effective methodology."""
    contract = (
        f"@{result.rerank_contract_version}"
        if result.rerank_contract_version is not None else ""
    )
    methodology_id = fingerprint(snapshot([result.pipeline]))[:12]
    return f"{result.pipeline}{contract}#{methodology_id}"


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
    if not settings.evaluation_build_id or not settings.evaluation_corpus_id:
        logger.warning(
            "save_compare_runs: EVALUATION_BUILD_ID/EVALUATION_CORPUS_ID missing; "
            "skipping unidentifiable evaluation rows"
        )
        return

    eligible_results = [
        result for result in results
        if result.quality_eligible and result.latency_eligible and result.cost_eligible
    ]
    skipped = len(results) - len(eligible_results)
    if skipped:
        logger.warning(
            "save_compare_runs: skipping %d quality/latency/cost-ineligible result(s)",
            skipped,
        )

    rows = [
        (
            query,
            collections,
            quota,
            _persisted_pipeline_key(r),
            r.total_duration_s,
            r.total_cost,
            len(r.chunks),
            json.dumps(
                [{"step": t.step, "duration_s": t.duration_s} for t in r.step_timings]
            ),
            json.dumps(r.cost_breakdown),
            json.dumps(pricing_snapshot()),
        )
        for r in eligible_results
    ]
    if not rows:
        return

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
