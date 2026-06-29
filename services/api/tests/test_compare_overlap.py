import pytest
from app.rag.compare.overlap import run as compute_overlap
from app.rag.steps.types import RankedChunk, PipelineResult, StepTiming


def _make_chunk(chunk_id: str, collection: str = "bible", score: float = 0.9) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id, content="x", reference=None, collection=collection,
        document_id="d1", document_title="T", author=None, reranker_score=score,
    )


def _make_result(pipeline: str, chunk_ids: list[str]) -> PipelineResult:
    return PipelineResult(
        pipeline=pipeline,
        chunks=[_make_chunk(cid) for cid in chunk_ids],
        step_timings=[StepTiming("embed", 0.1)],
        total_duration_s=1.0,
        cost_breakdown={},
        total_cost=0.0,
    )


def test_shared_chunks_identified():
    shared_id = "00000000-0000-0000-0000-000000000001"
    r1 = _make_result("s2_5_haiku", [shared_id, "00000000-0000-0000-0000-000000000002"])
    r2 = _make_result("s4_haiku",   [shared_id, "00000000-0000-0000-0000-000000000003"])
    report = compute_overlap([r1, r2])
    assert shared_id in report.shared


def test_unique_chunks_attributed():
    r1 = _make_result("s2_5_haiku", ["00000000-0000-0000-0000-000000000001"])
    r2 = _make_result("s4_haiku",   ["00000000-0000-0000-0000-000000000002"])
    report = compute_overlap([r1, r2])
    assert "00000000-0000-0000-0000-000000000001" in report.unique
    assert "s2_5_haiku" in report.unique["00000000-0000-0000-0000-000000000001"]


def test_rank_divergence_for_shared_chunks():
    shared_id = "00000000-0000-0000-0000-000000000001"
    r1 = _make_result("s2_5_haiku", [shared_id])
    r2 = _make_result("s4_haiku",   [shared_id])
    report = compute_overlap([r1, r2])
    assert shared_id in report.rank_divergence
    assert "s2_5_haiku" in report.rank_divergence[shared_id]
    assert "s4_haiku" in report.rank_divergence[shared_id]


def test_empty_results_returns_empty_report():
    report = compute_overlap([])
    assert report.shared == []
    assert report.partial == {}
    assert report.unique == {}
    assert report.rank_divergence == {}
    assert report.score_delta == {}


def test_partial_overlap():
    """Chunk in 2 of 3 pipelines goes to partial, not shared or unique."""
    shared_id = "00000000-0000-0000-0000-000000000001"
    only_id = "00000000-0000-0000-0000-000000000002"
    r1 = _make_result("s2_5_haiku", [shared_id, only_id])
    r2 = _make_result("s4_haiku",   [shared_id])
    r3 = _make_result("s2_5_cohere", ["00000000-0000-0000-0000-000000000003"])
    report = compute_overlap([r1, r2, r3])
    # shared_id appears in 2 of 3 → partial
    assert shared_id in report.partial
    assert shared_id not in report.shared
    # only_id appears in 1 of 3 → unique
    assert only_id in report.unique


def test_score_delta_computed_for_shared():
    shared_id = "00000000-0000-0000-0000-000000000001"
    r1 = _make_result("s2_5_haiku", [shared_id])
    r1.chunks[0].reranker_score = 0.8
    r2 = _make_result("s4_haiku",   [shared_id])
    r2.chunks[0].reranker_score = 0.6
    report = compute_overlap([r1, r2])
    assert shared_id in report.score_delta
    assert abs(report.score_delta[shared_id]["delta"] - 0.2) < 1e-6
