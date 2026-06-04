"""RAG search pipeline — orchestrates HyDE, embedding, retrieval, re-ranking, and explanation."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator

from app.config import settings
from app.db import get_pool
from app.rag.hyde import generate_hyde_passage
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
        # Step 1 — Parallel HyDE + query embedding + query expansion
        # ------------------------------------------------------------------
        hyde_passage, query_vec, expanded_queries = await asyncio.gather(
            generate_hyde_passage(query),
            embed_text(query),
            expand_query(query),
            return_exceptions=True,
        )

        if isinstance(query_vec, BaseException):
            logger.error("Query embedding failed: %s", query_vec)
            yield {"type": "error", "detail": "Embedding failed"}
            return

        if isinstance(hyde_passage, BaseException) or hyde_passage is None:
            hyde_passage = None  # HyDE fallback — use query_vec only

        if isinstance(expanded_queries, BaseException):
            expanded_queries = []

        # ------------------------------------------------------------------
        # Step 2 — Embed HyDE passage + expanded query variants (if available)
        # ------------------------------------------------------------------
        hyde_vec: list[float] | None = None
        if isinstance(hyde_passage, str) and hyde_passage:
            try:
                hyde_vec = await embed_text(hyde_passage)
            except Exception as exc:
                logger.warning("HyDE embedding failed, falling back to query_vec only: %s", exc)
                hyde_vec = None

        extra_vecs: list[list[float]] = []
        if expanded_queries:
            embed_results = await asyncio.gather(
                *[embed_text(q) for q in expanded_queries],
                return_exceptions=True,
            )
            extra_vecs = [v for v in embed_results if not isinstance(v, BaseException)]

        # ------------------------------------------------------------------
        # Step 3 — Per-collection retrieval (parallel)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "searching", "collections": collections}
        retrieve_tasks = [
            retrieve_candidates(query, query_vec, hyde_vec, extra_vecs, col, quota, user_id)
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
        # Step 5 — Global merge and sort by reranker_score descending
        # ------------------------------------------------------------------
        final_results = sorted(all_ranked, key=lambda c: c.reranker_score, reverse=True)

        # Ensure every selected collection has at least one result. If a
        # collection scored below the top results, append its best-ranked
        # chunk so no source is completely silenced.
        represented = {r.collection for r in final_results}
        for col in collections:
            if col not in represented:
                col_best = next(
                    (r for r in all_ranked if r.collection == col), None
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
        # Step 8 — Parallel streaming explanation generation
        # Each explanation streams tokens via a shared queue so multiple LLM
        # streams can run concurrently and their deltas are interleaved.
        # ------------------------------------------------------------------
        ExplainEvent = tuple[str, str, str]  # (kind, chunk_id, data)
        queue: asyncio.Queue[ExplainEvent] = asyncio.Queue()
        accumulated: dict[str, str] = {c.chunk_id: "" for c in final_results}

        async def _stream_one(chunk: RankedChunk) -> None:
            try:
                async for delta in stream_explanation(
                    chunk.content, chunk.reference, chunk.collection, query
                ):
                    accumulated[chunk.chunk_id] += delta
                    await queue.put(("delta", chunk.chunk_id, delta))
            except Exception as exc:
                logger.warning("_stream_one error for %s: %s", chunk.chunk_id, exc)
            finally:
                await queue.put(("done", chunk.chunk_id, ""))

        tasks = [asyncio.create_task(_stream_one(c)) for c in final_results]
        pending = len(final_results)
        try:
            while pending > 0:
                kind, chunk_id, data = await queue.get()
                if kind == "delta":
                    yield {"type": "explanation_delta", "chunk_id": chunk_id, "delta": data}
                elif kind == "done":
                    pending -= 1
                    full_text = accumulated[chunk_id][:2000]
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE retrievals SET explanation = $1 WHERE search_id = $2 AND chunk_id = $3",
                            full_text,
                            uuid.UUID(search_id),
                            uuid.UUID(chunk_id),
                        )
        finally:
            for t in tasks:
                t.cancel()

        # ------------------------------------------------------------------
        # Step 9 — Yield done
        # ------------------------------------------------------------------
        yield {"type": "done", "search_id": search_id, "result_count": len(final_results)}

    except Exception:
        logger.exception("run_search_pipeline unhandled error")
        yield {"type": "error", "detail": "Search failed. Please try again."}
