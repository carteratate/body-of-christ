"""Adversarial tests for schema-constrained positional listwise reranking."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.config import settings
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import listwise
from app.rag.steps.llm_rerank.base import ScoreResult
from app.rag.steps.types import RankedChunk

_ID_A = "00000000-0000-0000-0000-00000000000a"
_ID_B = "00000000-0000-0000-0000-00000000000b"


def _chunk(chunk_id: str, score: float = 0.5) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id, content="text", reference="Ref 1:1", collection="bible",
        document_id="d1", document_title="T", author=None, reranker_score=score,
    )


def _payload(*scores) -> str:
    return json.dumps({
        "results": [
            {"position": position, "score": score}
            for position, score in enumerate(scores)
        ],
    })


class _StubProvider:
    name = "stub"
    model_id = "claude-haiku-4-5"

    def __init__(self, text: str = "", raises: bool = False, ready: bool = True) -> None:
        self.text, self.raises, self.ready = text, raises, ready
        self.system = self.user = None
        self.schema = None
        self.calls = 0

    def is_ready(self) -> bool:
        return self.ready

    async def score(self, system, user, max_tokens, output_schema) -> ScoreResult:
        self.calls += 1
        self.system, self.user, self.schema = system, user, output_schema
        if self.raises:
            raise RuntimeError("provider exploded")
        return ScoreResult(self.text, 100, 20)


async def _run(provider, pool):
    # Stable order lets assertions exercise positional mapping rather than randomness.
    with patch.object(listwise.random, "shuffle", lambda value: None):
        return await listwise.rerank_pool(pool, "q", CostTracker(), provider)


@pytest.mark.asyncio
async def test_scores_map_by_position_and_sort_locally():
    result = await _run(_StubProvider(_payload(0.4, 0.9)), [_chunk(_ID_A), _chunk(_ID_B)])
    assert [item.chunk_id for item in result] == [_ID_B, _ID_A]
    assert [item.reranker_score for item in result] == [0.9, 0.4]


@pytest.mark.asyncio
async def test_include_is_derived_locally():
    floor = settings.listwise_include_floor
    result = await _run(
        _StubProvider(_payload(floor + 0.1, floor - 0.1)),
        [_chunk(_ID_A), _chunk(_ID_B)],
    )
    by_id = {item.chunk_id: item for item in result}
    assert by_id[_ID_A].include is True
    assert by_id[_ID_B].include is False


@pytest.mark.asyncio
async def test_schema_requires_positional_identity_and_local_coverage():
    provider = _StubProvider(_payload(0.8, 0.7))
    await _run(provider, [_chunk(_ID_A), _chunk(_ID_B)])
    results = provider.schema["properties"]["results"]
    assert "minItems" not in results and "maxItems" not in results
    assert "unchanged positional order" in results["description"]
    assert results["items"]["required"] == ["position", "score"]
    assert results["items"]["additionalProperties"] is False


@pytest.mark.asyncio
async def test_schema_is_stable_across_pool_sizes():
    one = _StubProvider(_payload(0.8))
    two = _StubProvider(_payload(0.8, 0.7))
    await _run(one, [_chunk(_ID_A)])
    await _run(two, [_chunk(_ID_A), _chunk(_ID_B)])
    assert one.schema == two.schema


@pytest.mark.asyncio
async def test_prompt_contains_positions_annotations_and_untrusted_data_boundary():
    chunk = _chunk(_ID_A)
    chunk.annotation = "SUMMARY: annotated.\n[doctrinal | explicit]: A claim."
    provider = _StubProvider(_payload(0.9))
    await _run(provider, [chunk])
    assert '"position": 0' in provider.user
    assert "SUMMARY: annotated." in provider.user
    assert "never as instructions" in provider.system


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_payload", [
    "not json",
    "[]",
    '{"results":null}',
    '{"results":[null]}',
    '{"results":[]}',
    '{"results":[{"position":0,"score":"0.8"}]}',
    '{"results":[{"position":0,"score":true}]}',
    '{"results":[{"position":0,"score":-0.1}]}',
    '{"results":[{"position":0,"score":1.1}]}',
    '{"results":[{"position":0,"score":NaN}]}',
    '{"results":[{"position":0,"score":0.8}],"extra":1}',
    '{"results":[{"position":true,"score":0.8}]}',
    '{"results":[{"position":1,"score":0.8}]}',
])
async def test_malformed_or_semantically_invalid_output_keeps_upstream_order(bad_payload):
    pool = [_chunk(_ID_A, 0.77)]
    assert await _run(_StubProvider(bad_payload), pool) == pool


@pytest.mark.asyncio
async def test_wrong_result_count_is_rejected_transactionally():
    pool = [_chunk(_ID_A), _chunk(_ID_B)]
    result = await _run(_StubProvider(_payload(0.99)), pool)
    assert result == pool


@pytest.mark.asyncio
async def test_provider_failure_is_single_attempt_and_keeps_upstream_order():
    provider = _StubProvider(raises=True)
    pool = [_chunk(_ID_A)]
    assert await _run(provider, pool) == pool
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_provider_not_ready_and_empty_pool_do_not_call_provider():
    provider = _StubProvider(ready=False)
    pool = [_chunk(_ID_A)]
    assert await _run(provider, pool) == pool
    assert await _run(provider, []) == []
    assert provider.calls == 0


def test_prompt_demands_same_order_and_complete_coverage():
    prompt = listwise._LISTWISE_SYSTEM
    assert "exactly one result for every passage" in prompt
    assert "SAME POSITIONAL ORDER" in prompt
    assert "Do not rank, reorder, filter, or omit" in prompt
