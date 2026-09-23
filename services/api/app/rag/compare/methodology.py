"""Canonical, non-secret identity for reproducible pipeline comparisons."""
from __future__ import annotations

import dataclasses
import hashlib
import json

from app.config import settings
from app.rag.compare.judge import WEIGHTS, _JUDGE_MODEL
from app.rag.pipelines.registry import PIPELINES
from app.rag.steps.rerank import contract_version
from app.rag.steps.llm_rerank.pointwise import POINTWISE_MAX_TOKENS
from app.rag.steps.rerank_cohere import COHERE_RERANK_MODEL
from app.rag.steps import hyde_luna
from app.rag.steps.llm_rerank import openai_provider


def snapshot(pipeline_names: list[str]) -> dict:
    """Describe every material configured input to retrieval/rerank evaluation."""
    return {
        "deployment": {
            "build_id": settings.evaluation_build_id,
            "corpus_id": settings.evaluation_corpus_id,
        },
        "pipelines": {
            name: {
                "config": (
                    dataclasses.asdict(PIPELINES[name]) if name in PIPELINES else None
                ),
                "rerank_contract_version": (
                    contract_version(PIPELINES[name].rerank)
                    if name in PIPELINES else None
                ),
            }
            for name in pipeline_names
        },
        "models": {
            "embedding": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dims,
            "hyde": (
                settings.hyde_luna_model
                if settings.hyde_passage_provider == "luna"
                else settings.hyde_model
            ),
            "hyde_passage_provider": settings.hyde_passage_provider,
            "hyde_genre_selector": (
                settings.hyde_genre_luna_model
                if settings.hyde_genre_provider == "luna"
                else settings.hyde_model
            ),
            "hyde_genre_provider": settings.hyde_genre_provider,
            "rerank_haiku": settings.rerank_model,
            "rerank_luna": settings.rerank_luna_model,
            "judge": _JUDGE_MODEL,
            "cohere_rerank": COHERE_RERANK_MODEL,
        },
        "rerank_settings": {
            name: getattr(settings, name)
            for name in (
                "candidate_multiplier", "cohere_include_floor",
                "cohere_keep_score_floor", "cohere_keep_extra", "cohere_max_pool",
                "cohere_pool_safety", "cohere_max_tokens_per_doc",
                "llm_pool_global_cap", "llm_pool_floor_per_col",
                "llm_rerank_max_tokens", "listwise_include_floor",
                "pointwise_score_cutoff", "llm_fallback_score_base",
                "guarantee_min_score",
                "retrieval_k_min", "retrieval_k_max", "judge_timeout_s",
                "rrf_k",
            )
        },
        # `rrf_k` is not here: it is a per-pipeline axis, so each entry above
        # carries its own override via `dataclasses.asdict`, and the default the
        # unpinned ones resolve to is recorded in `rerank_settings` (it is a
        # setting). Both halves are needed — an unpinned pipeline records
        # `rrf_k: None`, so without the setting two deployments on different
        # `RRF_K` values would fingerprint identically while merging differently.
        "fixed_parameters": {
            "pointwise_max_tokens": POINTWISE_MAX_TOKENS,
            "listwise_max_tokens": settings.llm_rerank_max_tokens,
            "hyde_luna_concurrency": settings.hyde_luna_concurrency,
            "hyde_luna_reasoning_effort": hyde_luna.REASONING_EFFORT,
            "rerank_luna_reasoning_effort": openai_provider.REASONING_EFFORT,
        },
        "judge_weights": dict(WEIGHTS),
    }


def fingerprint(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
