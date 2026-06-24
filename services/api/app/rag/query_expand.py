"""Query expansion — generates theological synonym phrasings to improve retrieval recall."""
import json
import logging
import re

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

_EXPAND_SYSTEM = (
    "You are a Catholic theology search assistant. Given a search query, generate "
    "exactly 2 alternative phrasings to improve retrieval across Catholic theological "
    "sources (Scripture, Catechism, Church Fathers, encyclicals, canon law).\n\n"
    "Generate one of each type:\n"
    "1. A SYNONYM variant — the same concept using traditional Catholic or archaic "
    "theological vocabulary. Examples: \"Holy Spirit\" → \"Holy Ghost\" or \"Paraclete\"; "
    "\"Eucharist\" → \"Blessed Sacrament\" or \"Holy Communion\"; "
    "\"salvation\" → \"redemption\" or \"justification\"; "
    "\"prayer\" → \"supplication\" or \"intercession\".\n"
    "2. A RELATED CONCEPT variant — a conceptually adjacent term that a source addressing "
    "this question would also discuss. Examples: a question about \"forgiveness\" → also "
    "expand to \"contrition\" or \"penance\"; a question about \"the soul\" → also expand "
    "to \"intellect and will\" or \"immortality\"; a question about \"Mary\" → also expand "
    "to \"intercession of the saints\" or \"Immaculate Conception\".\n\n"
    "Respond with ONLY a JSON array of exactly 2 strings. No explanation, no text before "
    "or after the array.\n"
    'Example: ["synonym variant", "related concept variant"]'
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
    """Return 2 alternative phrasings of *query*: a synonym variant and a related
    concept variant. On failure returns an empty list. Never raises.
    """
    if _client is None:
        logger.warning("query_expand client not initialized; skipping expansion")
        return []

    try:
        response = await _client.messages.create(
            model=settings.hyde_model,  # fast Haiku for cheap expansion
            max_tokens=200,
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
