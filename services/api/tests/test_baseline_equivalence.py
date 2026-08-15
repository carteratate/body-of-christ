"""Pin pointwise candidate sizing and ranking semantics within contract v1.

The structured positional rollout is an explicit methodology boundary from the
former free-text UUID baseline. Within this version, these assertions pin candidate
counts, per-collection call shape, document text, and the scoring rubric.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.rag.pipelines.registry import PIPELINES
from app.rag.steps import budget, rerank
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import pointwise
from app.rag.steps.rerank import RerankConfig
from app.rag.steps.types import ChunkCandidate, RankedChunk


def _cand(i: int, collection: str = "bible") -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content=f"content {i}",
        reference=f"Ref {i}", collection=collection, document_id="d1",
        document_title="T", author=None, rrf_score=1.0 - i * 0.01,
    )


def test_production_pipeline_is_llm_only_pointwise_haiku():
    config = PIPELINES["hyde_haiku"]
    assert config.rerank.mode == "llm_only"
    assert config.rerank.llm_provider == "haiku"
    assert config.rerank.use_cohere is False
    assert config.retrieval.hyde is True
    assert config.retrieval.fts is True


def test_baseline_retrieval_sizing_is_not_budget_derived():
    """llm_only must receive (None, None) so retrieve_* keep quota x multiplier."""
    from app.rag.pipelines.runner import _pool_sizes

    assert _pool_sizes(PIPELINES["hyde_haiku"], quota=4) == (None, None)


def test_cohere_modes_do_get_budget_derived_sizing():
    from app.rag.pipelines.runner import _pool_sizes

    k, top_n = _pool_sizes(PIPELINES["hyde_cohere_haiku"], quota=4)
    assert k is not None and top_n == settings.cohere_max_pool


@pytest.mark.asyncio
@pytest.mark.parametrize("quota", [3, 4, 5])
async def test_retrieve_vector_without_k_uses_historical_limit(quota):
    """The optional k parameter must default to quota x candidate_multiplier, so a
    baseline run retrieves exactly what it always did."""
    from app.rag.steps import retrieve_vector

    limits: list[int] = []

    async def _spy(collection, vec, limit, label):
        limits.append(limit)
        return []

    with patch.object(retrieve_vector, "_search_vector", new=_spy):
        await retrieve_vector.run([0.1] * 16, {}, ["bible"], quota)

    assert limits and set(limits) == {quota * settings.candidate_multiplier}


@pytest.mark.asyncio
async def test_retrieve_vector_with_k_overrides_the_historical_limit():
    from app.rag.steps import retrieve_vector

    limits: list[int] = []

    async def _spy(collection, vec, limit, label):
        limits.append(limit)
        return []

    with patch.object(retrieve_vector, "_search_vector", new=_spy):
        await retrieve_vector.run([0.1] * 16, {}, ["bible"], 4, None, k=37)

    assert set(limits) == {37}


@pytest.mark.asyncio
@pytest.mark.parametrize("quota", [3, 4, 5])
async def test_llm_only_sends_exactly_quota_times_multiplier_candidates(quota):
    captured: list[int] = []

    async def _capture(cands, query, q, tracker, provider, step="x"):
        captured.append(len(cands))
        return []

    with patch("app.rag.steps.llm_rerank.pointwise.rerank_collection", new=_capture):
        await rerank.run(
            PIPELINES["hyde_haiku"].rerank,
            {"bible": [_cand(i) for i in range(100)]}, "q", quota, CostTracker(),
        )
    assert captured == [quota * settings.candidate_multiplier]


@pytest.mark.asyncio
async def test_llm_only_makes_one_call_per_collection():
    calls: list[str] = []

    async def _capture(cands, query, q, tracker, provider, step="x"):
        calls.append(cands[0].collection if cands else "?")
        return []

    cols = ["bible", "summa", "canon-law"]
    with patch("app.rag.steps.llm_rerank.pointwise.rerank_collection", new=_capture):
        await rerank.run(
            PIPELINES["hyde_haiku"].rerank,
            {c: [_cand(i, c) for i in range(5)] for i, c in enumerate(cols)},
            "q", 4, CostTracker(),
        )
    assert sorted(calls) == sorted(cols)


def test_pointwise_prompt_preserves_scoring_contract_with_structured_output():
    """Only the serialization contract may differ from the historical baseline."""
    p = pointwise._RERANK_SYSTEM
    assert "You are evaluating Catholic theological passages" in p
    assert "SCORING — use the FULL 0.0-1.0 range" in p
    assert "Set include=false if score < 0.35." in p
    assert "Reserve this for passages that explicitly address the exact topic" in p
    assert "Include only if better passages are scarce" in p
    assert "same biblical book, same encyclical, same author and work" in p
    assert "reduced or no penalty even when they share a source" in p
    assert "sources, genres, or traditions" in p
    assert 'overlap_verdict="redundant"' in p
    assert 'overlap_verdict="complementary"' in p
    assert "SAME POSITIONAL ORDER" in p
    # Historical prompt was 2,592 chars. Positional/schema instructions add only a
    # small delta; a larger movement means ranking semantics changed too.
    assert abs(len(p) - 2592) < 50, f"prompt length moved to {len(p)}"


def test_pointwise_passage_format_uses_position_and_data_boundary():
    formatted = pointwise._format_passages([_cand(1)])
    assert json.loads(formatted) == {
        "position": 0, "source": "Ref 1", "passage": "content 1",
    }
    assert "00000000" not in formatted


def test_pointwise_uses_a_4096_token_budget_not_the_listwise_one():
    """The listwise cap (8192) must not leak into the pointwise baseline."""
    assert pointwise.POINTWISE_MAX_TOKENS == 4096


def test_hoisted_thresholds_default_to_their_previous_literals():
    """Hoisting these into settings must not have changed any value."""
    assert settings.guarantee_min_score == 0.25
    assert settings.cohere_include_floor == 0.25
    assert settings.pointwise_score_cutoff == 0.25


@pytest.mark.asyncio
async def test_llm_only_returns_the_same_list_for_both_outputs():
    """llm_only has no second stage, so `all_scored` is `ranked` — the collection
    guarantee sees exactly what it saw before."""
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000001", content="c", reference=None,
        collection="bible", document_id="d1", document_title="T", author=None,
        reranker_score=0.7,
    )

    async def _fixed(cands, query, q, tracker, provider, step="x"):
        return [chunk]

    with patch("app.rag.steps.llm_rerank.pointwise.rerank_collection", new=_fixed):
        ranked, all_scored = await rerank.run(
            RerankConfig(use_cohere=False, llm_provider="haiku"),
            {"bible": [_cand(0)]}, "q", 4, CostTracker(),
        )
    assert ranked is all_scored


def test_fts_ablation_holds_retrieval_depth_constant():
    """Removing FTS must not also deepen the remaining dense paths, or the ablation
    changes two variables and measures neither. retrieval_k scales UP as paths are
    removed (3 paths -> 50, 2 paths -> 60), so the ablation pins k to its control's."""
    from app.rag.pipelines.runner import _pool_sizes

    control_k, _ = _pool_sizes(PIPELINES["hyde_cohere_haiku"], quota=4)
    ablation_k, _ = _pool_sizes(PIPELINES["hyde_nolex_cohere_haiku"], quota=4)
    assert control_k == ablation_k, (
        f"FTS ablation confounded: control k={control_k}, ablation k={ablation_k}"
    )


def test_pointwise_fallback_cannot_outrank_a_real_score():
    """The production path's fallback used to emit 1.00/0.99/0.98 with include=True,
    so one failed collection sorted above every genuinely scored chunk."""
    from app.rag.steps.llm_rerank.pointwise import fallback_ranked

    fb = fallback_ranked([_cand(i) for i in range(5)], quota=5)
    assert max(r.reranker_score for r in fb) < settings.pointwise_score_cutoff
    assert all(r.include for r in fb)


def test_pointwise_fallback_preserves_dedup_slack_beyond_quota():
    from app.rag.steps.llm_rerank.pointwise import fallback_ranked

    candidates = [_cand(i) for i in range(30)]
    fallback = fallback_ranked(candidates, quota=4)
    assert len(fallback) == len(candidates)
    assert all(chunk.include for chunk in fallback)
