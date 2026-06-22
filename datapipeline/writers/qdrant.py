"""Qdrant client + helpers for the search pipeline."""
from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, HnswConfigDiff, MatchValue,
    PayloadSchemaType, PointStruct, VectorParams,
)

from config import settings

QDRANT_COLLECTION = "chunks"
EMBEDDING_DIMS = 1536


def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=120,
    )


def collection_filter(collection: str) -> Filter:
    return Filter(must=[FieldCondition(key="collection", match=MatchValue(value=collection))])


async def ensure_collection(client: AsyncQdrantClient) -> None:
    if await client.collection_exists(QDRANT_COLLECTION):
        return
    await client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIMS, distance=Distance.COSINE),
        hnsw_config=HnswConfigDiff(m=16, ef_construct=64),
    )
    await client.create_payload_index(
        collection_name=QDRANT_COLLECTION, field_name="collection",
        field_schema=PayloadSchemaType.KEYWORD,
    )


async def delete_collection_points(client: AsyncQdrantClient, collection: str) -> None:
    await client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=collection_filter(collection),
        wait=True,
    )


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
