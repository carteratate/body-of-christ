"""run_search_pipeline must treat DB persistence as best-effort.

Results are streamed to the client before persistence runs, so a DB failure
during the searches/retrievals insert (or the explanation UPDATE) must NOT
turn a successful search into a user-facing error.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.pipeline import _persist_empty_search, run_search_pipeline
from app.rag.pipelines.runner import PipelineExecutionError
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
    done = next(event for event in events if event["type"] == "done")
    assert done["persisted"] is False
    assert done["search_id"] is None


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
    done = next(event for event in events if event["type"] == "done")
    assert done["persisted"] is False
    assert done["search_id"] is None


@pytest.mark.asyncio
async def test_hung_persistence_is_bounded_and_results_still_complete():
    result = MagicMock()
    result.chunks = [_chunk("00000000-0000-0000-0000-000000000003")]

    class HangingAcquire:
        async def __aenter__(self):
            await asyncio.Future()

        async def __aexit__(self, *args):
            return False

    pool = MagicMock()
    pool.acquire.return_value = HangingAcquire()
    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
         patch("app.rag.pipeline.get_pool", return_value=pool), \
         patch("app.rag.pipeline.stream_explanation", _no_explanation), \
         patch("app.rag.pipeline._PERSIST_TIMEOUT_SECONDS", 0.01):
        events = [
            e async for e in run_search_pipeline(
                query="grace", collections=["bible"], translation="CPDV",
                quota=3, user_id="00000000-0000-0000-0000-000000000abc",
            )
        ]

    done = next(event for event in events if event["type"] == "done")
    assert done["persisted"] is False
    assert done["search_id"] is None


@pytest.mark.asyncio
async def test_hung_empty_persistence_is_bounded():
    pool = MagicMock()
    pool.execute = AsyncMock(side_effect=lambda *args: asyncio.Future())

    async def hang(*args, **kwargs):
        await asyncio.Future()

    pool.execute = hang
    with patch("app.rag.pipeline.get_pool", return_value=pool), \
         patch("app.rag.pipeline._PERSIST_TIMEOUT_SECONDS", 0.01):
        persisted = await _persist_empty_search(
            search_id="00000000-0000-0000-0000-000000000004",
            user_id="00000000-0000-0000-0000-000000000abc",
            query="grace",
            collections=["bible"],
            translation="CPDV",
            quota=3,
        )

    assert persisted is False


@pytest.mark.asyncio
async def test_slow_runner_emits_heartbeat_before_results():
    """Long retrieval/reranking work must not leave the SSE connection idle."""
    result = MagicMock()
    result.chunks = []
    result.outcome = "no_candidates"
    result.collection_outcomes = {"bible": "no_candidates"}

    async def slow_pipeline(**kwargs):
        await asyncio.sleep(0.025)
        return result

    with patch("app.rag.pipeline.run_pipeline", slow_pipeline), \
         patch("app.rag.pipeline._PIPELINE_HEARTBEAT_SECONDS", 0.005):
        events = [
            e async for e in run_search_pipeline(
                query="grace", collections=["bible"], translation="CPDV",
                quota=3, user_id=None,
            )
        ]

    heartbeats = [
        event for event in events
        if event["type"] == "status" and event.get("heartbeat")
    ]
    assert heartbeats
    assert events[-1]["type"] == "done"
    assert events[-1]["outcome"] == "no_candidates"


@pytest.mark.asyncio
async def test_empty_degraded_pipeline_emits_error_not_done():
    result = MagicMock()
    result.chunks = []
    result.outcome = "retrieval_failed"
    result.collection_outcomes = {"bible": "retrieval_failed"}

    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)):
        events = [
            e async for e in run_search_pipeline(
                query="grace", collections=["bible"], translation="CPDV",
                quota=3, user_id=None,
            )
        ]

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "retrieval_failed"
    assert not any(event["type"] == "done" for event in events)


@pytest.mark.asyncio
async def test_embedding_exception_has_specific_failure_stage():
    with patch(
        "app.rag.pipeline.run_pipeline",
        AsyncMock(side_effect=PipelineExecutionError("embed")),
    ):
        events = [
            e async for e in run_search_pipeline(
                query="grace", collections=["bible"], translation="CPDV",
                quota=3, user_id=None,
            )
        ]

    assert events[-1] == {
        "type": "error",
        "code": "embedding_failed",
        "stage": "embedding",
        "detail": "The query could not be prepared for semantic retrieval.",
    }
