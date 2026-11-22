"""Corpus cleanup 2.2b: search reads Qdrant through the alias `chunks_live`.

Builds `chunks` with three points (one marked `searchable = false`, one without the
field, one marked `searchable = true`), points `chunks_live` at it, and checks that vector
search, the near-duplicate vector fetch and the health check all work through the alias,
and that the `must_not` filter hides only the explicitly unsearchable point.

Runs against qdrant-client's in-process local mode always, and against a real server
when `QDRANT_TEST_URL` is set (marked `qdrant_live`; run it at production's server
version). The collection names are prefixed so a shared test server is left alone.
"""
import os
import uuid
from unittest.mock import patch

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    CreateAlias, CreateAliasOperation, DeleteAlias, DeleteAliasOperation, Distance,
    PayloadSchemaType, PointStruct, StrictModeConfig, VectorParams,
)

from app import main
from app.config import settings
from app.rag import dedup, qdrant_client
from app.rag.collection_scope import CollectionScope
from app.rag.steps import retrieve_vector
from app.rag.steps.types import RankedChunk

UNSEARCHABLE = str(uuid.UUID(int=1))
NO_FIELD = str(uuid.UUID(int=2))
SEARCHABLE = str(uuid.UUID(int=3))
VECTOR = [1.0, 0.0, 0.0, 0.0]


def _payload(position: int, **extra) -> dict:
    return {"collection": "bible", "document_id": "d1", "document_title": "Genesis",
            "content": f"verse {position}", **extra}


@pytest.fixture(params=[
    pytest.param("local", id="local"),
    pytest.param("server", id="server", marks=[
        pytest.mark.qdrant_live,
        pytest.mark.skipif(not os.environ.get("QDRANT_TEST_URL"),
                           reason="QDRANT_TEST_URL is not set"),
    ]),
])
async def qdrant(request, monkeypatch):
    if request.param == "local":
        client = AsyncQdrantClient(location=":memory:")
        prefix = ""
    else:
        client = AsyncQdrantClient(url=os.environ["QDRANT_TEST_URL"],
                                   api_key=os.environ.get("QDRANT_TEST_API_KEY"))
        prefix = f"test-2-2b-{uuid.uuid4().hex[:8]}-"
    collection, alias = f"{prefix}chunks", f"{prefix}chunks_live"
    await client.create_collection(
        collection, vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    if request.param == "server":  # local mode has no payload indexes
        await client.create_payload_index(collection, "collection", PayloadSchemaType.KEYWORD)
        await client.create_payload_index(collection, "searchable", PayloadSchemaType.BOOL)
    await client.upsert(collection, points=[
        PointStruct(id=UNSEARCHABLE, vector=VECTOR, payload=_payload(1, searchable=False)),
        PointStruct(id=NO_FIELD, vector=VECTOR, payload=_payload(2)),
        PointStruct(id=SEARCHABLE, vector=VECTOR, payload=_payload(3, searchable=True)),
    ], wait=True)
    await client.update_collection_aliases([CreateAliasOperation(
        create_alias=CreateAlias(collection_name=collection, alias_name=alias),
    )])
    monkeypatch.setattr(settings, "qdrant_read_collection", alias)
    if request.param == "local":  # local mode keeps no payload indexes to find
        monkeypatch.setattr(qdrant_client, "_searchable_indexed", True)
        monkeypatch.setattr(qdrant_client, "_searchable_checked_at", float("inf"))
    with (
        patch.object(retrieve_vector, "get_qdrant_client", return_value=client),
        patch.object(dedup, "get_qdrant_client", return_value=client),
        patch.object(main, "get_qdrant_client", return_value=client),
        patch.object(main, "get_pool", return_value=None),
        patch.object(qdrant_client, "_client", client),
    ):
        yield client, collection, alias
    await client.update_collection_aliases([DeleteAliasOperation(
        delete_alias=DeleteAlias(alias_name=alias),
    )])
    await client.delete_collection(collection)
    await client.close()


async def test_vector_search_through_the_alias_hides_only_unsearchable(qdrant):
    rows = await retrieve_vector._search_vector(CollectionScope("bible"), VECTOR, limit=10, label="query")
    assert {row["id"] for row in rows} == {NO_FIELD, SEARCHABLE}


async def test_retrieve_with_vectors_works_through_the_alias(qdrant):
    client, _, alias = qdrant
    points = await client.retrieve(alias, ids=[NO_FIELD, SEARCHABLE], with_vectors=True)
    assert {str(p.id) for p in points} == {NO_FIELD, SEARCHABLE}
    assert all(p.vector is not None for p in points)


async def test_near_duplicates_are_found_through_the_alias(qdrant):
    """Two adjacent passages with the same vector: the lower scorer is dropped, which
    only happens when the vectors were fetched through the alias."""
    def chunk(chunk_id, score, position):
        return RankedChunk(chunk_id=chunk_id, content="v", reference=None,
                           collection="bible", document_id="d1", document_title="Genesis",
                           author=None, reranker_score=score, position=position,
                           chapter_key=f"ch{position}")

    kept = await dedup.apply_dedup([chunk(NO_FIELD, 0.9, 1), chunk(SEARCHABLE, 0.8, 2)])
    assert [c.chunk_id for c in kept] == [NO_FIELD]


async def test_health_resolves_the_alias_to_its_collection(qdrant):
    _, collection, alias = qdrant
    live, read = await main._live_search_readiness()
    assert live["qdrant"] is True
    assert read == {"qdrant_read": alias, "qdrant_target": collection,
                    "qdrant_searchable_filter": True}


@pytest.mark.qdrant_live
@pytest.mark.skipif(not os.environ.get("QDRANT_TEST_URL"), reason="QDRANT_TEST_URL is not set")
async def test_strict_mode_needs_the_index_and_the_check_finds_it():
    """The reason search waits for the index: a server in strict mode refuses a filter
    on an unindexed field. Run against a server configured like production."""
    client = AsyncQdrantClient(url=os.environ["QDRANT_TEST_URL"],
                               api_key=os.environ.get("QDRANT_TEST_API_KEY"))
    name = f"test-2-2b-{uuid.uuid4().hex[:8]}-strict"
    try:
        await client.create_collection(
            name, vectors_config=VectorParams(size=4, distance=Distance.COSINE),
            strict_mode_config=StrictModeConfig(enabled=True,
                                                unindexed_filtering_retrieve=False),
        )
        await client.create_payload_index(name, "collection", PayloadSchemaType.KEYWORD)
        await client.upsert(name, points=[
            PointStruct(id=NO_FIELD, vector=VECTOR, payload=_payload(2))], wait=True)
        with (
            patch.object(retrieve_vector, "get_qdrant_client", return_value=client),
            patch.object(qdrant_client, "_client", client),
            patch.object(settings, "qdrant_read_collection", name),
        ):
            assert await qdrant_client.searchable_indexed() is False
            assert len(await retrieve_vector._search_vector(
                CollectionScope("bible"), VECTOR, limit=10, label="query")) == 1
            await client.create_payload_index(name, "searchable", PayloadSchemaType.BOOL)
            qdrant_client.forget_searchable_index()
            assert await qdrant_client.searchable_indexed() is True
            assert len(await retrieve_vector._search_vector(
                CollectionScope("bible"), VECTOR, limit=10, label="query")) == 1
    finally:
        await client.delete_collection(name)
        await client.close()


async def test_get_collection_accepts_the_alias(qdrant):
    """Recorded for the spec's open question; the health check does not rely on it."""
    client, _, alias = qdrant
    info = await client.get_collection(alias)
    assert info.points_count == 3
