# services/api/app/rag/pipelines/runner.py
"""Sequences pipeline steps, measures timing, accumulates cost."""
from __future__ import annotations

import logging
import time
import copy

from app.config import settings
from app.rag.pipelines.registry import PipelineConfig
from app.rag.steps import (
    budget,
    collection_guarantee,
    dedup,
    degradation,
    embed,
    fetch_positions,
    hyde_none,
    hyde_s25,
    min_floor,
    quota_cap,
    rerank,
    rerank_cohere,
    retrieve_fts,
    retrieve_vector,
    rrf,
)
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import ChunkCandidate, PipelineResult, StepTiming

logger = logging.getLogger(__name__)


def _pool_sizes(config: PipelineConfig, quota: int) -> tuple[int | None, int | None]:
    """(per-strategy retrieval k, RRF top_n) for this pipeline, or (None, None).

    `llm_only` returns (None, None) so the retrieval steps keep their historical
    `quota * candidate_multiplier` — that mode is the A/B baseline and must not move.
    Cohere modes size the pool to fill one Cohere search unit and scale the
    per-strategy limit to the number of active paths.
    """
    if config.rerank.mode == "llm_only":
        return None, None

    pool = settings.cohere_max_pool
    if config.retrieval.retrieval_k_override is not None:
        # Ablation pipelines pin k so removing a path does not also deepen the
        # remaining ones (see RetrievalConfig.retrieval_k_override).
        return config.retrieval.retrieval_k_override, pool
    # Bible contributes extra HyDE vectors, but sizing on the common case (one query
    # vector + one HyDE vector + FTS) is what keeps per-path limits sane.
    n_paths = 1 + (1 if config.retrieval.hyde else 0) + (1 if config.retrieval.fts else 0)
    return budget.retrieval_k(pool, n_paths), pool


async def run_from_candidates(
    config: PipelineConfig,
    candidates: dict[str, list[ChunkCandidate]],
    query: str,
    collections: list[str],
    quota: int,
    degradation_policy: degradation.DegradationPolicy = degradation.DegradationPolicy.ALLOW,
) -> PipelineResult:
    """Run only the pipeline-specific rerank and result-shaping stages.

    Evaluation uses this with a shared, captured candidate pool so reranker variants
    transform identical upstream evidence. Candidates are copied because downstream
    stages may mutate their objects.
    """
    tracker = CostTracker()
    rerank_cohere.begin_throttle_accounting()
    degradation.begin_degradation_accounting(degradation_policy)
    timings: list[StepTiming] = []
    t_total = time.perf_counter()
    candidates = copy.deepcopy(candidates)

    async def timed_async(step: str, coro):
        t0 = time.perf_counter()
        result = await coro
        timings.append(StepTiming(step=step, duration_s=time.perf_counter() - t0))
        return result

    def timed_sync(step: str, fn):
        t0 = time.perf_counter()
        result = fn()
        timings.append(StepTiming(step=step, duration_s=time.perf_counter() - t0))
        return result

    ranked, all_scored = await timed_async(
        "rerank", rerank.run(config.rerank, candidates, query, quota, tracker),
    )
    deduped = await timed_async("dedup", dedup.run(ranked))
    guaranteed = timed_sync(
        "collection_guarantee",
        lambda: collection_guarantee.run(deduped, all_scored, collections),
    )
    final = timed_sync("quota_cap", lambda: quota_cap.run(guaranteed, quota))
    if not final and ranked:
        final = timed_sync("min_floor", lambda: min_floor.run(ranked, quota))

    total_duration = time.perf_counter() - t_total
    throttle_wait = rerank_cohere.throttle_wait_seconds()
    degraded = degradation.degradations()
    return PipelineResult(
        pipeline=config.name,
        chunks=final,
        step_timings=timings,
        total_duration_s=total_duration,
        cost_breakdown=tracker.breakdown(),
        total_cost=tracker.total_cost(),
        throttle_wait_s=throttle_wait,
        degradations=degraded,
        degradation_events=degradation.event_dicts(),
        recovery_events=degradation.recovery_event_dicts(),
        quality_eligible=not bool(degraded),
        latency_eligible=not bool(degraded) and throttle_wait <= 1.0,
    )


async def run(
    config: PipelineConfig,
    query: str,
    collections: list[str],
    quota: int,
    user_id: str | None = None,
    degradation_policy: degradation.DegradationPolicy = degradation.DegradationPolicy.ALLOW,
) -> PipelineResult:
    tracker = CostTracker()
    # Fresh throttle accounting per run so waits are attributed to this pipeline.
    rerank_cohere.begin_throttle_accounting()
    degradation.begin_degradation_accounting(degradation_policy)
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

    hyde_module = hyde_s25 if config.retrieval.hyde else hyde_none
    k, top_n = _pool_sizes(config, quota)

    query_vec = await _timed_async("embed", embed.run(query, tracker))
    hyde_vecs = await _timed_async("hyde", hyde_module.run(query, collections, tracker))
    vec_raw   = await _timed_async("retrieve_vector", retrieve_vector.run(query_vec, hyde_vecs, collections, quota, user_id, k=k))
    if config.retrieval.fts:
        fts_raw = await _timed_async("retrieve_fts", retrieve_fts.run(query, collections, quota, user_id, k=k))
    else:
        # Lexical ablation — dense only. RRF handles a missing path natively.
        fts_raw = {}
    merged    = _timed_sync("rrf", lambda: rrf.run(vec_raw, fts_raw, quota, top_n=top_n))
    merged    = await _timed_async("fetch_positions", fetch_positions.run(merged))
    ranked, all_scored = await _timed_async(
        "rerank", rerank.run(config.rerank, merged, query, quota, tracker),
    )
    deduped   = await _timed_async("dedup", dedup.run(ranked))
    guaranteed = _timed_sync("collection_guarantee", lambda: collection_guarantee.run(deduped, all_scored, collections))
    final     = _timed_sync("quota_cap", lambda: quota_cap.run(guaranteed, quota))

    # Last-resort floor: if scoring excluded everything, surface best-effort
    # candidates rather than returning a silent "no results" (see min_floor).
    if not final and ranked:
        final = _timed_sync("min_floor", lambda: min_floor.run(ranked, quota))

    total_duration = time.perf_counter() - t_total
    throttle_wait = rerank_cohere.throttle_wait_seconds()
    degraded = degradation.degradations()
    degradation_events = degradation.event_dicts()
    recovery_events = degradation.recovery_event_dicts()
    if degraded:
        logger.warning(
            "pipeline_runner: pipeline=%s DEGRADED %s — rerank did not fully run; "
            "this result is not comparable with a healthy one",
            config.name, degraded,
        )
    logger.info(
        "pipeline_runner: pipeline=%s mode=%s duration=%.2fs (throttle %.2fs) "
        "cost=$%.6f chunks=%d recoveries=%d degraded=%s",
        config.name, config.rerank.mode, total_duration, throttle_wait,
        tracker.total_cost(), len(final), len(recovery_events), bool(degraded),
    )
    for event in recovery_events:
        logger.info(
            "pipeline_recovery: pipeline=%s stage=%s scope=%s reason=%s "
            "action=%s details=%s",
            config.name,
            event.get("stage"),
            event.get("scope"),
            event.get("reason"),
            event.get("action"),
            event.get("details"),
        )

    return PipelineResult(
        pipeline=config.name,
        chunks=final,
        step_timings=timings,
        total_duration_s=total_duration,
        cost_breakdown=tracker.breakdown(),
        total_cost=tracker.total_cost(),
        throttle_wait_s=throttle_wait,
        degradations=degraded,
        degradation_events=degradation_events,
        recovery_events=recovery_events,
        quality_eligible=not bool(degraded),
        latency_eligible=not bool(degraded) and throttle_wait <= 1.0,
    )
