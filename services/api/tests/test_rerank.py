"""Tests for per-item score error handling in _rerank_single_collection."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings
from app.rag.steps.rerank_haiku import _rerank_single_collection as rerank_collection
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import ChunkCandidate


def _make_candidate(chunk_id: str) -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=chunk_id,
        content="Sample content about grace",
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
    )


@pytest.mark.asyncio
async def test_rerank_null_score_rejects_response_and_uses_fallback():
    chunk_id = "00000000-0000-0000-0000-000000000001"
    candidate = _make_candidate(chunk_id)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{chunk_id}", "score": null}}]')
    ]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("app.rag.steps.rerank_haiku._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([candidate], "grace", 3, CostTracker())

    assert len(result) == 1
    assert result[0].chunk_id == chunk_id
    assert result[0].reranker_score == settings.llm_fallback_score_base
    assert result[0].score_source == "rrf_fallback"


@pytest.mark.asyncio
async def test_rerank_string_score_rejects_response_and_uses_fallback():
    chunk_id = "00000000-0000-0000-0000-000000000002"
    candidate = _make_candidate(chunk_id)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{chunk_id}", "score": "high"}}]')
    ]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("app.rag.steps.rerank_haiku._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([candidate], "grace", 3, CostTracker())

    assert len(result) == 1
    assert result[0].chunk_id == chunk_id
    assert result[0].reranker_score == settings.llm_fallback_score_base
    assert result[0].score_source == "rrf_fallback"


@pytest.mark.asyncio
async def test_rerank_bad_score_rejects_entire_partial_response():
    bad_id = "00000000-0000-0000-0000-000000000003"
    good_id = "00000000-0000-0000-0000-000000000004"
    candidates = [_make_candidate(bad_id), _make_candidate(good_id)]
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=f'[{{"chunk_id": "{bad_id}", "score": null}}, {{"chunk_id": "{good_id}", "score": 0.9}}]'
        )
    ]
    mock_response.usage = MagicMock(input_tokens=200, output_tokens=80)

    with patch("app.rag.steps.rerank_haiku._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection(candidates, "grace", 3, CostTracker())

    result_ids = {r.chunk_id for r in result}
    assert bad_id in result_ids
    assert good_id in result_ids

    assert all(r.score_source == "rrf_fallback" for r in result)


@pytest.mark.asyncio
async def test_rerank_propagates_position_for_dedup():
    """RankedChunk must carry ChunkCandidate.position (scored AND omitted paths)
    so the downstream cosine dedup can compute passage proximity."""
    scored_id = "00000000-0000-0000-0000-000000000030"
    omitted_id = "00000000-0000-0000-0000-000000000031"
    c_scored = _make_candidate(scored_id)
    c_scored.position = 10
    c_omitted = _make_candidate(omitted_id)
    c_omitted.position = 20

    mock_response = MagicMock()
    # Model returns only the scored chunk; the other falls through the omitted path.
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{scored_id}", "score": 0.8, "include": true}}]')
    ]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("app.rag.steps.rerank_haiku._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([c_scored, c_omitted], "grace", 3, CostTracker())

    positions = {r.chunk_id: r.position for r in result}
    assert positions[scored_id] == 10
    assert positions[omitted_id] == 20


@pytest.mark.asyncio
async def test_rerank_fallback_propagates_position():
    """The RRF fallback (client unavailable) must also carry position."""
    chunk_id = "00000000-0000-0000-0000-000000000032"
    candidate = _make_candidate(chunk_id)
    candidate.position = 7

    with patch("app.rag.steps.rerank_haiku._client", None):
        result = await rerank_collection([candidate], "grace", 3, CostTracker())

    assert result[0].position == 7


def test_format_passages_includes_full_content():
    """Reranker must see the full chunk, not just the first 600 chars."""
    from app.rag.steps.rerank_haiku import _format_passages
    c = ChunkCandidate(
        chunk_id="00000000-0000-0000-0000-000000000020",
        content="A" * 1000,
        reference="Test Ref",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Test",
        author=None,
        rrf_score=0.5,
    )
    result = _format_passages([c])
    assert "A" * 1000 in result


def test_ranked_chunk_has_position_field():
    """RankedChunk must carry a position field for downstream dedup."""
    from app.rag.steps.types import RankedChunk
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000010",
        content="test",
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        reranker_score=0.8,
        position=5,
    )
    assert chunk.position == 5


def test_ranked_chunk_position_defaults_to_none():
    """position must default to None so existing callers don't need to change."""
    from app.rag.steps.types import RankedChunk
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000011",
        content="test",
        reference=None,
        collection="catechism",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="CCC",
        author=None,
        reranker_score=0.5,
    )
    assert chunk.position is None
