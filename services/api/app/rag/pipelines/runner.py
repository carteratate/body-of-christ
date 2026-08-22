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
    fetch_context,
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
    stitch,
)
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import (
    AttachedContext, ChunkCandidate, PipelineResult, RankedChunk, StepTiming,
)

logger = logging.getLogger(__name__)

_RETRIEVAL_STAGES = {"retrieve_vector", "retrieve_fts"}
_HYDE_STAGES = {"hyde", "hyde_embed", "hyde_genre_select"}
_NON_QUALITY_ACTIONS = {"cost_estimated", "actual_cost_recorded"}
_RANKING_FAILURE_ACTIONS = {"collection_omitted"}


class PipelineExecutionError(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(f"pipeline stage failed: {stage}")
        self.stage = stage


def _classify_outcomes(
    *,
    collections: list[str],
    pre_enrichment: dict[str, list[ChunkCandidate]],
    candidates: dict[str, list[ChunkCandidate]],
    ranked_count: int,
    ranked_collections: set[str],
    final_collections: set[str],
    events: list[dict],
) -> tuple[str, dict[str, str]]:
    """Classify empty/partial output from evidence only the backend possesses."""
    collection_outcomes: dict[str, str] = {}
    retrieval_degraded: set[str] = set()
    ranking_degraded: set[str] = set()
    ranking_failed: set[str] = set()
    global_retrieval_degraded = False
    global_ranking_degraded = False
    enrichment_degraded: set[str] = set()
    global_enrichment_degraded = False
    orphaned = False
    for event in events:
        stage = event.get("stage")
        scope = event.get("scope")
        if stage in _RETRIEVAL_STAGES or stage in _HYDE_STAGES:
            if scope:
                retrieval_degraded.add(str(scope).split("/", 1)[0])
            else:
                global_retrieval_degraded = True
        if (
            stage
            and (stage == "rerank_cohere" or str(stage).startswith("rerank_"))
            and event.get("action") not in _NON_QUALITY_ACTIONS
        ):
            if scope:
                ranking_degraded.add(str(scope).split("/", 1)[0])
            else:
                global_ranking_degraded = True
            if event.get("action") in _RANKING_FAILURE_ACTIONS:
                if scope:
                    ranking_failed.add(str(scope).split("/", 1)[0])
        if stage == "fetch_positions":
            orphaned = orphaned or event.get("reason") == "orphaned_candidates"
            if scope:
                enrichment_degraded.add(str(scope).split("/", 1)[0])
            else:
                global_enrichment_degraded = True

    for collection in collections:
        if collection in final_collections:
            collection_outcomes[collection] = (
                "results_degraded"
                if (
                    global_retrieval_degraded
                    or collection in retrieval_degraded
                    or global_enrichment_degraded
                    or collection in enrichment_degraded
                    or global_ranking_degraded
                    or collection in ranking_degraded
                )
                else "results"
            )
        elif pre_enrichment.get(collection) and not candidates.get(collection):
            collection_outcomes[collection] = "corpus_sync_failed"
        elif not candidates.get(collection) and (
            global_retrieval_degraded or collection in retrieval_degraded
        ):
            collection_outcomes[collection] = "retrieval_failed"
        elif candidates.get(collection) and (
            ranked_count == 0
            or collection not in ranked_collections
            or collection in ranking_failed
        ):
            collection_outcomes[collection] = "ranking_failed"
        elif candidates.get(collection):
            collection_outcomes[collection] = "below_threshold"
        else:
            collection_outcomes[collection] = "no_candidates"

    if final_collections:
        degraded_outcomes = {
            "results_degraded", "retrieval_failed", "corpus_sync_failed", "ranking_failed"
        }
        outcome = (
            "degraded_success"
            if any(value in degraded_outcomes for value in collection_outcomes.values())
            else "success"
        )
    elif any(value == "corpus_sync_failed" for value in collection_outcomes.values()) or orphaned:
        outcome = "corpus_sync_failed"
    elif any(value == "retrieval_failed" for value in collection_outcomes.values()):
        outcome = "retrieval_failed"
    elif any(value == "ranking_failed" for value in collection_outcomes.values()):
        outcome = "ranking_failed"
    else:
        outcome = "no_candidates"
    return outcome, collection_outcomes


def _pool_sizes(config: PipelineConfig, quota: int) -> tuple[int | None, int | None]:
    """(per-strategy retrieval k, RRF top_n) for this pipeline, or (None, None).

    `llm_only` returns (None, None) so retrieval keeps its historical
    `quota * candidate_multiplier`. This preserves candidate sizing, not scoring-
    contract equivalence across the structured-output rollout.
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


# `run_from_candidates` deliberately does NOT stitch. It is the evaluation entry point,
# which scores retrieval and ranking against fixed candidate sets and never renders a
# card, so an attached passage would add two DB round trips and change nothing measured.
# The asymmetry with `run()` is intentional.
def _apply_stitching(
    final: list[RankedChunk], articles: dict,
) -> dict[str, AttachedContext]:
    """Index each result's attached context by chunk_id.

    `final` is NOT returned: `stitch.assemble` is a pure order-preserving map, so the
    result list this step receives is the result list it leaves behind. An earlier
    version merged cards and had to hand back a shortened list; that silently deleted
    scored results, and undoing it is what makes this a lookup rather than a transform.
    """
    return {
        item.chunk.chunk_id: AttachedContext(relation=item.relation, parts=item.parts)
        for item in stitch.assemble(final, articles)
        if item.is_stitched
    }


async def _stitching_context(final: list[RankedChunk], timed_async, timed_sync
                             ) -> dict[str, AttachedContext]:
    """The attached context for these results, or {} if anything goes wrong.

    The timing helpers are passed in because they close over `run_from_candidates`'s
    `timings` list. Reaching for them by name from module scope raises NameError, which
    this function's own guard would swallow — shipping the whole feature dead behind a
    green suite. `test_the_runner_attaches_context_end_to_end` is what stops that.

    Guarded, unlike the rest of the pipeline: by the time this runs, HyDE, embedding,
    retrieval, reranking and quota capping have all succeeded and nothing has been
    streamed yet. Letting an exception reach `_timed_sync` would raise
    PipelineExecutionError("stitch"), which the SSE layer reports as a ranking failure —
    discarding a complete, paid-for result set because a presentation flourish failed.

    The ASSEMBLY is inside the guard, not just the lookup: the lookup already degrades to
    {} on its own, so a guard around it alone would protect the half that needs it least.

    `record_recovery`, never `record`: `record` raises under DegradationPolicy.RAISE, and
    this call sits inside an except block, so it would escape the guard entirely.
    """
    try:
        articles = await timed_async(
            "fetch_context", fetch_context.articles(stitch.articles_needed(final)),
        )
        return timed_sync("stitch", lambda: _apply_stitching(final, articles))
    except Exception as exc:
        logger.warning("stitching failed (%s); results stay unattached",
                       exc.__class__.__name__)
        degradation.record_recovery(
            "stitch", type(exc).__name__, "results_unstitched",
            scope="summa", details={"message": str(exc)[:300]},
        )
        return {}


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
        cost_eligible=tracker.cost_eligible,
        rerank_contract_version=rerank.contract_version(config.rerank),
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
        try:
            result = fn_lambda()
        except Exception as exc:
            raise PipelineExecutionError(step) from exc
        timings.append(StepTiming(step=step, duration_s=time.perf_counter() - t0))
        return result

    async def _timed_async(step: str, coro):
        t0 = time.perf_counter()
        try:
            result = await coro
        except Exception as exc:
            raise PipelineExecutionError(step) from exc
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
    pre_enrichment = {col: list(chunks) for col, chunks in merged.items()}
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

    # Attach the passage that completes each Summa result. AFTER quota_cap on purpose:
    # this is presentation attached to a result, not a result itself, so it must never
    # consume a slot the user's quota would give to a different passage. One batched
    # query, and none at all for the majority of searches, which return no Summa
    # objection or reply.
    context = await _stitching_context(final, _timed_async, _timed_sync)


    total_duration = time.perf_counter() - t_total
    throttle_wait = rerank_cohere.throttle_wait_seconds()
    degraded = degradation.degradations()
    degradation_events = degradation.event_dicts()
    recovery_events = degradation.recovery_event_dicts()
    outcome, collection_outcomes = _classify_outcomes(
        collections=collections,
        pre_enrichment=pre_enrichment,
        candidates=merged,
        ranked_count=len(ranked),
        ranked_collections={chunk.collection for chunk in ranked},
        final_collections={chunk.collection for chunk in final},
        events=degradation_events,
    )
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
        cost_eligible=tracker.cost_eligible,
        rerank_contract_version=rerank.contract_version(config.rerank),
        throttle_wait_s=throttle_wait,
        degradations=degraded,
        degradation_events=degradation_events,
        recovery_events=recovery_events,
        quality_eligible=not bool(degraded),
        latency_eligible=not bool(degraded) and throttle_wait <= 1.0,
        outcome=outcome,
        collection_outcomes=collection_outcomes,
        context=context,
    )
