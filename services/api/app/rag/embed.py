"""Text embedding via OpenAI text-embedding-3-large."""
import logging

import openai

from app.config import settings

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


async def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a list of 1536 floats.

    Raises RuntimeError if the client is not initialized.
    Raises on API failure (let callers handle).
    """
    if _client is None:
        raise RuntimeError("Embed client not initialized")

    response = await _client.embeddings.create(
        input=text,
        model=settings.embedding_model,
        dimensions=settings.embedding_dims,
    )
    return response.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a single API call (batch).

    Returns list of vectors in same order as input.
    Raises RuntimeError if the client is not initialized.
    Raises on API failure (let callers handle).
    """
    if _client is None:
        raise RuntimeError("Embed client not initialized")

    response = await _client.embeddings.create(
        input=texts,
        model=settings.embedding_model,
        dimensions=settings.embedding_dims,
    )
    return [r.embedding for r in response.data]
