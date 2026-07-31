"""`hyde_haiku` must behave exactly as the pre-refactor `s2_5_haiku` did.

If the baseline shifts, every A/B measurement against it is meaningless — a
"cohere is better" result could just be "the baseline got worse". These assertions
pin the properties that would silently move: candidate counts, per-collection call
shape, document text, and the prompt itself.
"""
from __future__ import annotations

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


def test_pointwise_prompt_is_unchanged():
    """The system prompt drives every score; a reword would silently reshape the
    baseline. These invariants come from the pre-refactor prompt text."""
    p = pointwise._RERANK_SYSTEM
    assert "You are evaluating Catholic theological passages" in p
    assert "SCORING — use the FULL 0.0-1.0 range" in p
    assert "Set include=false if score < 0.35." in p
    assert '"overlap_verdict"' in p
    # 2592 chars / ~723 tokens at the time of extraction. A drift beyond a small
    # margin means the prompt was edited, not merely reformatted.
    assert abs(len(p) - 2592) < 50, f"prompt length moved to {len(p)}"


def test_pointwise_passage_format_is_unchanged():
    formatted = pointwise._format_passages([_cand(1)])
    assert formatted == "[00000000-0000-0000-0000-000000000001] Ref 1: content 1"


def test_pointwise_uses_a_4096_token_budget_not_the_listwise_one():
    """The listwise cap (8192) must not leak into the pointwise baseline."""
    import inspect

    src = inspect.getsource(pointwise.rerank_collection)
    assert "4096" in src
    assert "llm_rerank_max_tokens" not in src


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
    assert max(r.reranker_score for r in fb) < 0.6
    assert all(r.reranker_score >= settings.pointwise_score_cutoff for r in fb)
