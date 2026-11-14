"""Keyword search runs alongside embed, HyDE and vector retrieval (PR #372).

It needs only the question, so the runner and the eval capture start it before embed
and await it where RRF needs it. These tests pin that it overlaps the other steps, that
RRF gets exactly what it got before, that an earlier failure cancels it, that its own
failure still reports as `retrieve_fts`, and that a no-FTS pipeline never starts it.
"""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from app.rag.compare import shared_runner
from app.rag.pipelines import runner
from app.rag.pipelines.registry import PIPELINES
from app.rag.steps.types import RankedChunk, RetrievalPath

CONFIG = PIPELINES["hyde_cohere_luna_seats10t80_ftsminmatch"]
TIMEOUT = 2.0


def _row(i: int) -> dict:
    return {
        "id": f"00000000-0000-0000-0000-{i:012d}", "content": f"chunk {i}",
        "reference": None, "collection": "bible",
        "document_id": "00000000-0000-0000-0000-000000000099", "document_title": "Doc",
        "author": None, "anchor": None, "position": i, "annotation": None,
    }


VECTOR = {"bible": [RetrievalPath("query", [_row(1), _row(2)])]}
KEYWORD = {"bible": [_row(3), _row(1)]}
CHUNK = RankedChunk(
    chunk_id=_row(1)["id"], content="c", reference=None, collection="bible",
    document_id=_row(1)["document_id"], document_title="Doc", author=None,
    reranker_score=0.9,
)


@contextlib.contextmanager
def _pipeline(embed, fts, vector=None, rrf=None):
    """Every step but retrieval mocked; rrf defaults to a recorder over the real one."""
    from app.rag.steps import rrf as real_rrf

    rrf = rrf or patch("app.rag.steps.rrf.run", side_effect=real_rrf.run)
    with (
        patch("app.rag.steps.embed.run", new=embed),
        patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_vector.run",
              new=vector or AsyncMock(return_value=VECTOR)),
        patch("app.rag.steps.retrieve_fts.run", new=fts),
        rrf as rrf_mock,
        patch("app.rag.steps.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value={"bible": [CHUNK]})),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool",
              new=AsyncMock(side_effect=lambda pool, *a, **k: pool)),
    ):
        yield rrf_mock


async def test_keyword_search_runs_while_embed_is_still_running():
    """Embed waits until keyword search has started, and keyword search waits until
    embed has seen it: sequential steps would deadlock and time out."""
    fts_started, embed_saw_fts = asyncio.Event(), asyncio.Event()

    async def embed(*args, **kwargs):
        await asyncio.wait_for(fts_started.wait(), TIMEOUT)
        embed_saw_fts.set()
        return [0.1] * 1536

    async def fts(*args, **kwargs):
        fts_started.set()
        await asyncio.wait_for(embed_saw_fts.wait(), TIMEOUT)
        return KEYWORD

    with _pipeline(AsyncMock(side_effect=embed), AsyncMock(side_effect=fts)):
        result = await runner.run(CONFIG, "grace", ["bible"], quota=4)

    steps = [t.step for t in result.step_timings]
    assert steps.index("retrieve_vector") < steps.index("retrieve_fts") < steps.index("rrf")


async def test_rrf_gets_the_same_lists_and_the_keyword_call_is_unchanged():
    fts = AsyncMock(return_value=KEYWORD)
    with _pipeline(AsyncMock(return_value=[0.1] * 1536), fts) as rrf:
        await runner.run(CONFIG, "grace", ["bible"], quota=4)

    k, top_n = runner._pool_sizes(CONFIG, 4)
    fts.assert_awaited_once_with("grace", ["bible"], 4, None, k=k, mode="min_match")
    [call] = rrf.call_args_list
    assert call.args == (VECTOR, KEYWORD, 4)
    assert call.kwargs == {"top_n": top_n, "k": CONFIG.retrieval.rrf_k}


async def test_an_earlier_failure_cancels_the_keyword_search():
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def fts(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def embed(*args, **kwargs):
        await asyncio.wait_for(started.wait(), TIMEOUT)
        raise RuntimeError("embedding provider down")

    with _pipeline(AsyncMock(side_effect=embed), AsyncMock(side_effect=fts)):
        with pytest.raises(runner.PipelineExecutionError) as caught:
            await runner.run(CONFIG, "grace", ["bible"], quota=4)

    assert caught.value.stage == "embed"
    assert cancelled.is_set()


async def test_a_keyword_failure_still_reports_as_retrieve_fts():
    fts = AsyncMock(side_effect=RuntimeError("pool gone"))
    with _pipeline(AsyncMock(return_value=[0.1] * 1536), fts):
        with pytest.raises(runner.PipelineExecutionError) as caught:
            await runner.run(CONFIG, "grace", ["bible"], quota=4)
    assert caught.value.stage == "retrieve_fts"


async def test_a_no_fts_pipeline_never_starts_keyword_search():
    fts = AsyncMock(return_value=KEYWORD)
    with _pipeline(AsyncMock(return_value=[0.1] * 1536), fts) as rrf:
        result = await runner.run(
            PIPELINES["hyde_nolex_cohere_haiku"], "grace", ["bible"], quota=4,
        )
    fts.assert_not_awaited()
    assert rrf.call_args.args[1] == {}
    assert "retrieve_fts" not in [t.step for t in result.step_timings]


async def test_the_eval_capture_overlaps_keyword_search_and_cancels_it_on_failure():
    fts_started, embed_saw_fts = asyncio.Event(), asyncio.Event()

    async def embed(*args, **kwargs):
        await asyncio.wait_for(fts_started.wait(), TIMEOUT)
        embed_saw_fts.set()
        return [0.1]

    async def fts(*args, **kwargs):
        fts_started.set()
        await asyncio.wait_for(embed_saw_fts.wait(), TIMEOUT)
        return KEYWORD

    with (
        patch("app.rag.compare.shared_runner.embed.run", new=AsyncMock(side_effect=embed)),
        patch("app.rag.compare.shared_runner.hyde_s25.run",
              new=AsyncMock(return_value={"bible": [[0.2]]})),
        patch("app.rag.compare.shared_runner.retrieve_vector.run",
              new=AsyncMock(return_value=VECTOR)),
        patch("app.rag.compare.shared_runner.retrieve_fts.run",
              new=AsyncMock(side_effect=fts)),
        patch("app.rag.compare.shared_runner.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
    ):
        artifacts = await shared_runner.capture("q", ["bible"], 4, [CONFIG])
    assert artifacts.candidate_pools[CONFIG.name]["bible"]

    started, cancelled = asyncio.Event(), asyncio.Event()

    async def hanging_fts(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def failing_embed(*args, **kwargs):
        await asyncio.wait_for(started.wait(), TIMEOUT)
        raise RuntimeError("down")

    with (
        patch("app.rag.compare.shared_runner.embed.run",
              new=AsyncMock(side_effect=failing_embed)),
        patch("app.rag.compare.shared_runner.retrieve_fts.run",
              new=AsyncMock(side_effect=hanging_fts)),
    ):
        with pytest.raises(RuntimeError):
            await shared_runner.capture("q", ["bible"], 4, [CONFIG])
    assert cancelled.is_set()
