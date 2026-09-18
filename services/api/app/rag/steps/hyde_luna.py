"""OpenAI client for short Luna HyDE passage generation."""
from __future__ import annotations

import openai

from app.config import settings

_client: openai.AsyncOpenAI | None = None


def init() -> None:
    global _client
    _client = openai.AsyncOpenAI(
        api_key=settings.openai_api_key, timeout=45.0, max_retries=2,
    )


def is_ready() -> bool:
    return _client is not None


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def generate(system: str, query: str, max_tokens: int) -> tuple[str, int, int]:
    """Return a complete passage and billed input/output token counts."""
    if _client is None:
        raise RuntimeError("Luna HyDE client not initialized")
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
