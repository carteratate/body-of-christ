"""RAG search pipeline — orchestrates HyDE, embedding, retrieval, re-ranking, and explanation."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator

from app.config import settings
from app.db import get_pool
from app.rag.hyde import generate_hyde_passages
from app.rag.embed import embed_text
from app.rag.retrieve import retrieve_candidates, ChunkCandidate
from app.rag.rerank import rerank_collection, RankedChunk
from app.rag.explain import stream_explanation
from app.rag.query_expand import expand_query
from app.rag.constants import VALID_COLLECTIONS

logger = logging.getLogger(__name__)


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
        # ------------------------------------------------------------------
        # Step 1 — Parallel: query embedding + query expansion + per-collection HyDE
        # One HyDE passage is generated per collection so each embedding lands
        # close to that collection's prose style.
        # ------------------------------------------------------------------
        step1_results = await asyncio.gather(
            embed_text(query),
            expand_query(query),
            *[generate_hyde_passages(query, col) for col in collections],
            return_exceptions=True,
        )

        query_vec_result = step1_results[0]
        expanded_queries_result = step1_results[1]
        hyde_passage_results = step1_results[2:]  # one entry per collection, in order

        if isinstance(query_vec_result, BaseException):
            logger.error("Query embedding failed: %s", query_vec_result)
            yield {"type": "error", "detail": "Embedding failed"}
            return
        query_vec: list[float] = query_vec_result

        if isinstance(expanded_queries_result, BaseException):
            expanded_queries: list[str] = []
        else:
            expanded_queries = expanded_queries_result

        # ------------------------------------------------------------------
        # Step 2 — Embed all valid HyDE passages + expanded query variants
        # ------------------------------------------------------------------
        # hyde_passage_results: one list[str] per collection (bible returns up to 3, one per detected genre)
        valid_hyde: list[tuple[str, str, int]] = []  # (collection, passage_text, index_within_col)
        for col, passages in zip(collections, hyde_passage_results):
            if isinstance(passages, BaseException):
                logger.warning("HyDE generation failed for collection=%s: %s", col, passages)
                continue
            for idx, passage in enumerate(passages):
                if isinstance(passage, str) and passage:
                    valid_hyde.append((col, passage, idx))

        embed_inputs = [p for _, p, _ in valid_hyde] + list(expanded_queries)
        embed_results: list = list(await asyncio.gather(
            *[embed_text(t) for t in embed_inputs],
            return_exceptions=True,
        )) if embed_inputs else []

        # Build per-collection hyde vec map; additional passages (e.g. bible NT) go into
        # per_col_extra_hyde_vecs and are appended to extra_vecs at retrieval time.
        per_col_hyde_vec: dict[str, list[float] | None] = {col: None for col in collections}
        per_col_extra_hyde_vecs: dict[str, list[list[float]]] = {col: [] for col in collections}
        for i, (col, _, passage_idx) in enumerate(valid_hyde):
            result = embed_results[i]
            if isinstance(result, BaseException):
                logger.warning("HyDE embedding failed for collection=%s: %s", col, result)
                continue
            if passage_idx == 0:
                per_col_hyde_vec[col] = result
            else:
                per_col_extra_hyde_vecs[col].append(result)

        # Build extra_vecs from expanded queries (shared across all collections)
        extra_vecs: list[list[float]] = []
        for j in range(len(expanded_queries)):
            idx = len(valid_hyde) + j
            if idx < len(embed_results) and not isinstance(embed_results[idx], BaseException):
                extra_vecs.append(embed_results[idx])

        # ------------------------------------------------------------------
        # Step 3 — Per-collection retrieval (parallel)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "searching", "collections": collections}
        retrieve_tasks = [
            retrieve_candidates(
                query, query_vec, per_col_hyde_vec[col],
                extra_vecs + per_col_extra_hyde_vecs[col],
                col, quota, user_id,
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

        # Drop chunks the reranker excluded (low quality or redundant with a better chunk)
        final_results = [c for c in all_sorted if c.include]

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
                for rank, chunk in enumerate(final_results):
                    await conn.execute(
                        "INSERT INTO retrievals (id, search_id, chunk_id, rank, reranker_score) VALUES ($1,$2,$3,$4,$5)",
                        uuid.uuid4(),
                        uuid.UUID(search_id),
                        uuid.UUID(chunk.chunk_id),
                        rank,
                        chunk.reranker_score,
                    )

        # ------------------------------------------------------------------
        # Step 8 — Sequential streaming explanation generation (score order)
        # Running one explanation at a time ensures we never burst the rate
        # limit — the 2-4s each explanation takes to stream naturally spaces
        # requests, and the most important result's explanation always appears
        # first. The queue + stagger approach has been removed.
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

        # ------------------------------------------------------------------
        # Step 9 — Yield done
        # ------------------------------------------------------------------
        yield {"type": "done", "search_id": search_id, "result_count": len(final_results)}

    except Exception:
        logger.exception("run_search_pipeline unhandled error")
        yield {"type": "error", "detail": "Search failed. Please try again."}
