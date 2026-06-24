"""Tests for the Qdrant-backed retrieve module."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.retrieve import (
    ChunkCandidate,
    _get_excluded_ids,
    _rrf_merge,
    _search_vector,
    retrieve_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(chunk_id: str, collection: str = "bible", score: float = 0.9) -> dict:
    return {
        "id": chunk_id,
        "content": f"Content of {chunk_id}",
        "reference": f"Ref {chunk_id}",
        "collection": collection,
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "Test Doc",
        "author": None,
        "score": score,
    }


def _scored_point(chunk_id: str, collection: str = "bible", score: float = 0.9):
    """Build a mock ScoredPoint matching the qdrant_client return shape."""
    pt = MagicMock()
    pt.id = chunk_id
    pt.score = score
    pt.payload = {
        "collection": collection,
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "Test Doc",
        "author": None,
        "content": f"Content of {chunk_id}",
        "reference": f"Ref {chunk_id}",
    }
    return pt


# ---------------------------------------------------------------------------
# _rrf_merge
# ---------------------------------------------------------------------------

def test_rrf_merge_basic():
    """Top chunk from each list should appear in merged results."""
    list_a = [_row("aaa"), _row("bbb")]
    list_b = [_row("bbb"), _row("ccc")]
    merged = _rrf_merge([list_a, list_b], top_n=3)
    ids = [m["chunk_id"] for m in merged]
    assert "bbb" in ids  # ranked in both lists → highest RRF
    assert "aaa" in ids
    assert "ccc" in ids


def test_rrf_merge_deduplicates():
    """A chunk appearing in multiple lists must only appear once in the output."""
    shared = _row("shared-id")
    merged = _rrf_merge([[shared], [shared]], top_n=5)
    assert sum(1 for m in merged if m["chunk_id"] == "shared-id") == 1


def test_rrf_merge_per_strategy_guarantee():
    """Top-K from each list must be included even if their aggregate RRF is low."""
    # list_a has 'rare' at rank 1 but list_b has many higher-scoring chunks
    list_a = [_row("rare")] + [_row(f"b{i}") for i in range(20)]
    list_b = [_row(f"b{i}") for i in range(20)]
    merged = _rrf_merge([list_a, list_b], top_n=5)
    ids = {m["chunk_id"] for m in merged}
    assert "rare" in ids  # per-strategy guarantee must include rank-1 of list_a


def test_rrf_merge_score_order():
    """Merged results must be sorted by RRF score descending."""
    # 'top' appears first in both lists → highest RRF score
    list_a = [_row("top"), _row("mid"), _row("low")]
    list_b = [_row("top"), _row("other")]
    merged = _rrf_merge([list_a, list_b], top_n=10)
    assert merged[0]["chunk_id"] == "top"


def test_rrf_merge_empty_lists():
    """Empty result lists should be handled gracefully."""
    merged = _rrf_merge([[], [_row("aaa")]], top_n=5)
    assert len(merged) == 1
    assert merged[0]["chunk_id"] == "aaa"


def test_rrf_merge_all_empty():
    merged = _rrf_merge([[], []], top_n=5)
    assert merged == []


# ---------------------------------------------------------------------------
# _search_vector (mocked Qdrant)
# ---------------------------------------------------------------------------

def _mock_query_response(points):
    """Wrap a list of scored points in a QueryResponse-shaped mock."""
    resp = MagicMock()
    resp.points = points
    return resp


@pytest.mark.asyncio
async def test_search_vector_applies_collection_filter():
    """Qdrant search must use a collection filter and return dicts with correct keys."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([
        _scored_point("aaaaaaaa-0000-0000-0000-000000000001", "bible"),
    ]))

    with patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client):
        rows = await _search_vector("bible", [0.1] * 1536, limit=5, label="query", excluded_ids=[])

    assert len(rows) == 1
    assert rows[0]["id"] == "aaaaaaaa-0000-0000-0000-000000000001"
    assert rows[0]["collection"] == "bible"
    assert "content" in rows[0]

    call_kwargs = mock_client.query_points.call_args.kwargs
    filt = call_kwargs["query_filter"]
    assert any(
        hasattr(cond, "key") and cond.key == "collection"
        for cond in filt.must
    )


@pytest.mark.asyncio
async def test_search_vector_excludes_downvoted_ids():
    """Downvoted IDs must be passed to Qdrant as must_not HasIdCondition."""
    from qdrant_client.models import HasIdCondition

    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([]))

    excluded = ["bbbbbbbb-0000-0000-0000-000000000001"]
    with patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client):
        await _search_vector("bible", [0.1] * 1536, limit=5, label="hyde", excluded_ids=excluded)

    call_kwargs = mock_client.query_points.call_args.kwargs
    filt = call_kwargs["query_filter"]
    assert filt.must_not is not None
    assert any(isinstance(c, HasIdCondition) for c in filt.must_not)


@pytest.mark.asyncio
async def test_search_vector_no_must_not_when_no_exclusions():
    """When excluded_ids is empty, must_not must be None (not an empty list)."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([]))

    with patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client):
        await _search_vector("bible", [0.1] * 1536, limit=5, label="query", excluded_ids=[])

    filt = mock_client.query_points.call_args.kwargs["query_filter"]
    assert filt.must_not is None


@pytest.mark.asyncio
async def test_search_vector_raises_when_client_not_initialised():
    with patch("app.rag.retrieve.get_qdrant_client", return_value=None):
        with pytest.raises(RuntimeError, match="Qdrant client not initialised"):
            await _search_vector("bible", [0.1] * 1536, limit=5, label="query", excluded_ids=[])


# ---------------------------------------------------------------------------
# retrieve_candidates integration
# ---------------------------------------------------------------------------

def _make_pool_mock(excluded_ids: list[str] | None = None):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[
        {"chunk_id": cid} for cid in (excluded_ids or [])
    ])
    return pool


@pytest.mark.asyncio
async def test_retrieve_candidates_returns_chunk_candidates():
    """retrieve_candidates should return a list of ChunkCandidate on success."""
    chunk_id = "cccccccc-0000-0000-0000-000000000001"
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([_scored_point(chunk_id)]))

    mock_pool = _make_pool_mock()
    # FTS returns empty — only vector results matter here
    mock_pool.fetch = AsyncMock(side_effect=[
        [],           # _get_excluded_ids
        [],           # _search_fts
    ])

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        results = await retrieve_candidates(
            query_text="test query",
            query_vec=[0.1] * 1536,
            hyde_vec=[0.2] * 1536,
            extra_vecs=[],
            collection="bible",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert len(results) > 0
    assert all(isinstance(r, ChunkCandidate) for r in results)
    assert results[0].chunk_id == chunk_id


@pytest.mark.asyncio
async def test_retrieve_candidates_graceful_on_qdrant_failure():
    """If all Qdrant searches fail but FTS works, should still return results."""
    chunk_id = "dddddddd-0000-0000-0000-000000000001"
    fts_row = {
        "id": chunk_id,
        "content": "FTS result",
        "reference": "Test 1:1",
        "collection": "catechism",
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "CCC",
        "author": None,
    }

    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(side_effect=RuntimeError("Qdrant down"))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=[
        [],           # _get_excluded_ids
        [fts_row],    # _search_fts
    ])

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        results = await retrieve_candidates(
            query_text="test",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="catechism",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert len(results) == 1
    assert results[0].chunk_id == chunk_id


@pytest.mark.asyncio
async def test_retrieve_candidates_returns_empty_on_all_failures():
    """If every search strategy fails, returns empty list without raising."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(side_effect=RuntimeError("Qdrant down"))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=Exception("DB down"))

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        results = await retrieve_candidates(
            query_text="test",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="bible",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert results == []


# ---------------------------------------------------------------------------
# Migration script unit tests
# ---------------------------------------------------------------------------

def test_parse_pgvector():
    """parse_pgvector must convert pgvector text format to a float list."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from scripts.migrate_to_qdrant import parse_pgvector

    result = parse_pgvector("[0.1,-0.2,0.3]")
    assert result == pytest.approx([0.1, -0.2, 0.3])


def test_build_point():
    """build_point must produce a PointStruct with correct id, vector, and payload."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from scripts.migrate_to_qdrant import build_point, parse_pgvector
    from qdrant_client.models import PointStruct

    vec = [0.0] * 1536
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "chunk_id": "eeeeeeee-0000-0000-0000-000000000001",
        "content": "Test content",
        "reference": "Gen 1:1",
        "embedding": "[" + ",".join("0.0" for _ in range(1536)) + "]",
        "document_id": "ffffffff-0000-0000-0000-000000000001",
        "document_title": "Genesis",
        "author": "Moses",
        "collection": "bible",
    }[k]

    point = build_point(row)
    assert isinstance(point, PointStruct)
    assert point.id == "eeeeeeee-0000-0000-0000-000000000001"
    assert len(point.vector) == 1536
    assert point.payload["collection"] == "bible"
    assert point.payload["content"] == "Test content"


# ---------------------------------------------------------------------------
# expansion_queries parameter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_candidates_calls_fts_for_each_expansion():
    """FTS is called once per expansion query plus once for the original query."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([]))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[])  # _get_excluded_ids

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
        patch("app.rag.retrieve._search_fts", new_callable=AsyncMock) as mock_fts,
    ):
        mock_settings.candidate_multiplier = 3
        mock_fts.return_value = []

        await retrieve_candidates(
            query_text="Holy Spirit",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="catechism",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
            expansion_queries=["Holy Ghost", "divine grace"],
        )

    # original + 2 expansion = 3 FTS calls
    assert mock_fts.call_count == 3
    fts_texts = {call.args[3] for call in mock_fts.call_args_list}
    assert fts_texts == {"Holy Spirit", "Holy Ghost", "divine grace"}


@pytest.mark.asyncio
async def test_retrieve_candidates_no_expansion_by_default():
    """Without expansion_queries, only the original FTS call is made."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([]))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[])

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
        patch("app.rag.retrieve._search_fts", new_callable=AsyncMock) as mock_fts,
    ):
        mock_settings.candidate_multiplier = 3
        mock_fts.return_value = []

        await retrieve_candidates(
            query_text="grace",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="catechism",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert mock_fts.call_count == 1
    assert mock_fts.call_args.args[3] == "grace"
