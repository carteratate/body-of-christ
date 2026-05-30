"""HyDE (Hypothetical Document Embedding) passage generation."""
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

_HYDE_SYSTEM = (
    "You are a Catholic theology expert. Write a 2-3 sentence passage from an "
    "authoritative Catholic source (Scripture, Catechism, Church Fathers, or "
    "Magisterial documents) that would directly answer the following question. "
    "Write in the style of the source, not as a modern explanation."
)


def init_hyde() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_hyde() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def generate_hyde_passage(query: str) -> str | None:
    """Return a hypothetical passage or None if generation fails.

    On failure: logs the error, returns None (caller falls back to raw query).
    Never raises — failures are silent to the user.
    """
    if _client is None:
        logger.warning("HyDE client not initialized; skipping passage generation")
        return None

    try:
        response = await _client.messages.create(
            model=settings.hyde_model,
            max_tokens=200,
            system=_HYDE_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("HyDE passage generation failed: %s", exc)
        return None
