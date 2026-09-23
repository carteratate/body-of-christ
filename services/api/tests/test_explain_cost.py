from unittest.mock import patch

import pytest

from app.rag.steps import explain
from app.rag.steps.cost_tracker import CostTracker


class _Usage:
    prompt_tokens = 100
    completion_tokens = 20


class _Chunk:
    choices = []
    usage = _Usage()


class _Stream:
    def __aiter__(self):
        async def iterate():
            yield _Chunk()

        return iterate()


@pytest.mark.asyncio
async def test_explanation_stream_records_reported_token_cost():
    captured = {}
    tracker = CostTracker()

    class _Client:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    return _Stream()

    with patch.object(explain, "_client", _Client()):
        output = [
            delta async for delta in explain.stream(
                "Passage", "Gen 1:1", "bible", "creation",
                cost_tracker=tracker,
            )
        ]

    assert output == []
    assert captured["stream_options"] == {"include_usage": True}
    assert captured["model"] == "gpt-6-luna"
    # Reasoning off: it would bill as output and share the 220-token cap.
    assert captured["reasoning_effort"] == "none"
    assert tracker.breakdown()["explain"] == pytest.approx((100 * 0.10 + 20 * 0.50) / 1e6)
