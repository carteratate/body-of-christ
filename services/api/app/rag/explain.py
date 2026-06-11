"""Generates relevance explanations for retrieved chunks using Claude Haiku."""
import asyncio
import logging
from collections.abc import AsyncGenerator

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

_EXPLAIN_SYSTEM = (
    "You are explaining how a specific passage answers a user's question. "
    "You must base every sentence ONLY on what is explicitly written in the passage given — "
    "do not add theological knowledge, doctrine, or context not present in the passage itself. "
    "Write 2-3 sentences. Be direct: say what the passage says and how it addresses the question. "
    "If the passage is only tangentially related, say so honestly. "
    "Do not use markdown headings, bullet points, or any formatting. Write plain prose only."
)

_MAX_RETRIES = 4
_BASE_DELAY = 1.0  # seconds


def init_explain() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_explain() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def stream_explanation(
    chunk_content: str,
    chunk_reference: str | None,
    collection: str,
    query: str,
) -> AsyncGenerator[str, None]:
    """Async generator that yields text deltas from the explanation as they arrive.

    Retries on rate-limit errors before any tokens are emitted (can't un-yield).
    On unrecoverable failure yields the generic fallback as a single string.
    Never raises.
    """
    fallback = "Explanation unavailable — please read the passage directly."

    if _client is None:
        logger.warning("explain client not initialized")
        yield fallback
        return

    ref_label = chunk_reference or collection
    user_message = f"Question: {query}\n\nPassage ({ref_label}): {chunk_content}"

    for attempt in range(_MAX_RETRIES):
        tokens_started = False
        try:
            async with _client.messages.stream(
                model=settings.explain_model,
                max_tokens=220,
                system=_EXPLAIN_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for delta in stream.text_stream:
                    tokens_started = True
                    yield delta
            return  # stream completed successfully

        except anthropic.RateLimitError:
            if tokens_started or attempt == _MAX_RETRIES - 1:
                # Can't retry mid-stream, or out of retries
                if not tokens_started:
                    logger.warning("stream_explanation rate-limited after %d retries", _MAX_RETRIES)
                return
            delay = _BASE_DELAY * (2 ** attempt)
            logger.info(
                "stream_explanation rate-limited, retrying in %.1fs (attempt %d)",
                delay, attempt + 1,
            )
            await asyncio.sleep(delay)

        except Exception as exc:
            logger.warning("stream_explanation failed (%s): %s", exc.__class__.__name__, exc)
            if not tokens_started:
                yield fallback
            return

    yield fallback
