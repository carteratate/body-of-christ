"""Reciprocal Rank Fusion merge across retrieval strategy result lists."""
from __future__ import annotations

import logging

from app.config import settings
from app.rag.steps.types import ChunkCandidate

logger = logging.getLogger(__name__)

_RRF_K = 60
_PER_STRATEGY_TOP_K = 3


def _rrf_merge(result_lists: list[list[dict]], top_n: int) -> list[dict]:
    scores: dict[str, float] = {}
    metadata: dict[str, dict] = {}

    for result_list in result_lists:
        for rank_0, row in enumerate(result_list):
            rank = rank_0 + 1
            chunk_id = str(row["id"])
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
            if chunk_id not in metadata:
                metadata[chunk_id] = {
                    "chunk_id": chunk_id,
                    "content": row["content"],
                    "reference": row.get("reference"),
                    "collection": row["collection"],
                    "document_id": str(row["document_id"]),
                    "document_title": row["document_title"],
                    "author": row.get("author"),
                    "anchor": row.get("anchor"),
                    "chapter_key": row.get("chapter_key"),
                    "position": row.get("position"),
                    "annotation": row.get("annotation"),
                    # First-writer-wins, like every key here: whichever strategy list
                    # sees the chunk first supplies it. Vector lists precede FTS and
                    # carry unit_label only for collections the payload reconcile has
                    # run for, so pre-reconcile this is None on the vector path and
                    # fetch_positions backfills it from Postgres before reranking.
                    "unit_label": row.get("unit_label"),
                }

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    selected: set[str] = set(sorted_ids[:top_n])
    for result_list in result_lists:
        for row in result_list[:_PER_STRATEGY_TOP_K]:
            selected.add(str(row["id"]))

    final_sorted = sorted(selected, key=lambda cid: scores.get(cid, 0.0), reverse=True)
    return [dict({**metadata[cid], "rrf_score": scores[cid]}) for cid in final_sorted]


def run(
    vector_results: dict[str, list[list[dict]]],
    fts_results: dict[str, list[dict]],
    quota: int,
    top_n: int | None = None,
) -> dict[str, list[ChunkCandidate]]:
    """Merge per-collection vector strategy lists + fts list using RRF.

    vector_results: col → list of strategy result lists (one per search vector)
    fts_results: col → single ranked list from FTS
    Returns: col → list[ChunkCandidate] sorted by RRF score descending
    """
    all_collections = set(vector_results) | set(fts_results)
    output: dict[str, list[ChunkCandidate]] = {}

    for col in all_collections:
        all_lists: list[list[dict]] = list(vector_results.get(col, []))
        if col in fts_results:
            all_lists.append(fts_results[col])
        if not all_lists:
            continue

        effective_top_n = (
            top_n if top_n is not None else quota * settings.candidate_multiplier
        )
        merged = _rrf_merge(all_lists, top_n=effective_top_n)
        output[col] = [
            ChunkCandidate(
                chunk_id=e["chunk_id"],
                content=e["content"],
                reference=e.get("reference"),
                collection=e["collection"],
                document_id=e["document_id"],
                document_title=e["document_title"],
                author=e.get("author"),
                rrf_score=e["rrf_score"],
                anchor=e.get("anchor"),
                chapter_key=e.get("chapter_key"),
                position=e.get("position"),
                annotation=e.get("annotation"),
                unit_label=e.get("unit_label"),
            )
            for e in merged
        ]

    return output
