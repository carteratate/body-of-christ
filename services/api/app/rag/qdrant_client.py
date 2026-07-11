"""Qdrant async client — lifecycle management."""
import logging

from qdrant_client import AsyncQdrantClient

from app.config import settings

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "chunks"

_client: AsyncQdrantClient | None = None


def init_qdrant() -> None:
    global _client
    _client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=30,
    )
    logger.info("Qdrant client initialised (url=%s)", settings.qdrant_url)


async def close_qdrant() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_qdrant_client() -> AsyncQdrantClient | None:
    return _client
