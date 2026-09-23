"""RAG search pipeline — orchestrates SSE event emission, DB persistence, and explanation streaming.

Compute-heavy steps (HyDE, embed, retrieve, rerank, dedup, guarantee, quota) are delegated
to `pipelines/runner.py`.  This module owns the SSE contract and DB side-effects only.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import time
import uuid

from app.config import settings
from app.db import get_pool
from app.rag.constants import VALID_COLLECTIONS
from app.rag.outcomes import CollectionOutcome, PersistedSearchOutcome
from app.rag.pipelines.registry import PIPELINES, PipelineConfig
from app.rag.pipelines.runner import PipelineExecutionError, run as run_pipeline
from app.rag.search_plan import SearchPlan, resolve_search_plan
from app.rag.steps import stitch
from app.rag.steps import explain
from app.rag.steps.cost_tracker import PRICING_EFFECTIVE_DATE, CostTracker
from app.rag.steps.explain import stream as stream_explanation
from app.rag.steps.types import PipelineResult

logger = logging.getLogger(__name__)

_PRODUCTION_PIPELINE = "hyde_cohere_luna"
_PIPELINE_HEARTBEAT_SECONDS = 10.0
_PERSIST_TIMEOUT_SECONDS = 10.0


# Strong references to in-flight cost writes; a bare create_task can be collected
# before it runs.
_COST_WRITES: set[asyncio.Task] = set()


def _models_used(config: PipelineConfig) -> dict:
    """Model ids and reasoning efforts behind a search's cost, for `search_costs`."""
    hyde, rerank = config.retrieval, config.rerank
    models: dict = {
        "hyde_passage": (
            hyde.hyde_luna_model or settings.hyde_luna_model
            if settings.hyde_passage_provider == "luna" else settings.hyde_model
        ),
        "hyde_genre": (
            hyde.hyde_genre_luna_model or settings.hyde_genre_luna_model
            if settings.hyde_genre_provider == "luna" else settings.hyde_model
        ),
        "explain": settings.explain_openai_model,
        "explain_reasoning_effort": explain.REASONING_EFFORT,
    }
    if rerank.llm_provider is not None:
        provider = rerank.provider()
        models["rerank"] = provider.model_id
        effort = getattr(provider, "reasoning_effort", None)
        if effort is not None:
            models["rerank_reasoning_effort"] = effort
    return models


def _record_search_cost(
    *,
    search_id: str | None,
    user_id: str | None,
    plan: SearchPlan,
    config: PipelineConfig,
    pipeline_result: PipelineResult,
    outcome: str,
    delivered: int,
    explanation_cost: CostTracker | None = None,
) -> None:
    """Persist one search's provider cost to `search_costs`, in the background.

    Best-effort telemetry: never raises, never delays the stream, and a missing
    table (migration 0036 not yet applied) or DB outage only logs a warning. Called
    wherever a search stops spending money, including the no-result and failed-
    ranking exits, which spend on HyDE, embedding and Cohere all the same.
    """
    pool = get_pool()
    if pool is None:
        return
    breakdown = dict(pipeline_result.cost_breakdown)
    explain_total = 0.0
    eligible = pipeline_result.cost_eligible
    if explanation_cost is not None:
        explain_total = explanation_cost.total_cost()
        breakdown.update(explanation_cost.breakdown())
        eligible = eligible and explanation_cost.cost_eligible

    async def write() -> None:
        try:
            async with pool.acquire(timeout=_PERSIST_TIMEOUT_SECONDS) as conn:
                await conn.execute(
                    """
                    INSERT INTO search_costs (
                        search_id, audience, pipeline, outcome, collection_count,
                        quota, focused, delivered, runner_cost, explanation_cost,
                        cost_breakdown, cost_eligible, pricing_effective_date, models
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    uuid.UUID(search_id) if search_id else None,
                    "authenticated" if user_id is not None else "guest",
                    config.name,
                    outcome,
                    len(plan.collections),
                    plan.quota,
                    plan.focused,
                    delivered,
                    pipeline_result.total_cost,
                    explain_total,
                    # jsonb params go in as objects: app/db.py's codec encodes them.
                    breakdown,
                    eligible,
                    datetime.date.fromisoformat(PRICING_EFFECTIVE_DATE),
                    _models_used(config),
                    timeout=_PERSIST_TIMEOUT_SECONDS,
                )
        except Exception as exc:
            logger.warning("search cost persist failed: %s", exc)

    task = asyncio.create_task(write())
    _COST_WRITES.add(task)
    task.add_done_callback(_COST_WRITES.discard)


def _saved_search_filters(
    collections: list[str],
    translation: str,
    quota: int,
    delivery_outcome: str | None,
    outcome: PersistedSearchOutcome,
    collection_outcomes: dict[str, str],
) -> dict:
    filters = {
        "collections": collections,
        "translation": translation,
        "quota": quota,
        "outcome": outcome,
        "collection_outcomes": collection_outcomes,
    }
    if quota == 10 and delivery_outcome in {"complete", "underfilled", "minimum_floor"}:
        filters["delivery_outcome"] = delivery_outcome
    return filters


async def _persist_empty_search(
    *,
    search_id: str,
    user_id: str | None,
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    collection_outcomes: dict[str, CollectionOutcome],
    delivery_outcome: str | None = None,
) -> bool:
    if user_id is None:
        return False
    pool = get_pool()
    if pool is None:
        logger.warning("empty search not persisted: DB pool unavailable")
        return False
    try:
        persisted_collection_outcomes = {
            collection: CollectionOutcome(value)
            for collection, value in collection_outcomes.items()
        }
        async with asyncio.timeout(_PERSIST_TIMEOUT_SECONDS):
            await pool.execute(
                "INSERT INTO searches (id, user_id, query, filters, result_count) VALUES ($1,$2,$3,$4::jsonb,0)",
                uuid.UUID(search_id),
                uuid.UUID(user_id),
                query,
                _saved_search_filters(
                    collections,
                    translation,
                    quota,
                    delivery_outcome,
                    PersistedSearchOutcome.NO_CANDIDATES,
                    persisted_collection_outcomes,
                ),
            )
        return True
    except Exception:
        logger.exception("empty search persistence failed")
        return False


async def run_search_pipeline(
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    user_id: str | None,
    search_plan: SearchPlan | None = None,
):
    """Async generator yielding SSE-compatible dicts.

    Event types: "status", "chunk", "explanation_delta", "done", "error"
    """
    collections = [c for c in collections if c in VALID_COLLECTIONS]
    if not collections:
        yield {"type": "error", "detail": "No valid collections selected."}
        return

    try:
        _t0 = time.perf_counter()

        plan = search_plan or resolve_search_plan(collections, quota)
        collections = list(plan.collections)
        quota = plan.quota

        config = PIPELINES[_PRODUCTION_PIPELINE]

        # Emit status events before the runner executes so clients see live progress
        # while retrieval + reranking are in-flight — matches original timing semantics.
        yield {"type": "status", "phase": "searching", "collections": collections}
        yield {"type": "status", "phase": "ranking"}

        # Retrieval and reranking can legitimately take longer than an intermediary's
        # idle-stream timeout (especially when Cohere asks us to back off). Keep the
        # SSE response active while the runner is working instead of emitting two
        # status events and then going completely silent until every result is ready.
        pipeline_task = asyncio.create_task(
            run_pipeline(
                config=config,
                query=query,
                collections=collections,
                quota=quota,
                user_id=user_id,
                search_plan=plan,
            )
        )
        try:
            while not pipeline_task.done():
                done, _ = await asyncio.wait(
                    {pipeline_task},
                    timeout=_PIPELINE_HEARTBEAT_SECONDS,
                )
                if not done:
                    yield {"type": "status", "phase": "ranking", "heartbeat": True}
            pipeline_result = await pipeline_task
        finally:
            if not pipeline_task.done():
                pipeline_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pipeline_task

        final_results = pipeline_result.chunks

        _t_pipeline = time.perf_counter()
        logger.info(
            "pipeline timing: runner=%.2fs chunks=%d pipeline=%s recoveries=%d "
            "degradations=%d quality_eligible=%s outcome=%s collection_outcomes=%s",
            _t_pipeline - _t0,
            len(final_results),
            config.name,
            len(pipeline_result.recovery_events),
            len(pipeline_result.degradation_events),
            pipeline_result.quality_eligible,
            pipeline_result.outcome,
            pipeline_result.collection_outcomes,
        )

        if not final_results and pipeline_result.outcome != "no_candidates":
            _record_search_cost(
                search_id=None, user_id=user_id, plan=plan, config=config,
                pipeline_result=pipeline_result, outcome=pipeline_result.outcome,
                delivered=0,
            )
            code = pipeline_result.outcome
            stage = (
                "retrieval"
                if code in {"retrieval_failed", "corpus_sync_failed"}
                else "ranking"
            )
            yield {
                "type": "error",
                "code": code,
                "stage": stage,
                "detail": {
                    "retrieval_failed": "Passage retrieval was unavailable for the selected collections.",
                    "corpus_sync_failed": "Retrieved passages could not be matched to the readable corpus.",
                    "ranking_failed": "Passages were retrieved, but ranking could not be completed.",
                }[code],
                "collection_outcomes": pipeline_result.collection_outcomes,
            }
            return

        if not final_results:
            empty_search_id = str(uuid.uuid4())
            persisted = await _persist_empty_search(
                search_id=empty_search_id,
                user_id=user_id,
                query=query,
                collections=collections,
                translation=translation,
                quota=quota,
                collection_outcomes=pipeline_result.collection_outcomes,
                delivery_outcome=pipeline_result.delivery_outcome,
            )
            _record_search_cost(
                search_id=empty_search_id if persisted else None, user_id=user_id,
                plan=plan, config=config, pipeline_result=pipeline_result,
                outcome="no_candidates", delivered=0,
            )
            yield {
                "type": "done",
                "search_id": empty_search_id if persisted else None,
                "persisted": persisted,
                "result_count": 0,
                "outcome": "no_candidates",
                "collection_outcomes": pipeline_result.collection_outcomes,
                "delivery_outcome": pipeline_result.delivery_outcome,
                "requested_quota": quota,
            }
            return

        # ------------------------------------------------------------------
        # Step 6 — Yield chunk events
        # ------------------------------------------------------------------
        for chunk in final_results:
            yield {
                "type": "chunk",
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "source": {
                    "collection": chunk.collection,
                    "document_title": chunk.document_title,
                    "author": chunk.author,
                    "reference": chunk.reference,
                    "document_id": chunk.document_id,
                    "anchor": chunk.anchor,
                    "chapter_key": chunk.chapter_key,
                    "unit_label": chunk.unit_label,
                },
                "reranker_score": (
                    None if chunk.score_source == "rrf_fallback"
                    else chunk.reranker_score
                ),
                # The passage that completes this result: Aquinas's answer beneath a
                # matched objection, or the objection ABOVE a matched reply. `relation`
                # says which, so the renderer never infers placement from a label.
                # Presentation only — not a result, no score, not persisted to
                # `retrievals`, which records the passage that actually matched.
                "context": (
                    {
                        "relation": attached.relation,
                        "parts": [
                            {"content": part.content, "reference": part.reference,
                             "unit_label": part.unit_label, "anchor": part.anchor}
                            for part in attached.parts
                        ],
                    }
                    if (attached := pipeline_result.context.get(chunk.chunk_id))
                    else None
                ),
            }

        # ------------------------------------------------------------------
        # Step 7 — Persist search + retrievals to DB (authenticated users only)
        # ------------------------------------------------------------------
        search_id = str(uuid.uuid4())
        persisted = False
        if user_id is not None:
            pool = get_pool()
            if pool is None:
                logger.error("DB pool not available; returning results without saving search")
            else:
                # Persistence is best-effort: results are already streamed to the client,
                # so a DB failure here must NOT surface as a failed search. Log and move on.
                try:
                    async with asyncio.timeout(_PERSIST_TIMEOUT_SECONDS):
                        async with pool.acquire() as conn:
                            async with conn.transaction():
                                await conn.execute(
                                    "INSERT INTO searches (id, user_id, query, filters, result_count) VALUES ($1,$2,$3,$4::jsonb,$5)",
                                    uuid.UUID(search_id),
                                    uuid.UUID(user_id),
                                    query,
                                    _saved_search_filters(
                                        collections, translation, quota,
                                        pipeline_result.delivery_outcome,
                                        PersistedSearchOutcome(pipeline_result.outcome),
                                        {
                                            collection: CollectionOutcome(value)
                                            for collection, value
                                            in pipeline_result.collection_outcomes.items()
                                        },
                                    ),
                                    len(final_results),
                                )
                                if final_results:
                                    await conn.executemany(
                                        "INSERT INTO retrievals (id, search_id, chunk_id, rank, reranker_score) VALUES ($1,$2,$3,$4,$5)",
                                        [
                                            (
                                                uuid.uuid4(), uuid.UUID(search_id),
                                                uuid.UUID(chunk.chunk_id), rank,
                                                None if chunk.score_source == "rrf_fallback"
                                                else chunk.reranker_score,
                                            )
                                            for rank, chunk in enumerate(final_results, start=1)
                                        ],
                                    )
                    _t7 = time.perf_counter()
                    logger.info(
                        "pipeline timing: step7(db)=%.2fs total=%.2fs results=%d",
                        _t7 - _t_pipeline, _t7 - _t0, len(final_results),
                    )
                    persisted = True
                except Exception:
                    logger.exception("persist failed; returning results without saving search history")

        # ------------------------------------------------------------------
        # Step 8 — Yield done
        # ------------------------------------------------------------------
        yield {
            "type": "done",
            "search_id": search_id if persisted else None,
            "persisted": persisted,
            "result_count": len(final_results),
            "outcome": pipeline_result.outcome,
            "collection_outcomes": pipeline_result.collection_outcomes,
            "delivery_outcome": pipeline_result.delivery_outcome,
            "requested_quota": quota,
        }

        # ------------------------------------------------------------------
        # Step 9 — Sequential streaming explanations
        # ------------------------------------------------------------------
        _t_explanations = time.perf_counter()
        explanation_cost = CostTracker()
        for chunk in final_results:
            accumulated_text = ""
            try:
                # The ASSEMBLED card, not the fragment that matched it. This prose is
                # persisted to `retrievals.explanation` and re-served forever, so an
                # explanation about the objection alone would sit above the answer to
                # it permanently.
                attached = pipeline_result.context.get(chunk.chunk_id)
                explain_chunk = stitch.with_stitched_content(
                    stitch.Stitched(
                        chunk,
                        attached.parts if attached else [],
                        attached.relation if attached else None,
                    )
                )
                async for delta in stream_explanation(
                    explain_chunk.content, chunk.reference, chunk.collection, query,
                    unit_label=chunk.unit_label,
                    cost_tracker=explanation_cost,
                ):
                    accumulated_text += delta
                    yield {"type": "explanation_delta", "chunk_id": chunk.chunk_id, "delta": delta}
            except Exception as exc:
                logger.warning("explanation error for chunk %s: %s", chunk.chunk_id, exc)

            if persisted and user_id is not None:
                pool = get_pool()
                if pool is not None:
                    # Best-effort: a failed explanation write must not abort the
                    # response or the remaining chunks' explanations.
                    try:
                        async with pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE retrievals SET explanation = $1 WHERE search_id = $2 AND chunk_id = $3",
                                accumulated_text[:2000],
                                uuid.UUID(search_id),
                                uuid.UUID(chunk.chunk_id),
                            )
                    except Exception as exc:
                        logger.warning("explanation persist failed for chunk %s: %s", chunk.chunk_id, exc)

        _record_search_cost(
            search_id=search_id if persisted else None, user_id=user_id, plan=plan,
            config=config, pipeline_result=pipeline_result,
            outcome=pipeline_result.outcome, delivered=len(final_results),
            explanation_cost=explanation_cost,
        )
        logger.info(
            "search delivery: focused=%s requested=%d delivered=%d delivery_outcome=%s "
            "runner_seconds=%.2f explanation_tail_seconds=%.2f "
            "runner_cost=$%.6f explanation_cost=$%.6f explanation_cost_eligible=%s",
            plan.focused,
            quota,
            len(final_results),
            pipeline_result.delivery_outcome,
            _t_pipeline - _t0,
            time.perf_counter() - _t_explanations,
            pipeline_result.total_cost,
            explanation_cost.total_cost(),
            explanation_cost.cost_eligible,
        )

    except PipelineExecutionError as exc:
        logger.exception("run_search_pipeline stage failed: %s", exc.stage)
        if exc.stage == "embed":
            code, stage, detail = (
                "embedding_failed",
                "embedding",
                "The query could not be prepared for semantic retrieval.",
            )
        elif exc.stage in {
            "hyde", "retrieve_vector", "retrieve_fts", "rrf", "fetch_positions"
        }:
            code, stage, detail = (
                "retrieval_failed",
                "retrieval",
                "The search service could not retrieve passages.",
            )
        else:
            code, stage, detail = (
                "ranking_failed",
                "ranking",
                "Passages were retrieved, but ranking could not be completed.",
            )
        yield {"type": "error", "code": code, "stage": stage, "detail": detail}
    except Exception:
        logger.exception("run_search_pipeline unhandled error")
        yield {
            "type": "error",
            "code": "pipeline_failed",
            "stage": "retrieval_or_ranking",
            "detail": "The search service could not finish retrieving and ranking passages.",
        }
