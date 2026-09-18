"""Reciprocal Rank Fusion merge across retrieval strategy result lists."""
from __future__ import annotations

import logging

from app.config import settings
from app.rag.steps.types import ChunkCandidate, RetrievalPath

logger = logging.getLogger(__name__)

# Two families at rank r outrank one family at rank 1 when r < k + 2, so k sets the
# rank at which agreement stops beating precision. The usual 60 comes from Cormack
# et al. (2009), tuned on TREC runs 1000 deep; every list here is `budget.retrieval_k`
# deep — 50 in production — which put that crossover at rank 62, past the end of every
# list we produce, leaving rank as a tiebreak on a three-way vote (hyde/query/fts,
# since retrieve_vector collapses all HyDE genres into one `max` vote). 20 puts the
# crossover at rank 22, roughly the top 40% of a 50-deep list: agreement still wins
# where both paths ranked a chunk highly, and rank carries real weight below that.
# It is also what _PER_STRATEGY_TOP_K already implies — force-admitting each path's
# top 3 asserts that a single path's best hits are trustworthy.
_RRF_K = 20
_PER_STRATEGY_TOP_K = 3


def _rrf_merge(paths: list[RetrievalPath], top_n: int) -> list[dict]:
    family_scores: dict[str, dict[str, float]] = {}
    metadata: dict[str, dict] = {}

    for path in paths:
        for rank_0, row in enumerate(path.rows):
            rank = rank_0 + 1
            chunk_id = str(row["id"])
            scores_for_chunk = family_scores.setdefault(chunk_id, {})
            contribution = 1.0 / (_RRF_K + rank)
            scores_for_chunk[path.family] = max(
                scores_for_chunk.get(path.family, 0.0), contribution,
            )
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

    scores = {chunk_id: sum(by_family.values()) for chunk_id, by_family in family_scores.items()}
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    selected: set[str] = set(sorted_ids[:top_n])
    for path in paths:
        for row in path.rows[:_PER_STRATEGY_TOP_K]:
            selected.add(str(row["id"]))

    final_sorted = sorted(selected, key=lambda cid: scores.get(cid, 0.0), reverse=True)
    return [dict({**metadata[cid], "rrf_score": scores[cid]}) for cid in final_sorted]


def run(
    vector_results: dict[str, list[RetrievalPath]],
    fts_results: dict[str, list[dict]],
    quota: int,
    top_n: int | None = None,
) -> dict[str, list[ChunkCandidate]]:
    """Merge per-collection paths using one best vote per family.

    All HyDE paths share one family; the original query and FTS vote independently.
    vector_results: col → labeled ranked paths (one per search vector)
    fts_results: col → single ranked list from FTS
    Returns: col → list[ChunkCandidate] sorted by RRF score descending
    """
    all_collections = set(vector_results) | set(fts_results)
    output: dict[str, list[ChunkCandidate]] = {}

    for col in all_collections:
        paths = list(vector_results.get(col, []))
        if col in fts_results:
            paths.append(RetrievalPath(family="fts", rows=fts_results[col]))
        if not paths:
            continue

        effective_top_n = (
            top_n if top_n is not None else quota * settings.candidate_multiplier
        )
        merged = _rrf_merge(paths, top_n=effective_top_n)
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
