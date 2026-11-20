"""Qdrant async client — lifecycle management."""
import logging
import time

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PayloadSchemaType

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None

_INDEX_TTL_SECONDS = 300.0
_searchable_indexed: bool | None = None
_searchable_checked_at = 0.0


def read_collection() -> str:
    """The collection or alias search reads (`QDRANT_READ_COLLECTION`, default `chunks`)."""
    return settings.qdrant_read_collection


def init_qdrant() -> None:
    global _client
    _client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=30,
    )
    logger.info(
        "Qdrant client initialised (url=%s, read collection=%s)",
        settings.qdrant_url, read_collection(),
    )


async def resolve_read_target(client: AsyncQdrantClient) -> str:
    """The collection `read_collection()` names: the alias's target, or the name itself
    when it is not an alias. Resolved through the alias list rather than by asking
    `get_collection` for the alias, so the answer does not depend on the server
    accepting an alias there."""
    name = read_collection()
    response = await client.get_aliases()
    for alias in response.aliases:
        if alias.alias_name == name:
            return alias.collection_name
    return name


async def searchable_indexed() -> bool:
    """Whether the read collection has the boolean payload index on `searchable`.

    Search filters on `searchable` only when it does (corpus cleanup 2.2b): production's
    Qdrant runs in strict mode, which refuses a filter on an unindexed field, so the
    filter before the index exists would fail every vector search. Every collection a
    publish builds has the index (`datapipeline/qdrant_schema.py`); today's `chunks`
    gains it in 2.2b's first ops step. Read at startup and again after five minutes. A
    failed check keeps the last answer (False before the first, which is today's
    unfiltered search) for another five minutes.
    """
    global _searchable_indexed, _searchable_checked_at
    if (_searchable_indexed is not None
            and time.monotonic() - _searchable_checked_at < _INDEX_TTL_SECONDS):
        return _searchable_indexed
    client = _client
    if client is None:
        return False
    try:
        info = await client.get_collection(await resolve_read_target(client))
    except Exception as exc:
        logger.warning("Qdrant searchable index check failed (%s)", exc.__class__.__name__)
        indexed = bool(_searchable_indexed)
    else:
        field = (info.payload_schema or {}).get("searchable")
        indexed = field is not None and field.data_type == PayloadSchemaType.BOOL
        if indexed != _searchable_indexed:
            logger.log(
                logging.INFO if indexed else logging.WARNING,
                "Qdrant %s: searchable filter %s", read_collection(),
                "on" if indexed else "off (no boolean payload index on searchable)",
            )
    _searchable_indexed, _searchable_checked_at = indexed, time.monotonic()
    return indexed


def forget_searchable_index() -> None:
    global _searchable_indexed
    _searchable_indexed = None


async def close_qdrant() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_qdrant_client() -> AsyncQdrantClient | None:
    return _client
