"""Tests for position+cosine dedup and per-title cap."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.dedup import _cosine_sim, apply_dedup
from app.rag.steps.types import RankedChunk


def _chunk(chunk_id: str, doc_id: str, doc_title: str, score: float, position: int | None = None) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id,
        content="content",
        reference="Ref 1:1",
        collection="catechism",
        document_id=doc_id,
        document_title=doc_title,
        author=None,
        reranker_score=score,
        include=True,
        position=position,
    )


# ---------------------------------------------------------------------------
# _cosine_sim
# ---------------------------------------------------------------------------

def test_cosine_sim_identical_vectors_returns_one():
    v = [1.0, 0.0, 0.0]
    assert _cosine_sim(v, v) == pytest.approx(1.0)


def test_cosine_sim_orthogonal_vectors_returns_zero():
    assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_sim_zero_vector_returns_zero():
    assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_sim_opposite_vectors_returns_minus_one():
    assert _cosine_sim([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# apply_dedup — cosine dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dedup_drops_lower_scorer_when_close_and_cosine_high():
    """Position ≤2 apart AND cosine > 0.9 → lower scorer dropped."""
    a = _chunk("aaaa-0000-0000-0000-000000000001", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000002", "doc1", "CCC", 0.7, position=2)

    vec = [1.0] + [0.0] * 1535  # cosine(v, v) = 1.0 > 0.9

    mock_pt_a = MagicMock(); mock_pt_a.id = "aaaa-0000-0000-0000-000000000001"; mock_pt_a.vector = vec
    mock_pt_b = MagicMock(); mock_pt_b.id = "bbbb-0000-0000-0000-000000000002"; mock_pt_b.vector = vec
    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[mock_pt_a, mock_pt_b])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000001" in ids
    assert "bbbb-0000-0000-0000-000000000002" not in ids


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_cosine_below_threshold():
    """Same document, close positions, but cosine < 0.9 → keep both."""
    a = _chunk("aaaa-0000-0000-0000-000000000003", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000004", "doc1", "CCC", 0.7, position=2)

    vec_a = [1.0] + [0.0] * 1535
    vec_b = [0.0, 1.0] + [0.0] * 1534  # cosine(a, b) = 0.0

    mock_pt_a = MagicMock(); mock_pt_a.id = "aaaa-0000-0000-0000-000000000003"; mock_pt_a.vector = vec_a
    mock_pt_b = MagicMock(); mock_pt_b.id = "bbbb-0000-0000-0000-000000000004"; mock_pt_b.vector = vec_b
    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[mock_pt_a, mock_pt_b])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000003" in ids
    assert "bbbb-0000-0000-0000-000000000004" in ids


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_positions_far_apart():
    """Positions > 2 apart → skip cosine check entirely, keep both."""
    a = _chunk("aaaa-0000-0000-0000-000000000005", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000006", "doc1", "CCC", 0.7, position=10)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000005" in ids
    assert "bbbb-0000-0000-0000-000000000006" in ids
    # Qdrant should not be called when no close pairs exist
    mock_client.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_position_is_none():
    """When position is missing, cannot check proximity — keep both chunks."""
    a = _chunk("aaaa-0000-0000-0000-000000000007", "doc1", "CCC", 0.9, position=None)
    b = _chunk("bbbb-0000-0000-0000-000000000008", "doc1", "CCC", 0.7, position=None)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    assert len(result) == 2


# ---------------------------------------------------------------------------
# apply_dedup — per-title cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_title_cap_drops_third_chunk():
    """Max 2 results per document_title — third is dropped regardless of score."""
    # Three chunks with same title but different document_ids (different translations)
    a = _chunk("aaaa-0000-0000-0000-000000000009", "doc_a", "Summa Theologica", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000010", "doc_b", "Summa Theologica", 0.8, position=50)
    c = _chunk("cccc-0000-0000-0000-000000000011", "doc_c", "Summa Theologica", 0.7, position=100)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b, c])

    assert len(result) == 2
    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000009" in ids
    assert "bbbb-0000-0000-0000-000000000010" in ids
    assert "cccc-0000-0000-0000-000000000011" not in ids


@pytest.mark.asyncio
async def test_per_title_cap_allows_two_different_titles():
    """Different document titles are each allowed up to 2 results."""
    a = _chunk("aaaa-0000-0000-0000-000000000012", "doc1", "Summa", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000013", "doc1", "Summa", 0.8, position=50)
    c = _chunk("cccc-0000-0000-0000-000000000014", "doc2", "Catechism", 0.7, position=1)
    d = _chunk("dddd-0000-0000-0000-000000000015", "doc2", "Catechism", 0.6, position=50)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b, c, d])

    assert len(result) == 4


@pytest.mark.asyncio
async def test_dedup_graceful_on_qdrant_failure():
    """If Qdrant retrieve fails, dedup is skipped but per-title cap still applies."""
    a = _chunk("aaaa-0000-0000-0000-000000000016", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000017", "doc1", "CCC", 0.7, position=2)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(side_effect=RuntimeError("Qdrant down"))

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    # Both survive (cosine dedup skipped), per-title cap allows 2
    assert len(result) == 2
