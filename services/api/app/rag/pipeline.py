"""RAG search pipeline — orchestrates SSE event emission, DB persistence, and explanation streaming.

Compute-heavy steps (HyDE, embed, retrieve, rerank, dedup, guarantee, quota) are delegated
to `pipelines/runner.py`.  This module owns the SSE contract and DB side-effects only.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from app.db import get_pool
from app.rag.constants import VALID_COLLECTIONS
from app.rag.pipelines.registry import PIPELINES
from app.rag.pipelines.runner import run as run_pipeline
from app.rag.steps.explain import stream as stream_explanation

logger = logging.getLogger(__name__)

_PRODUCTION_PIPELINE = "s2_5_haiku"


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

        pipeline_result = await run_pipeline(
            config=config,
            query=query,
            collections=collections,
            quota=quota,
            user_id=user_id,
        )

        final_results = pipeline_result.chunks

        _t_pipeline = time.perf_counter()
        logger.info(
            "pipeline timing: runner=%.2fs chunks=%d pipeline=%s",
            _t_pipeline - _t0, len(final_results), config.name,
        )

        if not final_results:
            yield {"type": "done", "search_id": str(uuid.uuid4()), "result_count": 0}
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
                },
                "reranker_score": chunk.reranker_score,
            }

        # ------------------------------------------------------------------
        # Step 7 — Persist search + retrievals to DB (authenticated users only)
        # ------------------------------------------------------------------
        search_id = str(uuid.uuid4())
        if user_id is not None:
            pool = get_pool()
            if pool is None:
                logger.error("DB pool not available; returning results without saving search")
            else:
                # Persistence is best-effort: results are already streamed to the client,
                # so a DB failure here must NOT surface as a failed search. Log and move on.
                try:
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
                                        (uuid.uuid4(), uuid.UUID(search_id), uuid.UUID(chunk.chunk_id), rank, chunk.reranker_score)
                                        for rank, chunk in enumerate(final_results)
                                    ],
                                )
                    _t7 = time.perf_counter()
                    logger.info(
                        "pipeline timing: step7(db)=%.2fs total=%.2fs results=%d",
                        _t7 - _t_pipeline, _t7 - _t0, len(final_results),
                    )
                except Exception:
                    logger.exception("persist failed; returning results without saving search history")

        # ------------------------------------------------------------------
        # Step 8 — Yield done
        # ------------------------------------------------------------------
        yield {"type": "done", "search_id": search_id, "result_count": len(final_results)}

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

            if user_id is not None:
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

    except Exception:
        logger.exception("run_search_pipeline unhandled error")
        yield {"type": "error", "detail": "Search failed. Please try again."}
