import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.pipelines.registry import PIPELINES
from app.rag.pipelines import runner
from app.rag.steps.types import RankedChunk, PipelineResult


def test_registry_has_four_variants():
    assert set(PIPELINES.keys()) == {"s2_5_cohere", "s2_5_haiku", "s4_cohere", "s4_haiku"}


def test_registry_configs_have_required_fields():
    for name, config in PIPELINES.items():
        assert config.name == name
        assert hasattr(config.hyde_module, "run")
        assert hasattr(config.rerank_module, "run")


@pytest.mark.asyncio
async def test_runner_returns_pipeline_result():
    config = PIPELINES["s4_haiku"]
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
        patch("app.rag.steps.rerank_haiku.run", new=AsyncMock(return_value=[fake_chunk])),
        patch("app.rag.steps.dedup.run", new=AsyncMock(return_value=[fake_chunk])),
        patch("app.rag.steps.collection_guarantee.run", return_value=[fake_chunk]),
        patch("app.rag.steps.quota_cap.run", return_value=[fake_chunk]),
    ):
        result = await runner.run(config, "test query", ["bible"], quota=4)

    assert isinstance(result, PipelineResult)
    assert result.pipeline == "s4_haiku"
    assert len(result.chunks) == 1
    assert result.total_cost >= 0
    assert len(result.step_timings) > 0
