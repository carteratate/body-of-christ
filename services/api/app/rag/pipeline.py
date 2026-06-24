"""RAG search pipeline — orchestrates HyDE, embedding, retrieval, re-ranking, and explanation."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from app.config import settings
from app.db import get_pool
from app.rag.hyde import generate_hyde_passages
from app.rag.embed import embed_text
from app.rag.retrieve import retrieve_candidates, ChunkCandidate
from app.rag.rerank import rerank_collection, RankedChunk
from app.rag.explain import stream_explanation
from app.rag.constants import VALID_COLLECTIONS
from app.rag.query_expand import expand_query

logger = logging.getLogger(__name__)


async def _hyde_and_embed(query: str, col: str) -> tuple[str, list[list[float]]]:
    """Generate HyDE passages for one collection then embed them immediately.

    Chaining these per-collection allows non-bible collections (~2s) to finish
    embedding before bible's sequential genre detection (~6.5s) completes,
    instead of blocking all embedding on the slowest HyDE call.
    Returns (collection, [embedding_vectors]) — empty list on any failure.
    """
    passages = await generate_hyde_passages(query, col)
    if not passages:
        return col, []
    results = await asyncio.gather(*[embed_text(p) for p in passages], return_exceptions=True)
    return col, [v for v in results if not isinstance(v, BaseException)]


async def run_search_pipeline(
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    user_id: str,
) -> AsyncGenerator[dict, None]:
    """Async generator that runs the full RAG pipeline and yields SSE-compatible dicts.

    Event types yielded:
        - {"type": "chunk", ...}       — one per ranked result, yielded immediately after reranking
        - {"type": "explanation", ...} — one per result as explanations complete (progressive)
        - {"type": "done", ...}        — final event with search_id and result_count
        - {"type": "error", ...}       — on unrecoverable failure
    """
    # ------------------------------------------------------------------
    # Input validation — allowlist collections
    # ------------------------------------------------------------------
    collections = [c for c in collections if c in VALID_COLLECTIONS]
    if not collections:
        yield {"type": "error", "detail": "No valid collections selected."}
        return

    try:
        _t0 = time.perf_counter()
        # ------------------------------------------------------------------
        # Steps 1+2 — Concurrent: query embedding + per-collection HyDE→embed
        #
        # Each collection runs its own _hyde_and_embed pipeline concurrently
        # with the query embedding. Non-bible collections (~2s) start embedding
        # immediately after their HyDE call returns rather than waiting for
        # bible's sequential genre detection (~6.5s) to finish first.
        # ------------------------------------------------------------------
        all_results = await asyncio.gather(
            embed_text(query),
            expand_query(query),
            *[_hyde_and_embed(query, col) for col in collections],
            return_exceptions=True,
        )

        query_vec_result = all_results[0]
        expansion_result = all_results[1]
        hyde_embed_results = all_results[2:]  # one (col, [vecs]) tuple per collection

        expansion_queries: list[str] = (
            expansion_result
            if not isinstance(expansion_result, BaseException)
            else []
        )

        _t1 = time.perf_counter()
        logger.info(
            "pipeline timing: steps1_2(hyde_embed)=%.2fs collections=%s",
            _t1 - _t0, collections,
        )

        if isinstance(query_vec_result, BaseException):
            logger.error("Query embedding failed: %s", query_vec_result)
            yield {"type": "error", "detail": "Embedding failed"}
            return
        query_vec: list[float] = query_vec_result

        # Build per-collection vec maps from (col, [vecs]) results.
        # vecs[0] = primary HyDE vec; vecs[1:] = extra genre vecs (bible only).
        per_col_hyde_vec: dict[str, list[float] | None] = {col: None for col in collections}
        per_col_extra_hyde_vecs: dict[str, list[list[float]]] = {col: [] for col in collections}
        for item in hyde_embed_results:
            if isinstance(item, BaseException):
                logger.warning("_hyde_and_embed failed: %s", item)
                continue
            col, vecs = item
            if not vecs:
                continue
            per_col_hyde_vec[col] = vecs[0]
            per_col_extra_hyde_vecs[col] = vecs[1:]

        # ------------------------------------------------------------------
        # Step 3 — Per-collection retrieval (parallel)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "searching", "collections": collections}
        retrieve_tasks = [
            retrieve_candidates(
                query, query_vec, per_col_hyde_vec[col],
                per_col_extra_hyde_vecs[col],
                col, quota, user_id,
                expansion_queries=expansion_queries,
            )
            for col in collections
        ]
        retrieve_results = await asyncio.gather(*retrieve_tasks, return_exceptions=True)

        # Flatten valid results; skip exceptions
        per_collection_candidates: list[list[ChunkCandidate]] = []
        for col, result in zip(collections, retrieve_results):
            if isinstance(result, BaseException):
                logger.warning(
                    "retrieve_candidates failed for collection '%s': %s", col, result
                )
            else:
                per_collection_candidates.append(result)

        _t3 = time.perf_counter()
        logger.info("pipeline timing: step3(retrieval)=%.2fs", _t3 - _t1)

        if not per_collection_candidates:
            logger.warning("All collection retrievals failed; yielding done with 0 results")
            yield {"type": "done", "search_id": str(uuid.uuid4()), "result_count": 0}
            return

        # ------------------------------------------------------------------
        # Step 4 — Per-collection re-ranking (parallel)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "ranking"}
        rerank_tasks = [
            rerank_collection(col_candidates, query, quota)
            for col_candidates in per_collection_candidates
        ]
        rerank_results = await asyncio.gather(*rerank_tasks, return_exceptions=True)

        _t4 = time.perf_counter()
        logger.info("pipeline timing: step4(rerank)=%.2fs", _t4 - _t3)

        all_ranked: list[RankedChunk] = []
        for result in rerank_results:
            if isinstance(result, BaseException):
                logger.warning("rerank_collection failed: %s", result)
            else:
                all_ranked.extend(result)

        # ------------------------------------------------------------------
        # Step 5 — Global sort, hard cutoff, conditional collection guarantee
        # ------------------------------------------------------------------
        _GUARANTEE_MIN_SCORE = 0.25
        all_sorted = sorted(all_ranked, key=lambda c: c.reranker_score, reverse=True)

        # Drop chunks the reranker excluded; cap each collection at quota results (best-first).
        col_counts: dict[str, int] = {}
        final_results: list[RankedChunk] = []
        for c in all_sorted:
            if c.include:
                col_counts[c.collection] = col_counts.get(c.collection, 0) + 1
                if col_counts[c.collection] <= quota:
                    final_results.append(c)

        # For each selected collection absent from results, inject its best chunk only
        # if it clears the minimum score threshold. Collections below threshold are
        # silenced entirely rather than injecting noise.
        represented = {r.collection for r in final_results}
        for col in collections:
            if col not in represented:
                col_best = next(
                    (r for r in all_sorted
                     if r.collection == col and r.reranker_score >= _GUARANTEE_MIN_SCORE),
                    None,
                )
                if col_best:
                    final_results.append(col_best)

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
        # Step 7 — Persist search + retrievals to DB
        # ------------------------------------------------------------------
        pool = get_pool()
        if pool is None:
            logger.error("run_search_pipeline: DB pool not available, skipping persistence")
            # Still yield done (chunks were already streamed) but without a persisted search_id
            yield {"type": "done", "search_id": None, "result_count": len(final_results)}
            return
        search_id = str(uuid.uuid4())
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

        # ------------------------------------------------------------------
        _t7 = time.perf_counter()
        logger.info(
            "pipeline timing: step7(db_insert)=%.2fs total_before_done=%.2fs results=%d",
            _t7 - _t4, _t7 - _t0, len(final_results),
        )

        # Step 8 — Yield done (before explanations so the frontend can show
        # results immediately; explanation_delta events follow on the same
        # open SSE stream and are applied progressively by the client).
        # ------------------------------------------------------------------
        yield {"type": "done", "search_id": search_id, "result_count": len(final_results)}

        # ------------------------------------------------------------------
        # Step 9 — Sequential streaming explanation generation (score order)
        # Running one explanation at a time stays under the OpenAI rate limit.
        # The 2-4s per explanation naturally spaces requests; the most important
        # result's explanation always appears first.
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

            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE retrievals SET explanation = $1 WHERE search_id = $2 AND chunk_id = $3",
                    accumulated_text[:2000],
                    uuid.UUID(search_id),
                    uuid.UUID(chunk.chunk_id),
                )

    except Exception:
        logger.exception("run_search_pipeline unhandled error")
        yield {"type": "error", "detail": "Search failed. Please try again."}
