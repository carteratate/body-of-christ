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


def test_empty_healthy_retrieval_is_not_misclassified_as_threshold_filtering():
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={},
        candidates={},
        ranked_count=0,
        ranked_collections=set(),
        final_collections=set(),
        events=[],
    )
    assert outcome == "no_candidates"
    assert collections == {"bible": "no_candidates"}


def test_empty_degraded_retrieval_is_a_failure():
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={},
        candidates={},
        ranked_count=0,
        ranked_collections=set(),
        final_collections=set(),
        events=[{
            "stage": "retrieve_vector",
            "scope": "bible/query",
            "reason": "TimeoutError",
            "action": "path_omitted",
        }],
    )
    assert outcome == "retrieval_failed"
    assert collections == {"bible": "retrieval_failed"}


def test_candidates_lost_during_enrichment_are_corpus_sync_failure():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={"bible": [candidate]},
        candidates={"bible": []},
        ranked_count=0,
        ranked_collections=set(),
        final_collections=set(),
        events=[{
            "stage": "fetch_positions",
            "scope": None,
            "reason": "orphaned_candidates",
            "action": "candidates_omitted",
        }],
    )
    assert outcome == "corpus_sync_failed"
    assert collections == {"bible": "corpus_sync_failed"}


def test_candidates_without_ranked_output_are_ranking_failure():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={"bible": [candidate]},
        candidates={"bible": [candidate]},
        ranked_count=0,
        ranked_collections=set(),
        final_collections=set(),
        events=[],
    )
    assert outcome == "ranking_failed"
    assert collections == {"bible": "ranking_failed"}


def test_unranked_collection_in_partial_success_is_not_called_below_threshold():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible", "summa"],
        pre_enrichment={"bible": [candidate], "summa": [candidate]},
        candidates={"bible": [candidate], "summa": [candidate]},
        ranked_count=1,
        ranked_collections={"bible"},
        final_collections={"bible"},
        events=[],
    )
    assert outcome == "degraded_success"
    assert collections == {"bible": "results", "summa": "ranking_failed"}


def test_successful_ranking_fallback_is_visible_but_not_called_failure():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={"bible": [candidate]},
        candidates={"bible": [candidate]},
        ranked_count=1,
        ranked_collections={"bible"},
        final_collections={"bible"},
        events=[{
            "stage": "rerank_cohere",
            "scope": "bible",
            "reason": "TimeoutError",
            "action": "rrf_fallback_used",
        }],
    )
    assert outcome == "degraded_success"
    assert collections == {"bible": "results_degraded"}


def test_cost_accounting_event_does_not_degrade_success():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={"bible": [candidate]},
        candidates={"bible": [candidate]},
        ranked_count=1,
        ranked_collections={"bible"},
        final_collections={"bible"},
        events=[{
            "stage": "rerank_cohere",
            "scope": "bible",
            "reason": "billing_metadata_missing",
            "action": "cost_estimated",
        }],
    )
    assert outcome == "success"
    assert collections == {"bible": "results"}


def test_global_terminal_fallback_marks_all_returned_collections_degraded():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible", "summa"],
        pre_enrichment={"bible": [candidate], "summa": [candidate]},
        candidates={"bible": [candidate], "summa": [candidate]},
        ranked_count=2,
        ranked_collections={"bible", "summa"},
        final_collections={"bible", "summa"},
        events=[{
            "stage": "rerank_listwise_luna",
            "scope": None,
            "reason": "incomplete_output",
            "action": "upstream_order_used",
        }],
    )
    assert outcome == "degraded_success"
    assert collections == {
        "bible": "results_degraded",
        "summa": "results_degraded",
    }


def test_partial_retrieval_path_failure_marks_returned_results_degraded():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={"bible": [candidate]},
        candidates={"bible": [candidate]},
        ranked_count=1,
        ranked_collections={"bible"},
        final_collections={"bible"},
        events=[{
            "stage": "retrieve_vector",
            "scope": "bible/query",
            "reason": "TimeoutError",
            "action": "path_omitted",
        }],
    )
    assert outcome == "degraded_success"
    assert collections == {"bible": "results_degraded"}


def test_skipped_position_enrichment_marks_results_degraded():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible"],
        pre_enrichment={"bible": [candidate]},
        candidates={"bible": [candidate]},
        ranked_count=1,
        ranked_collections={"bible"},
        final_collections={"bible"},
        events=[{
            "stage": "fetch_positions",
            "scope": "bible",
            "reason": "pool_unavailable",
            "action": "enrichment_skipped",
        }],
    )
    assert outcome == "degraded_success"
    assert collections == {"bible": "results_degraded"}


def test_collection_scoped_hyde_failure_marks_results_degraded():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible", "summa"],
        pre_enrichment={"bible": [candidate], "summa": [candidate]},
        candidates={"bible": [candidate], "summa": [candidate]},
        ranked_count=2,
        ranked_collections={"bible", "summa"},
        final_collections={"bible", "summa"},
        events=[{
            "stage": "hyde_embed",
            "scope": "summa",
            "reason": "TimeoutError",
            "action": "vector_omitted",
        }],
    )
    assert outcome == "degraded_success"
    assert collections == {
        "bible": "results",
        "summa": "results_degraded",
    }


def test_global_hyde_failure_marks_all_results_degraded_for_legacy_events():
    candidate = MagicMock()
    outcome, collections = runner._classify_outcomes(
        collections=["bible", "summa"],
        pre_enrichment={"bible": [candidate], "summa": [candidate]},
        candidates={"bible": [candidate], "summa": [candidate]},
        ranked_count=2,
        ranked_collections={"bible", "summa"},
        final_collections={"bible", "summa"},
        events=[{
            "stage": "hyde",
            "scope": None,
            "reason": "RuntimeError",
            "action": "collection_omitted",
        }],
    )
    assert outcome == "degraded_success"
    assert collections == {
        "bible": "results_degraded",
        "summa": "results_degraded",
    }


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
