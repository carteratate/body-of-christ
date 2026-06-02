"""Tests for per-item score error handling in rerank_collection."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.rerank import rerank_collection
from app.rag.retrieve import ChunkCandidate


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
async def test_rerank_null_score_defaults_to_zero_not_dropped():
    """A null score from the LLM should default to 0.0; the chunk must still appear in results."""
    chunk_id = "00000000-0000-0000-0000-000000000001"
    candidate = _make_candidate(chunk_id)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{chunk_id}", "score": null}}]')
    ]

    with patch("app.rag.rerank._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([candidate], "grace", quota=3)

    assert len(result) == 1
    assert result[0].chunk_id == chunk_id
    assert result[0].reranker_score == 0.0


@pytest.mark.asyncio
async def test_rerank_string_score_defaults_to_zero_not_dropped():
    """A non-numeric string score like 'high' should default to 0.0; the chunk must still appear."""
    chunk_id = "00000000-0000-0000-0000-000000000002"
    candidate = _make_candidate(chunk_id)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{chunk_id}", "score": "high"}}]')
    ]

    with patch("app.rag.rerank._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([candidate], "grace", quota=3)

    assert len(result) == 1
    assert result[0].chunk_id == chunk_id
    assert result[0].reranker_score == 0.0


@pytest.mark.asyncio
async def test_rerank_bad_score_does_not_affect_other_chunks():
    """A bad score for one chunk must not drop the other chunks in the same batch."""
    bad_id = "00000000-0000-0000-0000-000000000003"
    good_id = "00000000-0000-0000-0000-000000000004"
    candidates = [_make_candidate(bad_id), _make_candidate(good_id)]
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=f'[{{"chunk_id": "{bad_id}", "score": null}}, {{"chunk_id": "{good_id}", "score": 0.9}}]'
        )
    ]

    with patch("app.rag.rerank._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection(candidates, "grace", quota=3)

    result_ids = {r.chunk_id for r in result}
    assert bad_id in result_ids
    assert good_id in result_ids

    good_chunk = next(r for r in result if r.chunk_id == good_id)
    assert good_chunk.reranker_score == pytest.approx(0.9)
