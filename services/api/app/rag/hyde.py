"""HyDE (Hypothetical Document Embedding) passage generation."""
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

# Fallback used when no collection is specified or collection is unknown.
_HYDE_SYSTEM_DEFAULT = (
    "You are a Catholic theology expert. Write a 2-3 sentence passage from an "
    "authoritative Catholic source (Scripture, Catechism, Church Fathers, or "
    "Magisterial documents) that would directly answer the following question. "
    "Write in the voice and style of the source — archaic and formal if appropriate. "
    "Do not use modern paraphrase. Do not add context not found in the source type."
)

# Per-collection prompts — each targets the prose style of that corpus so the
# resulting embedding lands closer to real chunks from that collection.
_COLLECTION_HYDE_PROMPTS: dict[str, str] = {
    "bible": (
        "Write 1-2 sentences in the style of a Bible verse or short Scripture passage "
        "(Old or New Testament) that would directly address the following question. "
        "Use formal, Scripture-like language. Return only the passage text, no labels or attribution."
    ),
    "catechism": (
        "Write 2-3 sentences in the style of the Catechism of the Catholic Church — "
        "doctrinal, systematic, clear — that would directly answer the following question. "
        "Return only the passage text, no labels or attribution."
    ),
    "encyclicals": (
        "Write 2-3 sentences in the style of a papal encyclical — authoritative, pastoral, "
        "formal prose with Latin-influenced cadence — that would directly address the following question. "
        "Return only the passage text, no labels or attribution."
    ),
    "church-fathers": (
        "Write 2-3 sentences in the style of an early Church Father (such as Augustine, "
        "Chrysostom, or Basil) — theological, exhortative, patristic — that would directly address "
        "the following question. Return only the passage text, no labels or attribution."
    ),
    "summa": (
        "Write 2-3 sentences in the scholastic style of Aquinas's Summa Theologiae — precise, "
        "structured, using phrases such as 'I answer that' or 'It must be said that' — that would "
        "directly address the following question. Return only the passage text, no labels or attribution."
    ),
    "councils": (
        "Write 2-3 sentences in the style of an ecumenical council decree or Vatican II document — "
        "authoritative, declarative, doctrinal — that would directly address the following question. "
        "Return only the passage text, no labels or attribution."
    ),
    "medieval": (
        "Write 2-3 sentences in the style of medieval Christian theological writing "
        "(such as Boethius, Anselm, or Bernard of Clairvaux) — contemplative, philosophical, "
        "devotional — that would directly address the following question. "
        "Return only the passage text, no labels or attribution."
    ),
    "canon-law": (
        "Write 1-2 sentences in the style of a canon law statute — prescriptive, legal, precise — "
        "that would directly address the following question. "
        "Return only the passage text, no labels or attribution."
    ),
}


def init_hyde() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_hyde() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def generate_hyde_passage(query: str, collection: str | None = None) -> str | None:
    """Return a hypothetical passage or None if generation fails.

    When *collection* is provided, uses a collection-specific style prompt so
    the generated passage embeds closer to real chunks from that corpus.
    Falls back to the generic prompt for unknown collections.

    On failure: logs the error, returns None (caller falls back to raw query vec).
    Never raises.
    """
    if _client is None:
        logger.warning("HyDE client not initialized; skipping passage generation")
        return None

    system = _COLLECTION_HYDE_PROMPTS.get(collection or "", _HYDE_SYSTEM_DEFAULT)

    try:
        response = await _client.messages.create(
            model=settings.hyde_model,
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": query}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("HyDE passage generation failed (collection=%s): %s", collection, exc)
        return None
