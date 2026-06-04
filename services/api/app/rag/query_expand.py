"""Query expansion — generates theological synonym phrasings to improve retrieval recall."""
import json
import logging
import re

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

_EXPAND_SYSTEM = (
    "You are a Catholic theology search assistant. Given a search query, generate exactly 2 "
    "alternative phrasings that would help find relevant passages in theological sources "
    "(Scripture, Catechism, Church Fathers, encyclicals, canon law). "
    "Focus on theological synonyms and conceptually related terms — for example, "
    "\"salvation\" → \"redemption\" or \"justification\"; "
    "\"Holy Spirit\" → \"Paraclete\" or \"Holy Ghost\"; "
    "\"Eucharist\" → \"Holy Communion\" or \"the Blessed Sacrament\". "
    "Return ONLY a JSON array of exactly 2 strings, no explanation. "
    'Example: ["alternative phrasing 1", "alternative phrasing 2"]'
)


def init_query_expand() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_query_expand() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def expand_query(query: str) -> list[str]:
    """Return up to 2 alternative phrasings of *query* for multi-query retrieval.

    On failure returns an empty list — callers treat this as no expansion.
    Never raises.
    """
    if _client is None:
        logger.warning("query_expand client not initialized; skipping expansion")
        return []

    try:
        response = await _client.messages.create(
            model=settings.hyde_model,  # fast Haiku for cheap expansion
            max_tokens=150,
            system=_EXPAND_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        raw = response.content[0].text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            logger.warning("expand_query: no JSON array in response: %s", raw[:100])
            return []
        variants: list = json.loads(match.group(0))
        return [str(v) for v in variants if isinstance(v, str) and v.strip()][:2]
    except Exception as exc:
        logger.warning("expand_query failed: %s", exc)
        return []
