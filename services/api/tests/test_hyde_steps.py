import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx2
import pytest

from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps import degradation, hyde_luna, hyde_none, hyde_s25
from app.rag.constants import VALID_COLLECTIONS


def test_every_known_non_bible_collection_has_its_own_hyde_prompt():
    assert set(hyde_s25._COLLECTION_HYDE_PROMPTS) == VALID_COLLECTIONS - {"bible"}


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
            passage_provider="haiku",
        )

    assert result == "A useful passage."


@pytest.mark.asyncio
async def test_luna_hyde_uses_no_reasoning_and_keeps_prompt_roles():
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content="  A useful passage.  ", refusal=None),
        )],
        usage=SimpleNamespace(prompt_tokens=21, completion_tokens=37),
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    with patch.object(hyde_luna, "_client", client):
        passage, input_tokens, output_tokens = await hyde_luna.generate(
            "Write a passage.", "What is grace?", 300,
        )

    assert (passage, input_tokens, output_tokens) == ("A useful passage.", 21, 37)
    assert client.chat.completions.create.await_args.kwargs["reasoning_effort"] == "none"
    assert client.chat.completions.create.await_args.kwargs["messages"] == [
        {"role": "system", "content": "Write a passage."},
        {"role": "user", "content": "What is grace?"},
    ]


@pytest.mark.asyncio
async def test_luna_hyde_rejects_truncated_passage():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason="length",
            message=SimpleNamespace(content="An unfinished passage", refusal=None),
        )],
    ))

    with patch.object(hyde_luna, "_client", client):
        with pytest.raises(ValueError, match="finish_reason=length"):
            await hyde_luna.generate("system", "query", 300)


@pytest.mark.asyncio
async def test_luna_hyde_usage_is_recorded_under_luna_model():
    tracker = CostTracker()
    with patch.object(
        hyde_luna, "generate", new=AsyncMock(return_value=("A passage.", 21, 37)),
    ):
        passage = await hyde_s25._generate_single(
            MagicMock(), "system", "query", 300, tracker,
            passage_provider="luna",
        )

    assert passage == "A passage."
    assert tracker.breakdown()["hyde"] > 0


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
        "free", "nt-epistles", "psalms", "nt-teachings",
    ]
    assert degradation.event_dicts() == [{
        "stage": "hyde_genre_select",
        "reason": "invalid_response",
        "action": "defaults_used",
        "scope": "bible",
        "details": {"valid_genre_count": 2},
    }]


@pytest.mark.asyncio
async def test_focused_bible_generates_and_embeds_all_eight_genres_without_selector():
    client = MagicMock()
    client.messages.create = AsyncMock()
    generated_systems: list[str] = []

    async def generate(_client, system, _query, _max_tokens, **_kwargs):
        generated_systems.append(system)
        return system

    with (
        patch("app.rag.steps.hyde_s25.get_key_for", return_value="key"),
        patch("app.rag.steps.hyde_s25.get_client", return_value=client),
        patch("app.rag.steps.hyde_s25.get_semaphore", return_value=asyncio.Semaphore(4)),
        patch("app.rag.steps.hyde_s25._generate_single", new=generate),
        patch("app.rag.steps.hyde_s25.embed_run", new=AsyncMock(return_value=[0.1])) as embed,
    ):
        result = await hyde_s25.run(
            "grace", ["bible"], CostTracker(), all_bible_genres=True,
        )

    client.messages.create.assert_not_awaited()
    assert set(generated_systems) == {
        hyde_s25._HYDE_BIBLE_FREE_PROMPT,
        *hyde_s25._GENRE_HYDE_PROMPTS.values(),
    }
    assert len(result["bible"]) == 8
    assert embed.await_count == 8


@pytest.mark.asyncio
async def test_standard_bible_selects_four_genres():
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=SimpleNamespace(
        content=[SimpleNamespace(text='["free", "psalms", "nt-stories", "ot-wisdom"]')],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    ))
    generated_systems: list[str] = []

    async def generate(_client, system, _query, _max_tokens, **_kwargs):
        generated_systems.append(system)
        return system

    with (
        patch("app.rag.steps.hyde_s25.get_key_for", return_value="key"),
        patch("app.rag.steps.hyde_s25.get_client", return_value=client),
        patch("app.rag.steps.hyde_s25.get_semaphore", return_value=asyncio.Semaphore(4)),
        patch("app.rag.steps.hyde_s25._generate_single", new=generate),
        patch("app.rag.steps.hyde_s25.embed_run", new=AsyncMock(return_value=[0.1])) as embed,
    ):
        result = await hyde_s25.run("grace", ["bible"], CostTracker())

    client.messages.create.assert_awaited_once()
    assert generated_systems == [
        hyde_s25._HYDE_BIBLE_FREE_PROMPT,
        hyde_s25._HYDE_PSALMS_PROMPT,
        hyde_s25._HYDE_NT_STORIES_PROMPT,
        hyde_s25._HYDE_OT_WISDOM_PROMPT,
    ]
    assert len(result["bible"]) == 4
    assert embed.await_count == 4


@pytest.mark.asyncio
async def test_focused_bible_keeps_successful_genres_when_one_generation_fails():
    client = MagicMock()
    client.messages.create = AsyncMock()

    async def generate(_client, system, _query, _max_tokens, **_kwargs):
        return None if system == hyde_s25._HYDE_PSALMS_PROMPT else system

    with (
        patch("app.rag.steps.hyde_s25.get_key_for", return_value="key"),
        patch("app.rag.steps.hyde_s25.get_client", return_value=client),
        patch("app.rag.steps.hyde_s25.get_semaphore", return_value=asyncio.Semaphore(4)),
        patch("app.rag.steps.hyde_s25._generate_single", new=generate),
        patch("app.rag.steps.hyde_s25.embed_run", new=AsyncMock(return_value=[0.1])) as embed,
    ):
        result = await hyde_s25.run(
            "grace", ["bible"], CostTracker(), all_bible_genres=True,
        )

    client.messages.create.assert_not_awaited()
    assert len(result["bible"]) == 7
    assert embed.await_count == 7
