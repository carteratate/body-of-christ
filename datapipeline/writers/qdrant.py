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
    """Create `chunks` if absent, and refuse to write to one this writer cannot fill.

    The check exists because its absence is what let the writer and the corpus drift
    apart unnoticed: the writer was retargeted at the V5 schema (3072-dim named vectors,
    per `qdrant_schema.py`) while the deployed collection stayed at 1536 unnamed, and
    nothing compared them until an ingest was attempted.

    A mismatch is refused rather than repaired. Reshaping a live collection means
    deleting every vector in it, which is not something an ingest run should decide.
    """
    if not await client.collection_exists(QDRANT_COLLECTION):
        await recreate_chunks(client)
        return

    info = await client.get_collection(QDRANT_COLLECTION)
    params = info.config.params.vectors
    named = isinstance(params, dict)
    size = (next(iter(params.values())).size if named else params.size)
    writer_named = settings.VECTOR_IS_NAMED

    if named != writer_named or size != settings.EMBEDDING_DIMS:
        raise SystemExit(
            f"REFUSING to write to '{QDRANT_COLLECTION}': it holds "
            f"{'named' if named else 'unnamed'} {size}-dim vectors, but this writer "
            f"produces {'named' if writer_named else 'unnamed'} "
            f"{settings.EMBEDDING_DIMS}-dim vectors (QDRANT_FORMAT="
            f"{settings.QDRANT_FORMAT!r}). Reshaping the collection would "
            f"delete every vector in it — do that deliberately, not as a side effect of "
            f"an ingest."
        )


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
