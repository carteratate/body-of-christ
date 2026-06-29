# services/api/app/rag/pipelines/runner.py
"""Sequences pipeline steps, measures timing, accumulates cost."""
from __future__ import annotations

import logging
import time

from app.rag.pipelines.registry import PipelineConfig
from app.rag.steps import (
    collection_guarantee,
    dedup,
    embed,
    fetch_positions,
    quota_cap,
    retrieve_fts,
    retrieve_vector,
    rrf,
)
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import PipelineResult, StepTiming

logger = logging.getLogger(__name__)


async def run(
    config: PipelineConfig,
    query: str,
    collections: list[str],
    quota: int,
    user_id: str | None = None,
) -> PipelineResult:
    tracker = CostTracker()
    timings: list[StepTiming] = []
    t_total = time.perf_counter()

    def _timed_sync(step: str, fn_lambda):
        t0 = time.perf_counter()
        result = fn_lambda()
        timings.append(StepTiming(step=step, duration_s=time.perf_counter() - t0))
        return result

    async def _timed_async(step: str, coro):
        t0 = time.perf_counter()
        result = await coro
        timings.append(StepTiming(step=step, duration_s=time.perf_counter() - t0))
        return result

    query_vec = await _timed_async("embed", embed.run(query, tracker))
    hyde_vecs = await _timed_async("hyde", config.hyde_module.run(query, collections, tracker))
    vec_raw   = await _timed_async("retrieve_vector", retrieve_vector.run(query_vec, hyde_vecs, collections, quota, user_id))
    fts_raw   = await _timed_async("retrieve_fts", retrieve_fts.run(query, collections, quota, user_id))
    merged    = _timed_sync("rrf", lambda: rrf.run(vec_raw, fts_raw, quota))
    _         = await _timed_async("fetch_positions", fetch_positions.run(merged))
    ranked    = await _timed_async("rerank", config.rerank_module.run(merged, query, quota, tracker))
    deduped   = await _timed_async("dedup", dedup.run(ranked))
    guaranteed = _timed_sync("collection_guarantee", lambda: collection_guarantee.run(deduped, ranked, collections))
    final     = _timed_sync("quota_cap", lambda: quota_cap.run(guaranteed, quota))

    total_duration = time.perf_counter() - t_total
    logger.info(
        "pipeline_runner: pipeline=%s duration=%.2fs cost=$%.6f chunks=%d",
        config.name, total_duration, tracker.total_cost(), len(final),
    )

    return PipelineResult(
        pipeline=config.name,
        chunks=final,
        step_timings=timings,
        total_duration_s=total_duration,
        cost_breakdown=tracker.breakdown(),
        total_cost=tracker.total_cost(),
    )
