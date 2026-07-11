"""run_search_pipeline must treat DB persistence as best-effort.

Results are streamed to the client before persistence runs, so a DB failure
during the searches/retrievals insert (or the explanation UPDATE) must NOT
turn a successful search into a user-facing error.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.pipeline import run_search_pipeline
from app.rag.steps.types import RankedChunk


def _chunk(cid: str) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid,
        content="content",
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        reranker_score=0.9,
    )


def _failing_pool():
    """A pool whose connection raises on every write (simulates DB failure)."""
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=Exception("db boom"))
    conn.executemany = AsyncMock(side_effect=Exception("db boom"))
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
    return pool


async def _no_explanation(*args, **kwargs):
    return
    yield  # noqa: make this an async generator that yields nothing


@pytest.mark.asyncio
async def test_persist_failure_does_not_fail_search():
    result = MagicMock()
    result.chunks = [_chunk("00000000-0000-0000-0000-000000000001")]

    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
         patch("app.rag.pipeline.get_pool", return_value=_failing_pool()), \
         patch("app.rag.pipeline.stream_explanation", _no_explanation):
        events = [
            e async for e in run_search_pipeline(
                query="grace",
                collections=["bible"],
                translation="CPDV",
                quota=3,
                user_id="00000000-0000-0000-0000-000000000abc",
            )
        ]

    types = [e["type"] for e in events]
    assert "chunk" in types, "results must still be streamed"
    assert "done" in types, "done must still be emitted despite persist failure"
    assert "error" not in types, "a persist failure must NOT surface as a failed search"


@pytest.mark.asyncio
async def test_pool_unavailable_still_returns_results():
    """No DB pool at all → still stream chunks + done, no error."""
    result = MagicMock()
    result.chunks = [_chunk("00000000-0000-0000-0000-000000000002")]

    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
         patch("app.rag.pipeline.get_pool", return_value=None), \
         patch("app.rag.pipeline.stream_explanation", _no_explanation):
        events = [
            e async for e in run_search_pipeline(
                query="grace", collections=["bible"], translation="CPDV",
                quota=3, user_id="00000000-0000-0000-0000-000000000abc",
            )
        ]

    types = [e["type"] for e in events]
    assert "chunk" in types
    assert "done" in types
    assert "error" not in types
