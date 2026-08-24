"""Tests for the retrieve steps (retrieve_vector, retrieve_fts, rrf, fetch_positions)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from app.rag.steps.types import ChunkCandidate
from app.rag.steps.rrf import _rrf_merge, run as rrf_run
from app.rag.steps.retrieve_vector import _search_vector, run as retrieve_vector
from app.rag.steps.retrieve_fts import run as retrieve_fts
from app.rag.steps.fetch_positions import run as fetch_positions


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
    """Qdrant search must use a collection filter, return correct keys, and have no must_not."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([
        _scored_point("aaaaaaaa-0000-0000-0000-000000000001", "bible"),
    ]))

    with patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=mock_client):
        rows = await _search_vector("bible", [0.1] * 1536, limit=5, label="query")

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
    assert filt.must_not is None


@pytest.mark.asyncio
async def test_search_vector_raises_when_client_not_initialised():
    with patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=None):
        with pytest.raises(RuntimeError, match="Qdrant client not initialised"):
            await _search_vector("bible", [0.1] * 1536, limit=5, label="query")


@pytest.mark.asyncio
async def test_search_vector_skips_malformed_point_keeps_good_ones():
    """A point with an incomplete payload must be dropped individually, not take
    down the whole strategy's result list."""
    good = _scored_point("aaaaaaaa-0000-0000-0000-000000000001", "bible")
    malformed = MagicMock()
    malformed.id = "bbbbbbbb-0000-0000-0000-000000000002"
    malformed.score = 0.8
    malformed.payload = {"collection": "bible"}  # missing content/document_id/document_title

    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([good, malformed]))

    with patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=mock_client):
        rows = await _search_vector("bible", [0.1] * 1536, limit=5, label="query")

    ids = [r["id"] for r in rows]
    assert "aaaaaaaa-0000-0000-0000-000000000001" in ids
    assert "bbbbbbbb-0000-0000-0000-000000000002" not in ids


@pytest.mark.asyncio
async def test_search_vector_handles_none_payload():
    """A point with no payload at all must be skipped, not raise."""
    pt = MagicMock()
    pt.id = "cccccccc-0000-0000-0000-000000000003"
    pt.score = 0.7
    pt.payload = None

    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([pt]))

    with patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=mock_client):
        rows = await _search_vector("bible", [0.1] * 1536, limit=5, label="query")

    assert rows == []


# ---------------------------------------------------------------------------
# Step integration: retrieve_vector + rrf_merge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_vector_run_returns_chunk_candidates():
    """retrieve_vector.run + rrf_merge should produce ChunkCandidates on success."""
    chunk_id = "cccccccc-0000-0000-0000-000000000001"
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([_scored_point(chunk_id)]))

    with (
        patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=mock_client),
        patch("app.rag.steps.retrieve_vector.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        vec_raw = await retrieve_vector(
            query_vec=[0.1] * 1536,
            hyde_vecs={},
            collections=["bible"],
            quota=4,
        )

    merged = rrf_run(vec_raw, {}, quota=4)
    assert "bible" in merged
    results = merged["bible"]
    assert len(results) > 0
    assert all(isinstance(r, ChunkCandidate) for r in results)
    assert results[0].chunk_id == chunk_id


@pytest.mark.asyncio
async def test_retrieve_fts_run_returns_results_without_vector():
    """retrieve_fts.run should return results even when vector search is absent."""
    chunk_id = "dddddddd-0000-0000-0000-000000000001"
    fts_row = {
        "id": chunk_id,
        "content": "FTS result",
        "reference": "Test 1:1",
        "collection": "catechism",
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "CCC",
        "author": None,
        "anchor": None,
        "position": 5,
        "annotation": None,
    }

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[fts_row])

    with (
        patch("app.rag.steps.retrieve_fts.get_pool", return_value=mock_pool),
        patch("app.rag.steps.retrieve_fts.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        fts_raw = await retrieve_fts("test", ["catechism"], 4, "00000000-0000-0000-0000-000000000001")

    merged = rrf_run({}, fts_raw, quota=4)
    assert "catechism" in merged
    assert merged["catechism"][0].chunk_id == chunk_id


@pytest.mark.asyncio
async def test_retrieve_fts_reacquires_after_transient_connection_loss():
    """A stale Supabase-pooler socket is retried once and never recorded degraded."""
    fts_row = _row("dddddddd-0000-0000-0000-000000000002", "catechism")
    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=[
        asyncpg.ConnectionDoesNotExistError("connection was closed"),
        [fts_row],
    ])

    with (
        patch("app.rag.steps.retrieve_fts.get_pool", return_value=mock_pool),
        patch("app.rag.steps.retrieve_fts.asyncio.sleep", new=AsyncMock()),
        patch("app.rag.steps.retrieve_fts.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        rows = await retrieve_fts("test", ["catechism"], 4)

    assert rows["catechism"][0]["id"] == fts_row["id"]
    assert mock_pool.fetch.await_count == 2


@pytest.mark.asyncio
async def test_retrieve_fts_does_not_retry_non_connection_error():
    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=asyncpg.PostgresSyntaxError("bad SQL"))

    with (
        patch("app.rag.steps.retrieve_fts.get_pool", return_value=mock_pool),
        patch("app.rag.steps.retrieve_fts.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        rows = await retrieve_fts("test", ["catechism"], 4)

    assert rows == {}
    assert mock_pool.fetch.await_count == 1


def test_rrf_run_empty_on_empty_inputs():
    """rrf.run with both inputs empty returns empty dict."""
    merged = rrf_run({}, {}, quota=4)
    assert merged == {}


# ---------------------------------------------------------------------------
# position / annotation plumbing
# ---------------------------------------------------------------------------

def test_chunk_candidate_has_position_field():
    """ChunkCandidate must carry position for dedup."""
    c = ChunkCandidate(
        chunk_id="aaaa0000-0000-0000-0000-000000000001",
        content="test",
        reference=None,
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
        position=7,
    )
    assert c.position == 7


def test_chunk_candidate_position_defaults_to_none():
    c = ChunkCandidate(
        chunk_id="aaaa0000-0000-0000-0000-000000000002",
        content="test",
        reference=None,
        collection="catechism",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="CCC",
        author=None,
        rrf_score=0.5,
    )
    assert c.position is None


@pytest.mark.asyncio
async def test_retrieve_fts_run_propagates_position():
    """FTS results include position; it must reach ChunkCandidate.position."""
    chunk_id = "fts00000-0000-0000-0000-000000000001"
    fts_row = {
        "id": chunk_id,
        "content": "FTS result",
        "reference": "Test 1:1",
        "collection": "catechism",
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "CCC",
        "author": None,
        "anchor": None,
        "position": 42,
        "annotation": None,
    }

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[fts_row])

    with (
        patch("app.rag.steps.retrieve_fts.get_pool", return_value=mock_pool),
        patch("app.rag.steps.retrieve_fts.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        fts_raw = await retrieve_fts("grace", ["catechism"], 4, "00000000-0000-0000-0000-000000000001")

    merged = rrf_run({}, fts_raw, quota=4)
    assert "catechism" in merged
    assert merged["catechism"][0].position == 42


def _mock_pool_returning(rows):
    """Build a pool mock whose acquire() -> conn.fetch(...) yields `rows`."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool


def _candidate(chunk_id: str) -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=chunk_id,
        content="Vector result",
        reference=None,
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
        position=None,
    )


@pytest.mark.asyncio
async def test_fetch_positions_run_fills_missing_positions():
    """fetch_positions.run must batch-fetch positions for Qdrant-sourced candidates."""
    chunk_id = "00000000-0000-0000-0000-000000000001"
    candidate = _candidate(chunk_id)
    mock_pool = _mock_pool_returning([{"id": chunk_id, "position": 17}])

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=mock_pool):
        result = await fetch_positions({"bible": [candidate]})

    assert result["bible"][0].position == 17


@pytest.mark.asyncio
async def test_fetch_positions_drops_orphaned_candidates():
    """A position=None candidate absent from the chunks table (orphaned Qdrant
    vector) must be dropped so it cannot crash retrievals persistence."""
    present_id = "00000000-0000-0000-0000-000000000001"
    orphan_id = "7e430ae4-ac20-5a8d-a587-b17bfdde8761"
    present = _candidate(present_id)
    orphan = _candidate(orphan_id)
    # DB only knows about the present id; orphan_id is not returned.
    mock_pool = _mock_pool_returning([{"id": present_id, "position": 9}])

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=mock_pool):
        result = await fetch_positions({"bible": [present, orphan]})

    kept_ids = {c.chunk_id for c in result["bible"]}
    assert present_id in kept_ids
    assert orphan_id not in kept_ids
    assert result["bible"][0].position == 9


@pytest.mark.asyncio
async def test_fetch_positions_populates_annotation_from_the_chunks_table():
    """Qdrant payloads carry no annotation, so the batch position lookup is where an
    enriched candidate picks one up. Guards the SELECT actually including the column."""
    chunk_id = "00000000-0000-0000-0000-000000000001"
    annotation = "SUMMARY: x\n[doctrinal | explicit]: y"
    candidate = _candidate(chunk_id)
    mock_pool = _mock_pool_returning(
        [{"id": chunk_id, "position": 3, "annotation": annotation}]
    )

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=mock_pool):
        result = await fetch_positions({"bible": [candidate]})

    assert result["bible"][0].annotation == annotation


@pytest.mark.asyncio
async def test_fetch_positions_does_not_overwrite_an_existing_annotation():
    """FTS rows already carry their annotation (retrieve_fts selects it); the lookup
    must not clobber it with a NULL from a partial row."""
    chunk_id = "00000000-0000-0000-0000-000000000001"
    candidate = _candidate(chunk_id)
    candidate.annotation = "already here"
    mock_pool = _mock_pool_returning([{"id": chunk_id, "position": 3, "annotation": None}])

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=mock_pool):
        result = await fetch_positions({"bible": [candidate]})

    assert result["bible"][0].annotation == "already here"
