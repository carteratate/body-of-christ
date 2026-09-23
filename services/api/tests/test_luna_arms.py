"""Per-pipeline Luna model / reasoning-effort axes and the separate genre-pick model.

Production defaults must be untouched by these axes; evaluation arms must actually
reach the provider with what they pin, and be costed against it.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.rag.compare import shared_runner
from app.rag.pipelines import runner
from app.rag.pipelines.registry import PIPELINES, RetrievalConfig
from app.rag.steps import hyde_luna, hyde_s25
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import openai_provider
from app.rag.steps.rerank import RerankConfig
from app.rag.steps.types import RetrievalPath


def _completion(content: str = "A passage.", prompt: int = 10, completion: int = 20):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=content, refusal=None),
        )],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


# --- production defaults ----------------------------------------------------

def test_production_pipeline_pins_no_overrides():
    config = PIPELINES["hyde_cohere_luna"]
    assert runner.hyde_overrides(config.retrieval) == {}
    assert config.rerank.llm_model is None
    assert config.rerank.llm_reasoning_effort is None
    provider = config.rerank.provider()
    assert provider is openai_provider.PROVIDER
    assert provider.model_id == settings.rerank_luna_model
    assert provider.reasoning_effort == "medium"


def test_genre_pick_model_is_a_separate_setting_defaulting_to_5_6():
    assert settings.hyde_genre_luna_model == "gpt-5.6-luna"
    assert settings.hyde_luna_model == "gpt-5.6-luna"
    assert settings.rerank_luna_model == "gpt-5.6-luna"


# --- rerank config validation and provider overrides -------------------------

def test_rerank_overrides_are_rejected_for_non_luna_providers():
    with pytest.raises(ValueError, match="only supported"):
        RerankConfig(use_cohere=True, llm_provider="haiku", llm_model="gpt-6-luna")
    with pytest.raises(ValueError, match="only supported"):
        RerankConfig(use_cohere=True, llm_provider=None, llm_reasoning_effort="low")


def test_unknown_reasoning_effort_is_rejected_at_construction():
    with pytest.raises(ValueError, match="llm_reasoning_effort"):
        RerankConfig(use_cohere=True, llm_provider="luna", llm_reasoning_effort="minimal")


@pytest.mark.asyncio
async def test_rerank_arm_reaches_the_api_with_its_model_and_effort():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_completion('{"results": []}'))
    provider = PIPELINES["hyde6_cohere_luna6_low"].rerank.provider()

    with patch.object(openai_provider, "_client", client):
        await provider.score("sys", "user", 100, {"type": "object"})

    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["reasoning_effort"] == "low"
    # Cost is keyed on the model actually called.
    assert provider.model_id == "gpt-6-luna"


# --- HyDE model routing -------------------------------------------------------

@pytest.mark.asyncio
async def test_hyde_passage_override_is_called_and_costed_as_that_model():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_completion())
    tracker = CostTracker()

    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(8)),
        patch.object(settings, "hyde_passage_provider", "luna"),
    ):
        await hyde_s25.generate_hyde_passages(
            "q", "catechism", MagicMock(), asyncio.Semaphore(1),
            cost_tracker=tracker, passage_model="gpt-6-luna",
        )

    assert client.chat.completions.create.await_args.kwargs["model"] == "gpt-6-luna"
    # 10 in / 20 out at gpt-6-luna rates, not the 5.6 default's.
    assert tracker.breakdown()["hyde"] == pytest.approx((10 * 0.10 + 20 * 0.50) / 1e6)


@pytest.mark.asyncio
async def test_genre_pick_uses_its_own_setting_not_the_passage_model():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_completion('{"genres": ["free", "psalms", "ot-wisdom", "nt-epistles"]}'))

    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(8)),
        patch.object(settings, "hyde_luna_model", "passage-model"),
        patch.object(settings, "hyde_genre_luna_model", "genre-model"),
    ):
        await hyde_luna.select_bible_genres("sys", "q")

    assert client.chat.completions.create.await_args.kwargs["model"] == "genre-model"


@pytest.mark.asyncio
async def test_genre_override_is_called_and_costed_as_that_model():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_completion('{"genres": ["free", "psalms", "ot-wisdom", "nt-epistles"]}'))
    tracker = CostTracker()

    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(8)),
        patch.object(settings, "hyde_genre_provider", "luna"),
    ):
        await hyde_s25.choose_bible_hyde_genres(
            "q", MagicMock(), cost_tracker=tracker, genre_model="gpt-6-luna",
        )

    assert client.chat.completions.create.await_args.kwargs["model"] == "gpt-6-luna"
    assert tracker.breakdown()["hyde_genre_select"] == pytest.approx(
        (10 * 0.10 + 20 * 0.50) / 1e6)


def test_hyde_overrides_only_include_what_a_pipeline_pins():
    assert runner.hyde_overrides(RetrievalConfig()) == {}
    assert runner.hyde_overrides(PIPELINES["hyde6_cohere_luna"].retrieval) == {
        "passage_model": "gpt-6-luna", "genre_model": "gpt-5.6-luna",
    }
    assert runner.hyde_overrides(PIPELINES["hyde6_cohere_luna6"].retrieval) == {
        "passage_model": "gpt-6-luna", "genre_model": "gpt-6-luna",
    }


def test_hybrid_arm_pins_todays_production_genre_pick_and_reranker():
    arm = PIPELINES["hyde6_cohere_luna"]
    production = PIPELINES["hyde_cohere_luna"].rerank.provider()
    provider = arm.rerank.provider()
    assert (provider.model_id, provider.reasoning_effort) == (
        production.model_id, production.reasoning_effort)
    assert arm.retrieval.hyde_genre_luna_model == settings.hyde_genre_luna_model
    assert arm.rerank.use_cohere is True


# --- shared evaluation capture ----------------------------------------------

def _row(i: int) -> dict:
    return {
        "id": f"00000000-0000-0000-0000-{i:012d}", "content": f"chunk {i}",
        "reference": f"Ref {i}", "collection": "bible",
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "Doc", "author": None, "anchor": None,
        "position": i, "annotation": None,
    }


@pytest.mark.asyncio
async def test_shared_capture_draws_hyde_once_per_distinct_hyde_config():
    configs = [
        PIPELINES["hyde_cohere_luna"],
        PIPELINES["hyde_cohere_haiku"],           # same HyDE as production: shares it
        PIPELINES["hyde6_cohere_luna"],           # own HyDE model
        PIPELINES["hyde_cohere_luna_hydesample"],  # production HyDE, independent draw
    ]
    # Distinct rows per HyDE draw so a pool built from the wrong draw is detectable.
    draws = iter([[_row(i) for i in range(0, 50)],
                  [_row(i) for i in range(100, 150)],
                  [_row(i) for i in range(200, 250)]])

    async def vectors(*_a, **_kw):
        return {"bible": [RetrievalPath("hyde", next(draws))]}

    with (
        patch("app.rag.compare.shared_runner.embed.run", new=AsyncMock(return_value=[0.1])),
        patch("app.rag.compare.shared_runner.hyde_s25.run",
              new=AsyncMock(return_value={"bible": [[0.2]]})) as hyde,
        patch("app.rag.compare.shared_runner.retrieve_vector.run",
              new=AsyncMock(side_effect=vectors)),
        patch("app.rag.compare.shared_runner.retrieve_fts.run",
              new=AsyncMock(return_value={"bible": []})),
        patch("app.rag.compare.shared_runner.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
    ):
        artifacts = await shared_runner.capture("q", ["bible"], 4, configs)

    assert hyde.await_count == 3
    assert hyde.await_args_list[0].kwargs == {}
    assert hyde.await_args_list[1].kwargs == {
        "passage_model": "gpt-6-luna", "genre_model": "gpt-5.6-luna",
    }
    assert hyde.await_args_list[2].kwargs == {}

    def ids(name: str) -> set[str]:
        return {c.chunk_id for c in artifacts.candidate_pools[name]["bible"]}

    assert ids("hyde_cohere_luna") == ids("hyde_cohere_haiku")
    assert ids("hyde_cohere_luna").isdisjoint(ids("hyde6_cohere_luna"))
    assert ids("hyde_cohere_luna").isdisjoint(ids("hyde_cohere_luna_hydesample"))
    assert ids("hyde6_cohere_luna").isdisjoint(ids("hyde_cohere_luna_hydesample"))


@pytest.mark.asyncio
async def test_each_arm_reports_the_cost_of_its_own_hyde_draw():
    configs = [PIPELINES["hyde_cohere_luna"], PIPELINES["hyde6_cohere_luna"]]
    prices = {None: ("gpt-5.6-luna", 0.20), "gpt-6-luna": ("gpt-6-luna", 0.10)}

    async def hyde(query, collections, tracker, passage_model=None, **_kw):
        model, _ = prices[passage_model]
        tracker.record("hyde", model, input_tokens=1_000_000, output_tokens=0)
        return {}

    with (
        patch("app.rag.compare.shared_runner.embed.run", new=AsyncMock(return_value=[0.1])),
        patch("app.rag.compare.shared_runner.hyde_s25.run", new=hyde),
        patch("app.rag.compare.shared_runner.retrieve_vector.run",
              new=AsyncMock(return_value={"bible": []})),
        patch("app.rag.compare.shared_runner.retrieve_fts.run",
              new=AsyncMock(return_value={"bible": []})),
        patch("app.rag.compare.shared_runner.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
    ):
        artifacts = await shared_runner.capture("q", ["bible"], 4, configs)

    assert artifacts.hyde_costs["hyde_cohere_luna"]["hyde"] == pytest.approx(0.20)
    assert artifacts.hyde_costs["hyde6_cohere_luna"]["hyde"] == pytest.approx(0.10)
    # The shared total still carries every draw.
    assert artifacts.cost_breakdown["hyde"] == pytest.approx(0.30)
    restored = shared_runner.SharedArtifacts.from_dict(artifacts.to_dict())
    assert restored.hyde_costs == artifacts.hyde_costs


def test_artifacts_from_before_per_draw_accounting_still_load():
    legacy = {
        "query": "q", "collections": ["bible"], "quota": 4, "candidate_pools": {},
        "cost_breakdown": {}, "total_cost": 0.0, "duration_s": 1.0,
    }
    assert shared_runner.SharedArtifacts.from_dict(legacy).hyde_costs == {}


def test_cost_tracker_merge_sums_steps_and_eligibility():
    a, b = CostTracker(), CostTracker()
    a.record("hyde", "gpt-5.6-luna", input_tokens=1_000_000, output_tokens=0)
    b.record("hyde", "gpt-6-luna", input_tokens=1_000_000, output_tokens=0)
    b.record("x", "not-a-model", input_tokens=1, output_tokens=1)
    a.merge(b)
    assert a.breakdown()["hyde"] == pytest.approx(0.30)
    assert a.cost_eligible is False
