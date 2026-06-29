"""Text embedding via OpenAI text-embedding-3-large."""
from __future__ import annotations

import logging

import openai

from app.config import settings
from app.rag.steps.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

_client: openai.AsyncOpenAI | None = None


def init_embed() -> None:
    global _client
    _client = openai.AsyncOpenAI(api_key=settings.openai_api_key)


async def close_embed() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def run(text: str, cost_tracker: CostTracker | None = None) -> list[float]:
    """Embed a single text string. Returns a list of floats."""
    if _client is None:
        raise RuntimeError("Embed client not initialized")
    response = await _client.embeddings.create(
        input=text,
        model=settings.embedding_model,
        dimensions=settings.embedding_dims,
    )
    if cost_tracker is not None and response.usage:
        cost_tracker.record("embed", settings.embedding_model,
                            input_tokens=response.usage.prompt_tokens, output_tokens=0)
    return response.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts (used by datapipeline, not pipeline steps)."""
    if _client is None:
        raise RuntimeError("Embed client not initialized")
    response = await _client.embeddings.create(
        input=texts,
        model=settings.embedding_model,
        dimensions=settings.embedding_dims,
    )
    return [r.embedding for r in sorted(response.data, key=lambda r: r.index)]
