"""Generates relevance explanations for retrieved chunks using OpenAI."""
import asyncio
import logging
from collections.abc import AsyncGenerator

import openai

from app.config import settings

logger = logging.getLogger(__name__)

_client: openai.AsyncOpenAI | None = None

_EXPLAIN_SYSTEM = (
    "You are explaining how a specific passage is relevant to a user's question. "
    "Be faithful to what the passage actually says — do not misrepresent or exaggerate its content. "
    "You may draw on theological knowledge and context to explain how the passage connects to the "
    "question, but the connection must be honest: do not claim the passage addresses something it does not.\n\n"
    "Length: 1 sentence if the passage is only tangentially related or addresses the question "
    "indirectly; 2-3 sentences if it directly addresses the question with substance. "
    "Err toward 1 sentence when in doubt.\n\n"
    "Lead with the theological point — state what the passage contributes, then how that applies "
    "to the question. Do not open with any framing device that describes the relationship instead "
    "of stating it: avoid 'This passage...', 'The passage states...', 'That connects to...', "
    "'This relates to...', 'In relation to the question...', or any variant. Say the thing directly.\n\n"
    "If the connection is weak or indirect, your single sentence must name the limitation plainly. "
    "Do not pad with general theological statements that are not grounded in what the passage "
    "actually says.\n\n"
    "Write plain prose. No markdown, no headings, no bullet points."
)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds — cumulative waits: 1+2+4 = 7s


def init_explain() -> None:
    global _client
    _client = openai.AsyncOpenAI(api_key=settings.openai_api_key)


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
            stream = await _client.chat.completions.create(
                model=settings.explain_openai_model,
                max_completion_tokens=220,
                messages=[
                    {"role": "system", "content": _EXPLAIN_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    tokens_started = True
                    yield chunk.choices[0].delta.content
            return  # stream completed successfully

        except openai.RateLimitError:
            if tokens_started or attempt == _MAX_RETRIES - 1:
                if not tokens_started:
                    logger.warning("stream_explanation rate-limited after %d retries", _MAX_RETRIES)
                    yield fallback
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
