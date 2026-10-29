"""Pin candidate sizing and the terminal reranker's scoring contract.

Every pipeline runs Cohere, alone or followed by one listwise LLM call; the
single-stage pointwise LLM mode was removed in October 2026.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import settings
from app.rag.pipelines.registry import PIPELINES
from app.rag.steps.rerank import RerankConfig


def test_a_pipeline_without_cohere_is_rejected():
    """The pointwise `llm_only` mode is gone, so an LLM alone is not a pipeline."""
    with pytest.raises(ValueError, match="must enable Cohere"):
        RerankConfig(use_cohere=False, llm_provider="haiku")


def test_cohere_modes_do_get_budget_derived_sizing():
    from app.rag.pipelines.runner import _pool_sizes

    k, top_n = _pool_sizes(PIPELINES["hyde_cohere_haiku"], quota=4)
    assert k is not None and top_n == settings.cohere_max_pool


@pytest.mark.asyncio
@pytest.mark.parametrize("quota", [3, 4, 5])
async def test_retrieve_vector_without_k_uses_the_default_limit(quota):
    """Pipelines always pass k; a direct caller that omits it gets
    quota x candidate_multiplier."""
    from app.rag.steps import retrieve_vector

    limits: list[int] = []

    async def _spy(collection, vec, limit, label):
        limits.append(limit)
        return []

    with patch.object(retrieve_vector, "_search_vector", new=_spy):
        await retrieve_vector.run([0.1] * 16, {}, ["bible"], quota)

    assert limits and set(limits) == {quota * settings.candidate_multiplier}


@pytest.mark.asyncio
async def test_retrieve_vector_with_k_overrides_the_default_limit():
    from app.rag.steps import retrieve_vector

    limits: list[int] = []

    async def _spy(collection, vec, limit, label):
        limits.append(limit)
        return []

    with patch.object(retrieve_vector, "_search_vector", new=_spy):
        await retrieve_vector.run([0.1] * 16, {}, ["bible"], 4, None, k=37)

    assert set(limits) == {37}


def test_hoisted_thresholds_default_to_their_previous_literals():
    """Hoisting these into settings must not have changed any value."""
    assert settings.guarantee_min_score == 0.25
    assert settings.cohere_include_floor == 0.25


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


def test_listwise_prompt_pins_its_scoring_contract_too():
    """The listwise prompt is the production terminal reranker's. Pin the scoring
    semantics plus the role guidance, so an unversioned edit fails here."""
    from app.rag.steps.llm_rerank.listwise import _LISTWISE_SYSTEM as p

    assert "First assign relevance independently of overlap" in p
    assert "Scores at least 0.30 require an identifiable contribution" in p
    assert "reduce a weaker repetition by at most 0.05" in p
    assert "Never cross the 0.30 eligibility boundary" in p
    assert "unchanged positional order" in p
    assert "Roles determine attribution, not fixed scores" in p
    assert "not the author's conclusion" in p
    assert "Section, canon, and verse locators" in p
    assert abs(len(p) - 4379) < 50, f"prompt length moved to {len(p)}"
