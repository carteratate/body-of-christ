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

    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(8)),
    ):
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

    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(8)),
    ):
        with pytest.raises(ValueError, match="finish_reason=length"):
            await hyde_luna.generate("system", "query", 300)


@pytest.mark.asyncio
async def test_luna_hyde_limits_concurrent_openai_calls():
    active = 0
    peak = 0

    async def create(**_kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="A passage.", refusal=None),
            )],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)
    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(1)),
    ):
        await asyncio.gather(*[
            hyde_luna.generate("system", "query", 100) for _ in range(3)
        ])

    assert peak == 1


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
@pytest.mark.parametrize("collection", ["bible", "catechism"])
async def test_luna_passages_do_not_wait_for_anthropic_semaphore(collection):
    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()
    with patch.object(
        hyde_s25, "_generate_single", new=AsyncMock(return_value="A passage."),
    ) as generate:
        try:
            passages = await asyncio.wait_for(
                hyde_s25.generate_hyde_passages(
                    "What is grace?", collection, MagicMock(), semaphore,
                    selected_genres=["free"] if collection == "bible" else None,
                    passage_provider="luna",
                ),
                timeout=0.1,
            )
        finally:
            semaphore.release()

    assert passages == ["A passage."]
    assert generate.await_args.kwargs["passage_provider"] == "luna"


@pytest.mark.asyncio
async def test_luna_genre_selector_uses_strict_json_schema():
    content = '{"genres":["free","psalms","nt-epistles","nt-teachings"]}'
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=content, refusal=None),
        )],
        usage=SimpleNamespace(prompt_tokens=500, completion_tokens=25),
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", asyncio.Semaphore(8)),
    ):
        result = await hyde_luna.select_bible_genres("Choose genres", "What is grace?")

    assert result == (content, 500, 25)
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["response_format"]["type"] == "json_schema"
    schema_config = kwargs["response_format"]["json_schema"]
    assert schema_config["strict"] is True
    schema = schema_config["schema"]
    assert schema["required"] == ["genres"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["genres"]["minItems"] == 4
    assert schema["properties"]["genres"]["maxItems"] == 4
    assert set(schema["properties"]["genres"]["items"]["enum"]) == (
        hyde_s25._BIBLE_VALID_GENRES
    )


@pytest.mark.asyncio
async def test_luna_genre_selector_shares_openai_limit():
    content = '{"genres":["free","psalms","nt-epistles","nt-teachings"]}'
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=content, refusal=None),
        )],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    ))
    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()
    with (
        patch.object(hyde_luna, "_client", client),
        patch.object(hyde_luna, "_semaphore", semaphore),
    ):
        task = asyncio.create_task(hyde_luna.select_bible_genres("system", "query"))
        try:
            await asyncio.sleep(0.01)
            client.chat.completions.create.assert_not_awaited()
        finally:
            semaphore.release()
        assert (await task)[0] == content


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
        patch.object(hyde_s25.settings, "hyde_genre_provider", "haiku"),
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
async def test_haiku_genre_selector_remains_available_for_rollback():
    tracker = CostTracker()
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=SimpleNamespace(
        content=[SimpleNamespace(text='["free","psalms","nt-stories","ot-wisdom"]')],
        usage=SimpleNamespace(input_tokens=500, output_tokens=25),
    ))

    with patch.object(hyde_s25.settings, "hyde_genre_provider", "haiku"):
        selected = await hyde_s25.choose_bible_hyde_genres(
            "What is grace?", client, cost_tracker=tracker,
        )

    assert selected == ["free", "psalms", "nt-stories", "ot-wisdom"]
    assert tracker.breakdown()["hyde_genre_select"] > 0
    kwargs = client.messages.create.await_args.kwargs
    assert kwargs["system"] == hyde_s25._BIBLE_GENRE_SELECT_HAIKU_SYSTEM
    assert "JSON array" in kwargs["system"]


@pytest.mark.asyncio
async def test_luna_genre_selector_duplicate_genres_use_defaults(caplog):
    degradation.begin_degradation_accounting()
    tracker = CostTracker()
    with (
        patch.object(hyde_s25.settings, "hyde_genre_provider", "luna"),
        patch.object(hyde_luna, "select_bible_genres", new=AsyncMock(
            return_value=(
                '{"genres":["free","free","psalms","nt-epistles"]}',
                500, 25,
            ),
        )),
    ):
        selected = await hyde_s25.choose_bible_hyde_genres(
            "What is grace?", MagicMock(), cost_tracker=tracker,
        )

    assert selected == hyde_s25._BIBLE_DEFAULT_GENRES
    assert "expected 4 valid genres, got 3; using defaults" in caplog.text
    assert tracker.breakdown()["hyde_genre_select"] > 0
    assert degradation.event_dicts() == [{
        "stage": "hyde_genre_select",
        "reason": "invalid_response",
        "action": "defaults_used",
        "scope": "bible",
        "details": {"valid_genre_count": 3},
    }]


@pytest.mark.asyncio
async def test_luna_genre_selector_failure_uses_defaults():
    degradation.begin_degradation_accounting()
    with (
        patch.object(hyde_s25.settings, "hyde_genre_provider", "luna"),
        patch.object(hyde_luna, "select_bible_genres", new=AsyncMock(
            side_effect=RuntimeError("temporary failure"),
        )),
    ):
        selected = await hyde_s25.choose_bible_hyde_genres(
            "What is grace?", MagicMock(),
        )

    assert selected == hyde_s25._BIBLE_DEFAULT_GENRES
    assert degradation.event_dicts() == [{
        "stage": "hyde_genre_select",
        "reason": "RuntimeError",
        "action": "defaults_used",
        "scope": "bible",
        "details": None,
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
        patch.object(hyde_luna, "select_bible_genres", new=AsyncMock()) as select,
        patch("app.rag.steps.hyde_s25.embed_run", new=AsyncMock(return_value=[0.1])) as embed,
    ):
        result = await hyde_s25.run(
            "grace", ["bible"], CostTracker(), all_bible_genres=True,
        )

    client.messages.create.assert_not_awaited()
    select.assert_not_awaited()
    assert set(generated_systems) == {
        hyde_s25._HYDE_BIBLE_FREE_PROMPT,
        *hyde_s25._GENRE_HYDE_PROMPTS.values(),
    }
    assert len(result["bible"]) == 8
    assert embed.await_count == 8


@pytest.mark.asyncio
async def test_standard_bible_selects_four_genres_with_luna():
    client = MagicMock()
    client.messages.create = AsyncMock()
    generated_systems: list[str] = []

    async def generate(_client, system, _query, _max_tokens, **_kwargs):
        generated_systems.append(system)
        return system

    with (
        patch.object(hyde_s25.settings, "hyde_genre_provider", "luna"),
        patch("app.rag.steps.hyde_s25.get_key_for", return_value="key"),
        patch("app.rag.steps.hyde_s25.get_client", return_value=client),
        patch("app.rag.steps.hyde_s25.get_semaphore", return_value=asyncio.Semaphore(4)),
        patch.object(hyde_luna, "select_bible_genres", new=AsyncMock(
            return_value=(
                '{"genres":["free","psalms","nt-stories","ot-wisdom"]}',
                500, 25,
            ),
        )) as select,
        patch("app.rag.steps.hyde_s25._generate_single", new=generate),
        patch("app.rag.steps.hyde_s25.embed_run", new=AsyncMock(return_value=[0.1])) as embed,
    ):
        result = await hyde_s25.run("grace", ["bible"], CostTracker())

    client.messages.create.assert_not_awaited()
    select.assert_awaited_once()
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
