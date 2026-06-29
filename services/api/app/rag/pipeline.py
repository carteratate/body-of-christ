"""RAG search pipeline — orchestrates HyDE, embedding, retrieval, scoring, and explanation."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from app.config import settings
from app.db import get_pool
from app.rag.api_keys import get_client, get_key_for, get_semaphore
from app.rag.dedup import apply_dedup
from app.rag.steps.embed import run as embed_text
from app.rag.steps.explain import stream as stream_explanation
from app.rag.steps.hyde_s25 import generate_hyde_passages, choose_bible_hyde_genres
from app.rag.steps.retrieve_vector import run as retrieve_vector
from app.rag.steps.retrieve_fts import run as retrieve_fts
from app.rag.steps.rrf import run as rrf_merge
from app.rag.steps.fetch_positions import run as fetch_positions
from app.rag.steps.types import ChunkCandidate, RankedChunk
from app.rag.steps.rerank_haiku import run as rerank_haiku
from app.rag.steps.cost_tracker import CostTracker
from app.rag.constants import VALID_COLLECTIONS

logger = logging.getLogger(__name__)


async def _hyde_and_embed(
    query: str,
    col: str,
) -> tuple[str, list[list[float]]]:
    """Generate HyDE passages for one collection then embed them immediately.

    Routes to the correct API key and acquires the key's semaphore for
    concurrency control. Returns (collection, [embedding_vectors]).
    """
    key = get_key_for(col)
    client = get_client(key)
    semaphore = get_semaphore(key)

    if col == "bible":
        # S2.5: one Haiku call picks 3 genres before generation, so only 4 calls
        # total for bible (1 selector + 3 generators) instead of 8.
        selected_genres = await choose_bible_hyde_genres(query, client)
        passages = await generate_hyde_passages(query, col, client, semaphore, selected_genres=selected_genres)
    else:
        passages = await generate_hyde_passages(query, col, client, semaphore)

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

        # ------------------------------------------------------------------
        # Steps 1+2 — query embedding + per-collection HyDE → embed (parallel)
        # ------------------------------------------------------------------
        all_results = await asyncio.gather(
            embed_text(query),
            *[_hyde_and_embed(query, col) for col in collections],
            return_exceptions=True,
        )

        query_vec_result = all_results[0]
        hyde_embed_results = all_results[1:]

        _t1 = time.perf_counter()
        logger.info("pipeline timing: steps1_2=%.2fs collections=%s", _t1 - _t0, collections)

        if isinstance(query_vec_result, BaseException):
            logger.error("Query embedding failed: %s", query_vec_result)
            yield {"type": "error", "detail": "Embedding failed"}
            return
        query_vec: list[float] = query_vec_result

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
        # Step 3 — Retrieval (vector + FTS) → RRF merge → position fill
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "searching", "collections": collections}

        per_col_hyde_vecs: dict[str, list[list[float]]] = {}
        for col in collections:
            vecs = []
            if per_col_hyde_vec.get(col) is not None:
                vecs.append(per_col_hyde_vec[col])
            vecs.extend(per_col_extra_hyde_vecs.get(col, []))
            if vecs:
                per_col_hyde_vecs[col] = vecs

        vec_raw = await retrieve_vector(query_vec, per_col_hyde_vecs, collections, quota, user_id)
        fts_raw = await retrieve_fts(query, collections, quota, user_id)
        merged_per_col = rrf_merge(vec_raw, fts_raw, quota)
        await fetch_positions(merged_per_col)
        per_collection_candidates = list(merged_per_col.values())

        _t3 = time.perf_counter()
        logger.info("pipeline timing: step3(retrieval)=%.2fs", _t3 - _t1)

        if not per_collection_candidates:
            yield {"type": "done", "search_id": str(uuid.uuid4()), "result_count": 0}
            return

        # ------------------------------------------------------------------
        # Step 4 — Haiku reranking per collection (parallel)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "ranking"}
        _dummy_tracker = CostTracker()
        candidates_by_col = {
            cands[0].collection: cands
            for cands in per_collection_candidates
            if cands
        }
        all_scored = await rerank_haiku(candidates_by_col, query, quota, _dummy_tracker)

        _t4 = time.perf_counter()
        logger.info("pipeline timing: step4(rerank)=%.2fs", _t4 - _t3)

        # ------------------------------------------------------------------
        # Step 5 — Global sort → dedup → per-collection guarantee + quota
        # ------------------------------------------------------------------
        _GUARANTEE_MIN_SCORE = 0.25

        all_sorted = sorted(all_scored, key=lambda c: c.reranker_score, reverse=True)

        # 5b. Combined dedup: position proximity + cosine threshold + per-title cap
        deduped = await apply_dedup(all_sorted)

        # 5c. Collection guarantee: inject best chunk for any selected collection
        #     absent after dedup, if it clears the minimum score threshold.
        represented = {r.collection for r in deduped}
        for col in collections:
            if col not in represented:
                col_best = next(
                    (r for r in all_sorted
                     if r.collection == col and r.reranker_score >= _GUARANTEE_MIN_SCORE),
                    None,
                )
                if col_best:
                    deduped.append(col_best)

        # 5d. Per-collection quota cap
        col_counts: dict[str, int] = {}
        final_results: list[RankedChunk] = []
        for c in deduped:
            col_counts[c.collection] = col_counts.get(c.collection, 0) + 1
            if col_counts[c.collection] <= quota:
                final_results.append(c)

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
            logger.error("DB pool not available, skipping persistence")
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

        _t7 = time.perf_counter()
        logger.info(
            "pipeline timing: step7(db)=%.2fs total=%.2fs results=%d",
            _t7 - _t4, _t7 - _t0, len(final_results),
        )

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
