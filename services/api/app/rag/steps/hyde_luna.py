"""OpenAI client for Luna HyDE passage generation and Bible genre selection."""
from __future__ import annotations

import asyncio

import openai

from app.config import settings

_client: openai.AsyncOpenAI | None = None
_semaphore: asyncio.Semaphore | None = None

_BIBLE_GENRE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "bible_hyde_genres",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "genres": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "free", "psalms", "ot-wisdom", "ot-prophets",
                            "ot-stories", "nt-stories", "nt-epistles", "nt-teachings",
                        ],
                    },
                    "minItems": 4,
                    "maxItems": 4,
                },
            },
            "required": ["genres"],
            "additionalProperties": False,
        },
    },
}


def init() -> None:
    global _client, _semaphore
    _client = openai.AsyncOpenAI(
        api_key=settings.openai_api_key, timeout=45.0, max_retries=2,
    )
    _semaphore = asyncio.Semaphore(settings.hyde_luna_concurrency)


def is_ready() -> bool:
    return _client is not None and _semaphore is not None


async def close() -> None:
    global _client, _semaphore
    if _client is not None:
        await _client.close()
        _client = None
    _semaphore = None


async def generate(system: str, query: str, max_tokens: int) -> tuple[str, int, int]:
    """Return a complete passage and billed input/output token counts."""
    if _client is None or _semaphore is None:
        raise RuntimeError("Luna HyDE client not initialized")
    async with _semaphore:
        response = await _client.chat.completions.create(
            model=settings.hyde_luna_model,
            reasoning_effort="none",
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
        )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or getattr(choice.message, "refusal", None):
        raise ValueError(f"Luna HyDE incomplete: finish_reason={choice.finish_reason}")
    passage = (choice.message.content or "").strip()
    if not passage:
        raise ValueError("Luna HyDE returned an empty passage")
    usage = response.usage
    return (
        passage,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )


async def select_bible_genres(system: str, query: str) -> tuple[str, int, int]:
    """Return a schema-constrained JSON object and billed token counts."""
    if _client is None:
        raise RuntimeError("Luna HyDE client not initialized")
    response = await _client.chat.completions.create(
        model=settings.hyde_luna_model,
        reasoning_effort="none",
        max_completion_tokens=100,
        response_format=_BIBLE_GENRE_SCHEMA,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
    )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or getattr(choice.message, "refusal", None):
        raise ValueError(f"Luna genre selection incomplete: finish_reason={choice.finish_reason}")
    content = (choice.message.content or "").strip()
    if not content:
        raise ValueError("Luna genre selection returned empty JSON")
    usage = response.usage
    return (
        content,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )
