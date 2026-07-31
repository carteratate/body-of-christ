"""Listwise rerank parsing must never lose the pool.

Every failure mode falls back to the upstream (Cohere) order rather than raising or
returning empty — a parse failure that silently dropped reranking is exactly the
behaviour this replaces.
"""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import listwise
from app.rag.steps.llm_rerank.base import ScoreResult
from app.rag.steps.types import RankedChunk

_ID_A = "00000000-0000-0000-0000-00000000000a"
_ID_B = "00000000-0000-0000-0000-00000000000b"


def _chunk(chunk_id: str, score: float = 0.5, collection: str = "bible") -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id, content="text", reference="Ref 1:1", collection=collection,
        document_id="d1", document_title="T", author=None, reranker_score=score,
    )


class _StubProvider:
    """Returns a fixed payload; records the prompt it was given."""

    name = "stub"
    model_id = "claude-haiku-4-5"

    def __init__(self, text: str = "", raises: bool = False) -> None:
        self.text = text
        self.raises = raises
        self.system: str | None = None
        self.user: str | None = None

    def is_ready(self) -> bool:
        return True

    async def score(self, system: str, user: str, max_tokens: int) -> ScoreResult:
        self.system, self.user = system, user
        if self.raises:
            raise RuntimeError("provider exploded")
        return ScoreResult(text=self.text, input_tokens=100, output_tokens=20)


async def _run(provider, pool):
    return await listwise.rerank_pool(pool, "q", CostTracker(), provider)


# --- happy path ---

@pytest.mark.asyncio
async def test_scores_and_orders_by_llm_score():
    payload = json.dumps([{"chunk_id": _ID_B, "score": 0.9},
                          {"chunk_id": _ID_A, "score": 0.4}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A), _chunk(_ID_B)])
    assert [r.chunk_id for r in result] == [_ID_B, _ID_A]
    assert result[0].reranker_score == 0.9


@pytest.mark.asyncio
async def test_include_derived_from_score_not_requested_from_model():
    floor = settings.listwise_include_floor
    payload = json.dumps([{"chunk_id": _ID_A, "score": floor + 0.1},
                          {"chunk_id": _ID_B, "score": floor - 0.1}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A), _chunk(_ID_B)])
    by_id = {r.chunk_id: r for r in result}
    assert by_id[_ID_A].include is True
    assert by_id[_ID_B].include is False


@pytest.mark.asyncio
async def test_omitted_candidate_rejects_partial_response_and_keeps_upstream_order():
    payload = json.dumps([{"chunk_id": _ID_A, "score": 0.9}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A), _chunk(_ID_B)])
    by_id = {r.chunk_id: r for r in result}
    assert set(by_id) == {_ID_A, _ID_B}
    assert by_id[_ID_B].include is True
    assert by_id[_ID_B].reranker_score == 0.5


@pytest.mark.asyncio
async def test_annotation_survives_into_the_prompt():
    pool = [_chunk(_ID_A)]
    pool[0].annotation = "SUMMARY: annotated.\n[doctrinal | explicit]: A claim."
    provider = _StubProvider(json.dumps([{"chunk_id": _ID_A, "score": 0.9}]))
    await _run(provider, pool)
    assert "SUMMARY: annotated." in provider.user
    assert "[doctrinal | explicit]" in provider.user


# --- fallback paths: all must return the pool, none may raise ---

@pytest.mark.asyncio
async def test_provider_exception_keeps_upstream_order():
    pool = [_chunk(_ID_A, 0.8), _chunk(_ID_B, 0.2)]
    result = await _run(_StubProvider(raises=True), pool)
    assert result == pool


@pytest.mark.asyncio
async def test_no_json_array_keeps_upstream_order():
    pool = [_chunk(_ID_A)]
    assert await _run(_StubProvider("I cannot comply."), pool) == pool


@pytest.mark.asyncio
async def test_truncated_json_keeps_upstream_order():
    pool = [_chunk(_ID_A)]
    truncated = '[{"chunk_id":"%s","score":0.9},{"chunk_id":"%s","sc' % (_ID_A, _ID_B)
    assert await _run(_StubProvider(truncated), pool) == pool


@pytest.mark.asyncio
async def test_empty_array_keeps_upstream_order():
    pool = [_chunk(_ID_A)]
    assert await _run(_StubProvider("[]"), pool) == pool


@pytest.mark.asyncio
async def test_all_invalid_uuids_keeps_upstream_order():
    pool = [_chunk(_ID_A)]
    payload = json.dumps([{"chunk_id": "not-a-uuid", "score": 0.9}])
    assert await _run(_StubProvider(payload), pool) == pool


@pytest.mark.asyncio
async def test_unknown_chunk_id_is_dropped_not_invented():
    """A hallucinated but well-formed UUID must not enter the results."""
    unknown = "00000000-0000-0000-0000-0000000000ff"
    payload = json.dumps([{"chunk_id": _ID_A, "score": 0.9},
                          {"chunk_id": unknown, "score": 0.95}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A)])
    assert [r.chunk_id for r in result] == [_ID_A]


@pytest.mark.asyncio
async def test_duplicate_chunk_id_counted_once():
    payload = json.dumps([{"chunk_id": _ID_A, "score": 0.9},
                          {"chunk_id": _ID_A, "score": 0.1}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A)])
    assert len(result) == 1
    assert result[0].reranker_score == 0.5


@pytest.mark.asyncio
async def test_identical_duplicate_is_harmless_when_expected_coverage_is_complete():
    payload = json.dumps([{"chunk_id": _ID_A, "score": 0.9},
                          {"chunk_id": _ID_A, "score": 0.9}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A)])
    assert result[0].reranker_score == 0.9


@pytest.mark.asyncio
async def test_repair_scores_only_missing_ids_and_merges_valid_first_pass():
    class SequentialProvider(_StubProvider):
        def __init__(self):
            super().__init__()
            self.calls: list[str] = []

        async def score(self, system, user, max_tokens):
            self.calls.append(user)
            if len(self.calls) == 1:
                text = json.dumps([{"chunk_id": _ID_A, "score": 0.8}])
            else:
                text = json.dumps([{"chunk_id": _ID_B, "score": 0.7}])
            return ScoreResult(text=text, input_tokens=100, output_tokens=20)

    provider = SequentialProvider()
    result = await _run(provider, [_chunk(_ID_A), _chunk(_ID_B)])

    assert {r.chunk_id: r.reranker_score for r in result} == {
        _ID_A: 0.8,
        _ID_B: 0.7,
    }
    assert "Score ONLY the expected IDs" in provider.calls[1]
    assert f"Expected IDs:\n{_ID_B}" in provider.calls[1]


@pytest.mark.asyncio
async def test_luna_provider_exception_does_not_retry():
    class CountingLuna(_StubProvider):
        name = "luna"

        def __init__(self):
            super().__init__(raises=True)
            self.calls = 0

        async def score(self, system, user, max_tokens):
            self.calls += 1
            return await super().score(system, user, max_tokens)

    provider = CountingLuna()
    pool = [_chunk(_ID_A, 0.8), _chunk(_ID_B, 0.2)]

    assert await _run(provider, pool) == pool
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_luna_incomplete_output_does_not_retry():
    class CountingLuna(_StubProvider):
        name = "luna"

        def __init__(self):
            super().__init__(json.dumps([{"chunk_id": _ID_A, "score": 0.9}]))
            self.calls = 0

        async def score(self, system, user, max_tokens):
            self.calls += 1
            return await super().score(system, user, max_tokens)

    provider = CountingLuna()
    pool = [_chunk(_ID_A, 0.8), _chunk(_ID_B, 0.2)]

    assert await _run(provider, pool) == pool
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_non_numeric_score_entry_is_dropped():
    payload = json.dumps([{"chunk_id": _ID_A, "score": "high"},
                          {"chunk_id": _ID_B, "score": 0.7}])
    result = await _run(_StubProvider(payload), [_chunk(_ID_A), _chunk(_ID_B)])
    by_id = {r.chunk_id: r for r in result}
    assert by_id[_ID_B].reranker_score == 0.5
    assert by_id[_ID_A].include is True


@pytest.mark.asyncio
async def test_provider_not_ready_keeps_upstream_order():
    class NotReady(_StubProvider):
        def is_ready(self) -> bool:
            return False

    pool = [_chunk(_ID_A)]
    assert await _run(NotReady(), pool) == pool


@pytest.mark.asyncio
async def test_empty_pool_returns_empty():
    assert await _run(_StubProvider("[]"), []) == []


# --- coverage: a filtering model must be surfaced, not silently accepted ---

@pytest.mark.asyncio
async def test_partial_coverage_warns(caplog):
    """Haiku scored 97% of the pool and Luna 62% under an ambiguous prompt, which
    made a provider A/B a comparison of two different tasks. Low coverage must be
    loud."""
    pool = [_chunk(f"00000000-0000-0000-0000-{i:012d}") for i in range(10)]
    payload = json.dumps([{"chunk_id": pool[i].chunk_id, "score": 0.9} for i in range(3)])
    with caplog.at_level("WARNING"):
        result = await _run(_StubProvider(payload), pool)
    assert "no valid entries" in caplog.text
    # Partial model output is rejected transactionally; the complete upstream order
    # is retained rather than mixing model scores with synthetic zeros.
    assert len(result) == 10
    assert sum(1 for r in result if r.include) == 10
    assert {r.reranker_score for r in result} == {0.5}


@pytest.mark.asyncio
async def test_full_coverage_does_not_warn(caplog):
    pool = [_chunk(f"00000000-0000-0000-0000-{i:012d}") for i in range(10)]
    payload = json.dumps([{"chunk_id": c.chunk_id, "score": 0.9} for c in pool])
    with caplog.at_level("WARNING"):
        await _run(_StubProvider(payload), pool)
    assert "LOW COVERAGE" not in caplog.text


def test_listwise_prompt_demands_every_passage_be_scored():
    """The prompt must not be readable as 'return only the good ones'."""
    p = listwise._LISTWISE_SYSTEM
    assert "score EVERY passage" in p
    assert "Do NOT filter" in p
    assert "exactly one entry per" in p
    assert "worth returning" not in p  # the ambiguous phrasing that caused the split
