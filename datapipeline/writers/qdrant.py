"""Qdrant client + helpers for the search pipeline.

A publish (2.2w) writes only a collection no alias points at, `chunks-<release>`, and
every function here takes the collection name. Nothing in this module deletes a point
from, or reshapes, the collection the `chunks_live` alias targets.
"""
from __future__ import annotations

import asyncio
from typing import Any, cast

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition, Filter, MatchValue, PointStruct,
)

from config import settings

# The collection users searched before the alias existed. Only the refusals name it:
# nothing writes here by default, and no other module may name it
# (test_no_writer_names_the_chunks_collection).
PRE_ALIAS_COLLECTION = "chunks"

_SCROLL = 256


def write_collection() -> str:
    """The collection a V5 stage or a repair script writes. It must be named, so none of
    them can fall back to the collection users search."""
    name = settings.QDRANT_WRITE_COLLECTION
    if not name:
        raise SystemExit("REFUSING: set QDRANT_WRITE_COLLECTION to the Qdrant collection "
                         "to write. It has no default")
    return name


def scan_collection() -> str:
    """The collection a dry-running repair script reads: the one it would write when
    that is named, otherwise the one users search."""
    return settings.QDRANT_WRITE_COLLECTION or settings.QDRANT_LIVE_ALIAS


def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=120,
    )


def collection_filter(collection: str) -> Filter:
    return Filter(must=[FieldCondition(key="collection", match=MatchValue(value=collection))])


async def alias_target(client: AsyncQdrantClient, alias: str) -> str | None:
    """The collection `alias` points at, or None when there is no such alias."""
    for a in (await client.get_aliases()).aliases:
        if a.alias_name == alias:
            return a.collection_name
    return None


async def vector_size(client: AsyncQdrantClient, name: str) -> tuple[bool, int]:
    """(named, size) of a collection's vectors."""
    params = (await client.get_collection(name)).config.params.vectors
    if isinstance(params, dict):
        return True, next(iter(params.values())).size
    return False, cast(Any, params).size


async def check_vectors(client: AsyncQdrantClient, name: str) -> None:
    """Refuse to write to a collection this writer cannot fill, or one that is missing.

    A mismatch is refused rather than repaired: reshaping a collection deletes every
    vector in it, which no write should decide as a side effect. A publish creates its
    own collection (`qdrant_schema.create_chunks_collection`); nothing here creates one.
    """
    if not await client.collection_exists(name):
        raise SystemExit(f"REFUSING to write to '{name}': no such collection")
    named, size = await vector_size(client, name)
    if named or size != settings.EMBEDDING_DIMS:
        raise SystemExit(
            f"REFUSING to write to '{name}': it holds {'named' if named else 'unnamed'} "
            f"{size}-dim vectors, but this writer produces unnamed "
            f"{settings.EMBEDDING_DIMS}-dim vectors. Reshaping the collection would delete "
            "every vector in it; do that deliberately, not as a side effect of a write.")


async def collection_point_ids(client: AsyncQdrantClient, name: str,
                               collection: str) -> set[str]:
    """Every point ID in collection `name` whose payload `collection` is `collection`."""
    point_ids: set[str] = set()
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=name, scroll_filter=collection_filter(collection),
            limit=1000, offset=offset, with_payload=False, with_vectors=False,
        )
        point_ids.update(str(point.id) for point in points)
        if offset is None:
            return point_ids


async def count_points(client: AsyncQdrantClient, name: str,
                       collection: str | None = None) -> int:
    result = await client.count(
        collection_name=name,
        count_filter=collection_filter(collection) if collection else None, exact=True)
    return result.count


async def retrieve(client: AsyncQdrantClient, name: str, ids: list[str],
                   *, with_vectors: bool = True) -> dict[str, Any]:
    """The points of `ids` that exist in `name`, by ID, with payloads (and vectors)."""
    out = {}
    for start in range(0, len(ids), _SCROLL):
        points = await client.retrieve(collection_name=name, ids=ids[start:start + _SCROLL],
                                       with_payload=True, with_vectors=with_vectors)
        out.update({str(p.id): p for p in points})
    return out


async def scroll_points(client: AsyncQdrantClient, name: str, collection: str | None = None,
                        *, with_vectors: bool = False):
    """Yield every point of `name` (one payload collection when given) in pages."""
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=name,
            scroll_filter=collection_filter(collection) if collection else None,
            limit=_SCROLL, offset=offset, with_payload=True, with_vectors=with_vectors,
        )
        if points:
            yield points
        if offset is None:
            return


async def copy_points(client: AsyncQdrantClient, source: str, target: str,
                      collection: str) -> int:
    """Copy one payload collection's points, vectors and payloads, from `source` into
    `target`, and return how many. Reads `source` only."""
    copied = 0
    async for points in scroll_points(client, source, collection, with_vectors=True):
        await upsert_points(client, target, [
            PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points])
        copied += len(points)
    return copied


async def clear_staged_points(client: AsyncQdrantClient, name: str, collection: str,
                              *, alias: str) -> None:
    """Remove one payload collection's points from a publish's own collection before it
    is staged again. Refuses when `name` is what `alias` targets, or is the pre-alias
    `chunks` collection the API read before the alias, so it can only ever touch a
    collection users do not search."""
    if name == PRE_ALIAS_COLLECTION or name == await alias_target(client, alias):
        raise SystemExit(f"REFUSING to remove points from '{name}': users search it")
    await client.delete(collection_name=name, points_selector=collection_filter(collection),
                        wait=True)


async def upsert_points(client: AsyncQdrantClient, name: str,
                        points: list[PointStruct]) -> None:
    if not points:
        return
    # Retry transient network/timeout errors (long runs make occasional blips likely).
    for attempt in range(4):
        try:
            await client.upsert(collection_name=name, points=points, wait=True)
            return
        except Exception:
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt)
