"""Create the Qdrant collections used by the data pipeline.

`create_chunks_collection` makes a new passage collection for a publish (2.2w): a stage
writes `chunks-<release>`, and the `chunks_live` alias is switched to it at the apply.
It never deletes or reshapes a collection, so no publish can empty the live one.
"""
from __future__ import annotations

from qdrant_client.models import Distance, HnswConfigDiff, PayloadSchemaType, VectorParams

from config import settings

FACETS = "facets"
QUESTIONS = "questions"

# Payload fields search filters on (D5), each with its index type.
CHUNK_PAYLOAD_INDEXES = (
    ("collection", PayloadSchemaType.KEYWORD),
    ("genre", PayloadSchemaType.KEYWORD),
    ("issuer", PayloadSchemaType.KEYWORD),
    ("document_id", PayloadSchemaType.KEYWORD),
    ("searchable", PayloadSchemaType.BOOL),
)


async def name_in_use(client, name: str) -> bool:
    """Whether `name` is a collection or an alias."""
    if await client.collection_exists(name):
        return True
    aliases = (await client.get_aliases()).aliases
    return any(a.alias_name == name for a in aliases)


async def create_chunks_collection(client, name: str) -> None:
    """Create the unnamed 1536-dim passage collection the application queries, with
    today's HNSW settings and the D5 payload indexes. Vectors stay in memory (4.0).

    Refuses with SystemExit when `name` is already a collection or an alias: a publish
    always writes a collection nobody reads yet."""
    if await name_in_use(client, name):
        raise SystemExit(f"REFUSING to create '{name}': a collection or alias of that "
                         "name exists")
    await client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=settings.EMBEDDING_DIMS, distance=Distance.COSINE, on_disk=False,
        ),
        hnsw_config=HnswConfigDiff(m=16, ef_construct=64),
    )
    for field, schema in CHUNK_PAYLOAD_INDEXES:
        await client.create_payload_index(
            collection_name=name, field_name=field, field_schema=schema)


async def ensure_facets(client) -> None:
    if await client.collection_exists(FACETS):
        return
    await client.create_collection(
        collection_name=FACETS,
        vectors_config=VectorParams(size=settings.EMBEDDING_DIMS, distance=Distance.COSINE))
    # "facet_id" (the stable f1/f2/... id) is indexed alongside the positional
    # "facet_index" so a re-embed's delete-by-chunk_id step, and any future
    # by-facet_id lookup, don't have to rely on array position alone.
    for field in ("collection", "chunk_id", "grounding", "kind", "kind_secondary", "facet_id"):
        await client.create_payload_index(
            collection_name=FACETS, field_name=field, field_schema=PayloadSchemaType.KEYWORD)


async def ensure_questions(client) -> None:
    if await client.collection_exists(QUESTIONS):
        return
    await client.create_collection(
        collection_name=QUESTIONS,
        vectors_config=VectorParams(size=settings.EMBEDDING_DIMS, distance=Distance.COSINE))
    for field in ("collection", "chunk_id", "facet_index", "facet_id", "facet_grounding",
                 "facet_kind", "facet_kind_secondary"):
        await client.create_payload_index(
            collection_name=QUESTIONS, field_name=field, field_schema=PayloadSchemaType.KEYWORD)
