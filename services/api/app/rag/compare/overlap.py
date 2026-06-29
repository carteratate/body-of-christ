# services/api/app/rag/compare/overlap.py
"""Structural overlap analysis across pipeline results. No LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.rag.steps.types import PipelineResult


@dataclass
class OverlapReport:
    shared: list[str]                      # chunk_ids in ALL pipelines
    partial: dict[str, list[str]]          # chunk_ids in some → which pipelines
    unique: dict[str, list[str]]           # chunk_ids in exactly one → which pipeline
    rank_divergence: dict[str, dict]       # shared chunks: rank per pipeline + delta
    score_delta: dict[str, dict]           # shared chunks: score per pipeline + delta


def run(results: list[PipelineResult]) -> OverlapReport:
    """Compute chunk overlap statistics across pipeline results."""
    if not results:
        return OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})

    # Build per-pipeline chunk sets and rank/score maps
    pipeline_chunk_ids: dict[str, set[str]] = {}
    rank_maps: dict[str, dict[str, int]] = {}
    score_maps: dict[str, dict[str, float]] = {}

    for result in results:
        pname = result.pipeline
        pipeline_chunk_ids[pname] = {c.chunk_id for c in result.chunks}
        rank_maps[pname] = {c.chunk_id: i for i, c in enumerate(result.chunks)}
        score_maps[pname] = {c.chunk_id: c.reranker_score for c in result.chunks}

    all_chunk_ids: set[str] = set()
    for ids in pipeline_chunk_ids.values():
        all_chunk_ids.update(ids)

    n_pipelines = len(results)
    shared: list[str] = []
    partial: dict[str, list[str]] = {}
    unique: dict[str, list[str]] = {}

    for chunk_id in all_chunk_ids:
        pipelines_with_chunk = [
            p for p, ids in pipeline_chunk_ids.items() if chunk_id in ids
        ]
        if len(pipelines_with_chunk) == n_pipelines:
            shared.append(chunk_id)
        elif len(pipelines_with_chunk) == 1:
            unique[chunk_id] = pipelines_with_chunk
        else:
            partial[chunk_id] = pipelines_with_chunk

    # Rank divergence and score delta for shared chunks
    rank_divergence: dict[str, dict] = {}
    score_delta: dict[str, dict] = {}

    for chunk_id in shared:
        ranks = {p: rank_maps[p][chunk_id] for p in rank_maps if chunk_id in rank_maps[p]}
        scores = {p: score_maps[p][chunk_id] for p in score_maps if chunk_id in score_maps[p]}
        rank_values = list(ranks.values())
        score_values = list(scores.values())
        rank_divergence[chunk_id] = {
            **ranks,
            "delta": max(rank_values) - min(rank_values) if rank_values else 0,
        }
        score_delta[chunk_id] = {
            **scores,
            "delta": round(max(score_values) - min(score_values), 4) if score_values else 0,
        }

    return OverlapReport(
        shared=shared,
        partial=partial,
        unique=unique,
        rank_divergence=rank_divergence,
        score_delta=score_delta,
    )
