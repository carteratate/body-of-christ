import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.pipelines.registry import PIPELINES
from app.rag.pipelines import runner
from app.rag.steps.types import RankedChunk, PipelineResult


_EXPECTED_PIPELINES = {
    "hyde_haiku", "nohyde_haiku", "hyde_luna",
    "hyde_cohere", "nohyde_cohere",
    "hyde_cohere_haiku", "hyde_cohere_luna", "nohyde_cohere_haiku",
    "hyde_nolex_cohere_haiku",
}


def test_registry_keys_match_expected_variants():
    assert set(PIPELINES.keys()) == _EXPECTED_PIPELINES


def test_registry_configs_have_required_fields():
    for name, config in PIPELINES.items():
        assert config.name == name
        assert isinstance(config.retrieval.hyde, bool)
        assert isinstance(config.retrieval.fts, bool)
        # Every pipeline must rerank somehow; RerankConfig rejects neither-enabled.
        assert config.rerank.use_cohere or config.rerank.llm_provider
        assert config.rerank.mode in {"llm_only", "cohere_only", "both"}


def test_production_pipeline_is_registered():
    """pipeline.py's production choice must exist, or every live search 500s."""
    from app.rag.pipeline import _PRODUCTION_PIPELINE

    assert _PRODUCTION_PIPELINE in PIPELINES


def test_production_pipeline_is_round_three_winner():
    from app.rag.pipeline import _PRODUCTION_PIPELINE

    assert _PRODUCTION_PIPELINE == "hyde_cohere_luna"


@pytest.mark.asyncio
async def test_runner_returns_pipeline_result():
    config = PIPELINES["nohyde_haiku"]
    fake_chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000001",
        content="test", reference=None, collection="bible",
        document_id="d1", document_title="T", author=None, reranker_score=0.9,
    )
    with (
        patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1] * 1536)),
        patch("app.rag.steps.hyde_none.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_vector.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_fts.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.rrf.run", return_value={"bible": []}),
        patch("app.rag.steps.rerank.run", new=AsyncMock(return_value=([fake_chunk], [fake_chunk]))),
        patch("app.rag.steps.dedup.run", new=AsyncMock(return_value=[fake_chunk])),
        patch("app.rag.steps.collection_guarantee.run", return_value=[fake_chunk]),
        patch("app.rag.steps.quota_cap.run", return_value=[fake_chunk]),
    ):
        result = await runner.run(config, "test query", ["bible"], quota=4)

    assert isinstance(result, PipelineResult)
    assert result.pipeline == "nohyde_haiku"
    assert len(result.chunks) == 1
    assert result.total_cost >= 0
    assert len(result.step_timings) > 0


@pytest.mark.asyncio
async def test_runner_drives_a_cohere_pipeline_end_to_end():
    """Cohere pipelines were previously unexercised through the runner, which let a
    rerank return-type change break them while the suite stayed green."""
    config = PIPELINES["hyde_cohere_haiku"]
    fake_chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000002",
        content="test", reference=None, collection="bible",
        document_id="d1", document_title="T", author=None, reranker_score=0.8,
    )
    with (
        patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1] * 1536)),
        patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_vector.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_fts.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.rrf.run", return_value={"bible": []}),
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value={"bible": [fake_chunk]})),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool",
              new=AsyncMock(return_value=[fake_chunk])),
    ):
        result = await runner.run(config, "test query", ["bible"], quota=4)

    assert isinstance(result, PipelineResult)
    assert result.pipeline == "hyde_cohere_haiku"
    assert [c.chunk_id for c in result.chunks] == [fake_chunk.chunk_id]
