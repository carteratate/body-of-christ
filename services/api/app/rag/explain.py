"""Generates relevance explanations for retrieved chunks using Claude Haiku."""
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

_EXPLAIN_SYSTEM = (
    "You are a Catholic theology guide. Explain in 2-3 sentences how the given passage speaks "
    "to the user's question. Be specific to this passage — reference its actual content, not "
    "generic theology. Do not begin with 'This passage' or similar formulaic openings."
)


def init_explain() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_explain() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def generate_explanation(
    chunk_content: str,
    chunk_reference: str | None,
    collection: str,
    query: str,
) -> str:
    """Return a 2-3 sentence explanation of why this passage is relevant to the query.

    On failure: returns a generic fallback string. Never raises.
    """
    if _client is None:
        logger.warning("explain client not initialized; returning generic fallback")
        return f"This passage from {collection} relates to your question."

    ref_label = chunk_reference or collection
    user_message = f"Question: {query}\n\nPassage ({ref_label}): {chunk_content[:500]}"

    try:
        response = await _client.messages.create(
            model=settings.explain_model,
            max_tokens=150,
            system=_EXPLAIN_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("generate_explanation failed: %s", exc)
        return f"This passage from {collection} relates to your question."
