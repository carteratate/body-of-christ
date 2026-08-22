"""Qdrant client + helpers for the search pipeline."""
from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition, Filter, MatchValue, PointStruct,
)

from config import settings
from qdrant_schema import recreate_chunks

QDRANT_COLLECTION = "chunks"


def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=120,
    )


def collection_filter(collection: str) -> Filter:
    return Filter(must=[FieldCondition(key="collection", match=MatchValue(value=collection))])


async def ensure_collection(client: AsyncQdrantClient) -> None:
    if await client.collection_exists(QDRANT_COLLECTION):
        return
    await recreate_chunks(client)


async def delete_collection_points(client: AsyncQdrantClient, collection: str) -> None:
    await client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=collection_filter(collection),
        wait=True,
    )


async def prune_missing_points(client: AsyncQdrantClient, collection: str,
                               keep_ids: set[str]) -> int:
    """Delete this collection's points that the current build no longer produces.

    The Qdrant counterpart to `reader_writer.prune_missing_chunks`, and the reason it
    exists: `write_document` only ever upserts, so a re-chunk that renumbers or drops a
    passage leaves its old point behind forever. Those orphans stay searchable, and
    because the pipeline looks their ids up in Postgres to fill in position and role,
    a hit on one returns a row that is not there.

    Scans ids rather than trusting a count: a stale point is by definition one this
    build did not emit, which cannot be derived from totals alone.

    Returns the number deleted, so a caller can refuse a run that would remove far more
    than the rebuild explains.
    """
    stale: list[str] = []
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=collection_filter(collection),
            limit=1000, offset=offset, with_payload=False, with_vectors=False,
        )
        stale.extend(str(p.id) for p in points if str(p.id) not in keep_ids)
        if offset is None:
            break
    if stale:
        await client.delete(collection_name=QDRANT_COLLECTION,
                            points_selector=stale, wait=True)
    return len(stale)


async def upsert_points(client: AsyncQdrantClient, points: list[PointStruct]) -> None:
    if not points:
        return
    # Retry transient network/timeout errors (long runs make occasional blips likely).
    for attempt in range(4):
        try:
            await client.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)
            return
        except Exception:
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt)
