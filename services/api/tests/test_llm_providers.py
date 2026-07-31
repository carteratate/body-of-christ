"""Provider parity: Haiku and Luna must be interchangeable behind one interface.

Given the same model output, both must produce identical parsed results — a provider
swap must not change how a response is interpreted.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.config import settings
from app.rag.steps import rerank
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps import rerank_haiku
from app.rag.steps.llm_rerank import openai_provider, pointwise
from app.rag.steps.types import ChunkCandidate

_ID = "00000000-0000-0000-0000-00000000000a"
_PAYLOAD = json.dumps([{"chunk_id": _ID, "score": 0.82, "include": True}])


def _cand() -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=_ID, content="passage", reference="Ref 1:1", collection="bible",
        document_id="d1", document_title="T", author=None, rrf_score=0.5,
    )


# --- registry ---

def test_both_providers_registered_under_expected_names():
    assert set(rerank.PROVIDERS) == {"haiku", "luna"}


def test_provider_model_ids_come_from_settings():
    assert rerank.PROVIDERS["haiku"].model_id == settings.rerank_model
    assert rerank.PROVIDERS["luna"].model_id == settings.rerank_luna_model


def test_luna_model_id_is_priced():
    """An unpriced model would silently report $0 for every Luna run."""
    from app.rag.steps.cost_tracker import _OPENAI_PRICING

    assert settings.rerank_luna_model in _OPENAI_PRICING


def test_providers_report_not_ready_before_init():
    """is_ready() gates the call so an uninitialised client falls back rather than
    raising AttributeError on None."""
    with patch.object(rerank_haiku, "_client", None):
        assert rerank_haiku.PROVIDER.is_ready() is False
    with patch.object(openai_provider, "_client", None):
        assert openai_provider.PROVIDER.is_ready() is False


# --- anthropic transport ---

class _FakeAnthropicUsage:
    input_tokens, output_tokens = 120, 30


class _FakeAnthropicBlock:
    text = _PAYLOAD


class _FakeAnthropicResponse:
    content = [_FakeAnthropicBlock()]
    usage = _FakeAnthropicUsage()


class _FakeAnthropicMessages:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeAnthropicResponse()


class _FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = _FakeAnthropicMessages()


# --- openai transport ---

class _FakeOpenAIUsage:
    prompt_tokens, completion_tokens = 120, 30


class _FakeOpenAIMessage:
    content = _PAYLOAD


class _FakeOpenAIChoice:
    message = _FakeOpenAIMessage()


class _FakeOpenAIResponse:
    choices = [_FakeOpenAIChoice()]
    usage = _FakeOpenAIUsage()


class _FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeOpenAIResponse()


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


@pytest.mark.asyncio
async def test_both_providers_return_identical_score_results():
    with patch.object(rerank_haiku, "_client", _FakeAnthropicClient()):
        a = await rerank_haiku.PROVIDER.score("sys", "user", 4096)
    with patch.object(openai_provider, "_client", _FakeOpenAIClient()):
        o = await openai_provider.PROVIDER.score("sys", "user", 4096)

    assert a.text == o.text == _PAYLOAD
    assert (a.input_tokens, a.output_tokens) == (o.input_tokens, o.output_tokens)


@pytest.mark.asyncio
async def test_pointwise_parses_identically_across_providers():
    """The load-bearing parity check: same payload, same RankedChunk output."""
    results = []
    for module, client in (
        (rerank_haiku, _FakeAnthropicClient()),
        (openai_provider, _FakeOpenAIClient()),
    ):
        with patch.object(module, "_client", client):
            results.append(
                await pointwise.rerank_collection(
                    [_cand()], "q", 4, CostTracker(), module.PROVIDER,
                )
            )
    a, o = results
    assert [(r.chunk_id, r.reranker_score, r.include) for r in a] == \
           [(r.chunk_id, r.reranker_score, r.include) for r in o]


@pytest.mark.asyncio
async def test_luna_sends_system_prompt_as_a_system_message():
    """The same prompt text must work unchanged on both providers."""
    client = _FakeOpenAIClient()
    with patch.object(openai_provider, "_client", client):
        await openai_provider.PROVIDER.score("SYSTEM-TEXT", "USER-TEXT", 4096)
    messages = client.chat.completions.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "SYSTEM-TEXT"}
    assert messages[1] == {"role": "user", "content": "USER-TEXT"}


@pytest.mark.asyncio
async def test_each_provider_records_cost_under_its_own_model_id():
    for module, client, expected in (
        (rerank_haiku, _FakeAnthropicClient(), settings.rerank_model),
        (openai_provider, _FakeOpenAIClient(), settings.rerank_luna_model),
    ):
        tracker = CostTracker()
        with patch.object(module, "_client", client):
            await pointwise.rerank_collection(
                [_cand()], "q", 4, tracker, module.PROVIDER, step="rerank_test",
            )
        assert module.PROVIDER.model_id == expected
        assert tracker.breakdown()["rerank_test"] > 0
