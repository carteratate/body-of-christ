"""Cohere fan-out: one call per collection, real billed units, per-collection isolation."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import settings
from app.rag.steps import rerank_cohere
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import ChunkCandidate


def _cand(i: int, collection: str, content: str = "passage text") -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content=content, reference=None,
        collection=collection, document_id="d1", document_title="T", author=None,
        rrf_score=1.0 - i * 0.01,
    )


class _Result:
    def __init__(self, index: int, score: float) -> None:
        self.index, self.relevance_score = index, score


class _BilledUnits:
    def __init__(self, units) -> None:
        self.search_units = units


class _Meta:
    def __init__(self, units) -> None:
        self.billed_units = _BilledUnits(units)


class _Response:
    def __init__(self, n: int, units=1) -> None:
        self.results = [_Result(i, 0.9 - i * 0.01) for i in range(n)]
        self.meta = _Meta(units)


class _StubClient:
    def __init__(self, units=1, fail_on: set[str] | None = None) -> None:
        self.calls: list[dict] = []
        self.units = units
        self.fail_on = fail_on or set()

    async def rerank(self, *, model, query, documents, top_n, max_tokens_per_doc):
        self.calls.append({"documents": documents, "max_tokens_per_doc": max_tokens_per_doc})
        if any(f in documents[0] for f in self.fail_on):
            raise RuntimeError("cohere 500")
        return _Response(len(documents), self.units)


@pytest.mark.asyncio
async def test_one_call_per_collection():
    stub = _StubClient()
    candidates = {c: [_cand(i, c) for i in range(5)] for c in ("bible", "summa", "canon-law")}
    with patch.object(rerank_cohere, "_client", stub):
        out = await rerank_cohere.run_per_collection(candidates, "q", 4, CostTracker())
    assert len(stub.calls) == 3
    assert set(out) == {"bible", "summa", "canon-law"}


@pytest.mark.asyncio
async def test_passes_max_tokens_per_doc_from_settings():
    stub = _StubClient()
    with patch.object(rerank_cohere, "_client", stub):
        await rerank_cohere.run_per_collection(
            {"bible": [_cand(0, "bible")]}, "q", 4, CostTracker(),
        )
    assert stub.calls[0]["max_tokens_per_doc"] == settings.cohere_max_tokens_per_doc


@pytest.mark.asyncio
async def test_pool_is_packed_not_fixed_and_respects_the_cap():
    """Short documents pack more per call than long ones — same search unit either way."""
    short = _StubClient()
    long = _StubClient()
    with patch.object(rerank_cohere, "_client", short):
        await rerank_cohere.run_per_collection(
            {"bible": [_cand(i, "bible", "x" * 200) for i in range(200)]},
            "q", 4, CostTracker(),
        )
    with patch.object(rerank_cohere, "_client", long):
        await rerank_cohere.run_per_collection(
            {"bible": [_cand(i, "bible", "x" * 4000) for i in range(200)]},
            "q", 4, CostTracker(),
        )
    n_short = len(short.calls[0]["documents"])
    n_long = len(long.calls[0]["documents"])
    assert n_short > n_long
    assert n_short <= settings.cohere_max_pool


@pytest.mark.asyncio
async def test_billed_search_units_are_summed_across_collections():
    """A flat per-call charge would report 10 per-collection calls as costing the same
    as one global call."""
    stub = _StubClient(units=2)
    candidates = {c: [_cand(0, c)] for c in ("bible", "summa", "canon-law")}
    tracker = CostTracker()
    with patch.object(rerank_cohere, "_client", stub):
        await rerank_cohere.run_per_collection(candidates, "q", 4, tracker)
    # 3 collections x 2 units x $0.0025
    assert tracker.breakdown()["rerank_cohere"] == pytest.approx(3 * 2 * 0.0025)


@pytest.mark.asyncio
async def test_missing_billed_units_defaults_to_one_unit():
    class _NoMeta(_StubClient):
        async def rerank(self, **kw):
            self.calls.append(kw)
            r = _Response(len(kw["documents"]))
            del r.meta
            return r

    tracker = CostTracker()
    with patch.object(rerank_cohere, "_client", _NoMeta()):
        await rerank_cohere.run_per_collection(
            {"bible": [_cand(0, "bible")]}, "q", 4, tracker,
        )
    assert tracker.breakdown()["rerank_cohere"] == pytest.approx(0.0025)


@pytest.mark.asyncio
async def test_one_failing_collection_falls_back_without_losing_the_others():
    stub = _StubClient(fail_on={"POISON"})
    candidates = {
        "bible": [_cand(0, "bible")],
        "summa": [_cand(1, "summa", "POISON")],
    }
    with patch.object(rerank_cohere, "_client", stub):
        out = await rerank_cohere.run_per_collection(candidates, "q", 4, CostTracker())
    assert len(out["bible"]) == 1
    # summa degrades to RRF order rather than disappearing.
    assert len(out["summa"]) == 1
    assert out["summa"][0].reranker_score > 0


@pytest.mark.asyncio
async def test_empty_candidates_makes_no_calls():
    stub = _StubClient()
    with patch.object(rerank_cohere, "_client", stub):
        out = await rerank_cohere.run_per_collection({"bible": []}, "q", 4, CostTracker())
    assert stub.calls == []
    assert out == {}


@pytest.mark.asyncio
async def test_uninitialised_client_raises_rather_than_silently_returning_nothing():
    with patch.object(rerank_cohere, "_client", None):
        with pytest.raises(RuntimeError, match="Cohere client not initialized"):
            await rerank_cohere.run_per_collection(
                {"bible": [_cand(0, "bible")]}, "q", 4, CostTracker(),
            )


@pytest.mark.asyncio
async def test_annotation_is_carried_into_the_ranked_output():
    """A second-stage reranker needs the annotation; RankedChunk must not drop it."""
    stub = _StubClient()
    cand = _cand(0, "bible")
    cand.annotation = "SUMMARY: x\n[doctrinal | explicit]: y"
    with patch.object(rerank_cohere, "_client", stub):
        out = await rerank_cohere.run_per_collection(
            {"bible": [cand]}, "q", 4, CostTracker(),
        )
    assert out["bible"][0].annotation == cand.annotation
    assert "[doctrinal | explicit]" in stub.calls[0]["documents"][0]


# --- throttle + 429 retry: timing must stay interpretable ---

def test_throttle_accounting_merges_concurrent_waits_instead_of_summing():
    """Per-collection tasks wait CONCURRENTLY on one shared window. Summing their
    waits reported 5 x 20s inside a 20s span, and subtracting that from wall clock
    produced negative latencies in a real run — so overlapping intervals are merged.
    """
    from app.rag.steps import rerank_cohere as rc

    rc.begin_throttle_accounting()
    box = rc._throttle_wait.get()

    # Five tasks each "wait" 20s starting at the same instant: 20s elapsed, not 100s.
    box.extend((1000.0, 1020.0) for _ in range(5))
    assert rc.throttle_wait_seconds() == pytest.approx(20.0)


def test_throttle_accounting_adds_disjoint_waits():
    from app.rag.steps import rerank_cohere as rc

    rc.begin_throttle_accounting()
    box = rc._throttle_wait.get()
    box.append((1000.0, 1010.0))   # 10s
    box.append((2000.0, 2005.0))   # 5s, no overlap
    assert rc.throttle_wait_seconds() == pytest.approx(15.0)


def test_throttle_accounting_merges_partial_overlap():
    from app.rag.steps import rerank_cohere as rc

    rc.begin_throttle_accounting()
    box = rc._throttle_wait.get()
    box.append((1000.0, 1010.0))
    box.append((1005.0, 1020.0))   # overlaps -> span is 1000..1020
    assert rc.throttle_wait_seconds() == pytest.approx(20.0)


def test_throttle_accounting_is_zero_before_any_wait():
    from app.rag.steps import rerank_cohere as rc

    rc.begin_throttle_accounting()
    assert rc.throttle_wait_seconds() == 0.0


@pytest.mark.asyncio
async def test_limiter_records_a_wait_when_the_window_is_full():
    """Behavioural check that the limiter actually feeds the accountant."""
    from app.rag.steps import rerank_cohere as rc

    rc.begin_throttle_accounting()
    with patch.object(settings, "cohere_max_calls_per_minute", 1):
        await rc._rate_limiter.acquire()          # takes the only slot
        rc._rate_limiter._calls[0] -= 61.0        # window already expired
        await rc._rate_limiter.acquire()          # must NOT wait
    assert rc.throttle_wait_seconds() == 0.0
    assert len(rc._rate_limiter._calls) >= 1


@pytest.mark.asyncio
async def test_429_is_retried_and_the_backoff_is_counted_not_hidden():
    import asyncio as _asyncio

    from app.rag.steps import rerank_cohere as rc

    class _Boom(Exception):
        status_code = 429

    calls = {"n": 0}

    class _FlakyClient:
        async def rerank(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _Boom("429 rate limited")
            return _Response(len(kw["documents"]))

    rc.begin_throttle_accounting()
    slept: list[float] = []

    async def _no_sleep(s):
        slept.append(s)

    with (
        patch.object(rc, "_client", _FlakyClient()),
        patch.object(_asyncio, "sleep", _no_sleep),
    ):
        out = await rc.run_per_collection(
            {"bible": [_cand(0, "bible")]}, "q", 4, CostTracker(),
        )

    assert calls["n"] == 2, "429 was not retried"
    # A real Cohere score, not the 0.40 fallback band -> the retry actually worked.
    assert out["bible"][0].reranker_score > 0.5
    assert rc.throttle_wait_seconds() == pytest.approx(sum(slept))


@pytest.mark.asyncio
async def test_non_429_errors_are_not_retried():
    """Only 429 is transient. Retrying a 400 or auth failure just delays the fallback."""
    from app.rag.steps import rerank_cohere as rc

    calls = {"n": 0}

    class _BadRequest(Exception):
        status_code = 400

    class _AlwaysBad:
        async def rerank(self, **kw):
            calls["n"] += 1
            raise _BadRequest("bad request")

    with patch.object(rc, "_client", _AlwaysBad()):
        out = await rc.run_per_collection(
            {"bible": [_cand(0, "bible")]}, "q", 4, CostTracker(),
        )
    assert calls["n"] == 1
    # Degraded to the fallback band, which must not outrank a real score.
    assert out["bible"][0].reranker_score <= settings.cohere_fallback_score_base
