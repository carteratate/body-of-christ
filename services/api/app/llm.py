from collections.abc import AsyncGenerator

import anthropic

from app.config import settings

_client: anthropic.AsyncAnthropic | None = None


def init_llm() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_llm() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def complete(messages: list[dict], system: str) -> str:
    """Send a conversation to the LLM and return the assistant reply.

    messages: full conversation history in [{role, content}] format.
    system:   system prompt (not logged, not stored).
    """
    if _client is None:
        raise RuntimeError("LLM client not initialized")

    response = await _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.llm_max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text


_TITLE_SYSTEM = (
    "You generate ultra-short conversation titles. "
    "Reply with 2–5 words only. No punctuation. No quotes. Nothing else."
)


async def generate_title(message: str) -> str:
    """Return a 2–5 word title for a conversation that starts with *message*.

    Uses the fastest/cheapest model — title quality matters less than latency.
    Raises on failure so callers can fall back gracefully.
    """
    if _client is None:
        raise RuntimeError("LLM client not initialized")

    response = await _client.messages.create(
        model=settings.anthropic_title_model,
        max_tokens=20,
        system=_TITLE_SYSTEM,
        messages=[{"role": "user", "content": message}],
    )
    raw = response.content[0].text.strip()
    # Strip stray quotes or trailing punctuation the model occasionally adds
    return raw.strip("\"'").rstrip(".")[:100]


async def stream_complete(
    messages: list[dict], system: str
) -> AsyncGenerator[str, None]:
    """Stream assistant reply tokens one chunk at a time."""
    if _client is None:
        raise RuntimeError("LLM client not initialized")

    async with _client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=settings.llm_max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
