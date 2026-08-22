"""Create the V5 Qdrant collections: chunks (named dense + 2 sparse), facets, questions.

recreate_chunks() is a BREAKING change: it deletes and recreates `chunks` because
named sparse vectors cannot be added to an existing collection. All chunks are re-ingested.
"""
from __future__ import annotations

from qdrant_client.models import (
    Distance, HnswConfigDiff, PayloadSchemaType, SparseVectorParams, VectorParams,
)

from config import settings

CHUNKS = "chunks"
FACETS = "facets"
QUESTIONS = "questions"


async def recreate_chunks(client) -> None:
    """Create `chunks` in the shape `settings.QDRANT_FORMAT` selects.

    Both shapes are described here so the schema and the writer cannot disagree — a
    collection this creates must be one `writers/search_writer.build_point` can fill.
    """
    if await client.collection_exists(CHUNKS):
        await client.delete_collection(CHUNKS)
    dense = VectorParams(size=settings.EMBEDDING_DIMS, distance=Distance.COSINE)
    if settings.VECTOR_IS_NAMED:
        await client.create_collection(
            collection_name=CHUNKS,
            vectors_config={"dense": dense},
            sparse_vectors_config={
                "sparse_content": SparseVectorParams(),
                "sparse_annotation": SparseVectorParams(),
            },
            hnsw_config=HnswConfigDiff(m=16, ef_construct=64),
        )
    else:
        await client.create_collection(
            collection_name=CHUNKS,
            vectors_config=dense,
            hnsw_config=HnswConfigDiff(m=16, ef_construct=64),
        )
    await client.create_payload_index(
        collection_name=CHUNKS, field_name="collection", field_schema=PayloadSchemaType.KEYWORD)


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
