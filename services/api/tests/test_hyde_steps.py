from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx2
import pytest

from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps import degradation, hyde_none, hyde_s25


@pytest.mark.asyncio
async def test_hyde_none_returns_empty_dict():
    tracker = CostTracker()
    result = await hyde_none.run("what is prayer?", ["bible", "catechism"], tracker)
    assert result == {}
    assert tracker.total_cost() == 0.0


@pytest.mark.asyncio
async def test_hyde_none_makes_no_llm_calls():
    tracker = CostTracker()
    with patch("anthropic.AsyncAnthropic") as mock_client:
        result = await hyde_none.run("test", ["bible"], tracker)
    mock_client.assert_not_called()
    assert result == {}


@pytest.mark.asyncio
async def test_generate_single_uses_current_anthropic_messages_signature():
    async def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            request=request,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [{"type": "text", "text": "A useful passage."}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 3, "output_tokens": 4},
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as http_client:
        client = anthropic.AsyncAnthropic(
            api_key="test-key",
            http_client=http_client,
            max_retries=0,
        )
        result = await hyde_s25._generate_single(
            client,
            "Write a passage.",
            "What is grace?",
            100,
        )

    assert result == "A useful passage."


@pytest.mark.asyncio
async def test_bible_genre_selector_wrong_cardinality_records_fallback():
    tracker = CostTracker()
    response = SimpleNamespace(
        content=[SimpleNamespace(text='["free", "psalms"]')],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    degradation.begin_degradation_accounting()

    with (
        patch("app.rag.steps.hyde_s25.get_key_for", return_value="key"),
        patch("app.rag.steps.hyde_s25.get_client", return_value=client),
        patch("app.rag.steps.hyde_s25.get_semaphore", return_value=MagicMock()),
        patch(
            "app.rag.steps.hyde_s25.generate_hyde_passages",
            new=AsyncMock(return_value=[]),
        ) as generate,
    ):
        result = await hyde_s25.run("grace", ["bible"], tracker)

    assert result == {}
    assert generate.await_args.kwargs["selected_genres"] == [
        "free", "nt-epistles", "psalms",
    ]
    assert degradation.event_dicts() == [{
        "stage": "hyde_genre_select",
        "reason": "invalid_response",
        "action": "defaults_used",
        "scope": "bible",
        "details": {"valid_genre_count": 2},
    }]
