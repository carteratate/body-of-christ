"""Degraded rerank stages must be recorded, not inferred from cost.

Inference from the cost breakdown misses two real cases: Cohere records cost per
SUCCESSFUL collection (so 4-of-5 succeeding leaves the step present), and listwise
records cost BEFORE parsing (so a parse failure still bills). Both produce a
plausible result set, so an evaluation that misses them averages a query where the
reranker never ran against queries where it did.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.rag.steps import degradation, rerank_cohere
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import listwise
from app.rag.steps.llm_rerank.base import ScoreResult
from app.rag.steps.types import ChunkCandidate, RankedChunk


def _cand(i: int, collection: str, content: str = "text") -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content=content, reference=None,
        collection=collection, document_id="d1", document_title="T", author=None,
        rrf_score=0.5,
    )


class _Res:
    def __init__(self, i, s): self.index, self.relevance_score = i, s


class _Resp:
    def __init__(self, n):
        self.results = [_Res(i, 0.9 - i * 0.01) for i in range(n)]
        self.meta = type("M", (), {"billed_units": type("B", (), {"search_units": 1})()})()


def test_accounting_starts_empty():
    degradation.begin_degradation_accounting()
    assert degradation.degradations() == []


@pytest.mark.asyncio
async def test_partial_cohere_failure_is_recorded_even_though_cost_is_present():
    """4-of-5 collections succeeding leaves `rerank_cohere` in the cost breakdown, so
    the old cost-based flag reported this query as healthy."""
    class _PartialClient:
        async def rerank(self, **kw):
            if "POISON" in kw["documents"][0]:
                raise RuntimeError("cohere 500")
            return _Resp(len(kw["documents"]))

    degradation.begin_degradation_accounting()
    tracker = CostTracker()
    with patch.object(rerank_cohere, "_client", _PartialClient()):
        await rerank_cohere.run_per_collection(
            {"bible": [_cand(0, "bible")],
             "summa": [_cand(1, "summa", "POISON")]},
            "q", 4, tracker,
        )
    # Cost IS present from the collection that succeeded...
    assert "rerank_cohere" in tracker.breakdown()
    # ...but the failure is still recorded.
    assert degradation.degradations() == ["rerank_cohere:summa:RuntimeError"]
    event = degradation.events()[0]
    assert event.scope == "summa"
    assert event.action == "rrf_fallback_used"


@pytest.mark.asyncio
async def test_healthy_cohere_run_records_nothing():
    class _OK:
        async def rerank(self, **kw):
            return _Resp(len(kw["documents"]))

    degradation.begin_degradation_accounting()
    with patch.object(rerank_cohere, "_client", _OK()):
        await rerank_cohere.run_per_collection(
            {"bible": [_cand(0, "bible")]}, "q", 4, CostTracker(),
        )
    assert degradation.degradations() == []


class _StubProvider:
    name, model_id = "stub", "claude-haiku-4-5"

    def __init__(self, text="", raises=False, ready=True):
        self.text, self.raises, self.ready = text, raises, ready

    def is_ready(self): return self.ready

    async def score(self, system, user, max_tokens, output_schema):
        if self.raises:
            raise RuntimeError("boom")
        return ScoreResult(text=self.text, input_tokens=10, output_tokens=5)


def _chunk(i):
    return RankedChunk(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content="c", reference=None,
        collection="bible", document_id="d1", document_title="T", author=None,
        reranker_score=0.5,
    )


@pytest.mark.asyncio
async def test_listwise_malformed_response_is_recorded_even_though_cost_is_present():
    """Listwise records cost BEFORE extracting JSON, so a malformed response still
    bills — the pipeline silently becomes cohere_only for that query."""
    degradation.begin_degradation_accounting()
    tracker = CostTracker()
    out = await listwise.rerank_pool(
        [_chunk(0)], "q", tracker, _StubProvider("not json at all"),
    )
    assert tracker.breakdown(), "cost was recorded before the response was parsed"
    assert any("structured_decode_failed" in d for d in degradation.degradations())
    assert len(out) == 1, "upstream order must be preserved"


@pytest.mark.asyncio
async def test_listwise_wrong_coverage_is_recorded():
    degradation.begin_degradation_accounting()
    payload = json.dumps({"results": []})
    await listwise.rerank_pool([_chunk(0)], "q", CostTracker(), _StubProvider(payload))
    assert any("structured_contract_failed" in d for d in degradation.degradations())


@pytest.mark.asyncio
async def test_listwise_transport_failure_is_recorded():
    degradation.begin_degradation_accounting()
    await listwise.rerank_pool([_chunk(0)], "q", CostTracker(),
                               _StubProvider(raises=True))
    assert any("provider_call_failed" in d for d in degradation.degradations())


@pytest.mark.asyncio
async def test_listwise_not_ready_is_recorded():
    degradation.begin_degradation_accounting()
    await listwise.rerank_pool([_chunk(0)], "q", CostTracker(),
                               _StubProvider(ready=False))
    assert any("provider_not_ready" in d for d in degradation.degradations())


@pytest.mark.asyncio
async def test_healthy_listwise_records_nothing():
    degradation.begin_degradation_accounting()
    payload = json.dumps({"results": [{"position": 0, "score": 0.9}]})
    await listwise.rerank_pool([_chunk(0)], "q", CostTracker(), _StubProvider(payload))
    assert degradation.degradations() == []


def test_raise_policy_turns_graceful_degradation_into_test_failure():
    degradation.begin_degradation_accounting(degradation.DegradationPolicy.RAISE)
    with pytest.raises(RuntimeError, match="pipeline degraded"):
        degradation.record("retrieve_fts", "timeout", "path_omitted", scope="bible")


def test_recovery_is_observable_without_making_result_degraded():
    degradation.begin_degradation_accounting()

    degradation.record_recovery(
        "rerank_listwise_luna",
        "incomplete_output",
        "targeted_retry",
        details={"matched": 34, "expected": 35},
    )

    assert degradation.degradations() == []
    assert degradation.recovery_event_dicts() == [
        {
            "stage": "rerank_listwise_luna",
            "reason": "incomplete_output",
            "action": "targeted_retry",
            "scope": None,
            "details": {"matched": 34, "expected": 35},
        }
    ]
