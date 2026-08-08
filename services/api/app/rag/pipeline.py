"""RAG search pipeline — orchestrates SSE event emission, DB persistence, and explanation streaming.

Compute-heavy steps (HyDE, embed, retrieve, rerank, dedup, guarantee, quota) are delegated
to `pipelines/runner.py`.  This module owns the SSE contract and DB side-effects only.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

from app.db import get_pool
from app.rag.constants import VALID_COLLECTIONS
from app.rag.pipelines.registry import PIPELINES
from app.rag.pipelines.runner import PipelineExecutionError, run as run_pipeline
from app.rag.steps.explain import stream as stream_explanation

logger = logging.getLogger(__name__)

_PRODUCTION_PIPELINE = "hyde_cohere_luna"
_PIPELINE_HEARTBEAT_SECONDS = 10.0
_PERSIST_TIMEOUT_SECONDS = 10.0


async def _persist_empty_search(
    *,
    search_id: str,
    user_id: str | None,
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
) -> bool:
    if user_id is None:
        return False
    pool = get_pool()
    if pool is None:
        logger.warning("empty search not persisted: DB pool unavailable")
        return False
    try:
        async with asyncio.timeout(_PERSIST_TIMEOUT_SECONDS):
            await pool.execute(
                "INSERT INTO searches (id, user_id, query, filters, result_count) VALUES ($1,$2,$3,$4::jsonb,0)",
                uuid.UUID(search_id),
                uuid.UUID(user_id),
                query,
                json.dumps({
                    "collections": collections,
                    "translation": translation,
                    "quota": quota,
                }),
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
            )
            yield {
                "type": "done",
                "search_id": empty_search_id if persisted else None,
                "persisted": persisted,
                "result_count": 0,
                "outcome": "no_candidates",
                "collection_outcomes": pipeline_result.collection_outcomes,
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
                },
                "reranker_score": (
                    None if chunk.score_source == "rrf_fallback"
                    else chunk.reranker_score
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
                                    json.dumps({"collections": collections, "translation": translation, "quota": quota}),
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
        }

        # ------------------------------------------------------------------
        # Step 9 — Sequential streaming explanations
        # ------------------------------------------------------------------
        for chunk in final_results:
            accumulated_text = ""
            try:
                async for delta in stream_explanation(
                    chunk.content, chunk.reference, chunk.collection, query
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
