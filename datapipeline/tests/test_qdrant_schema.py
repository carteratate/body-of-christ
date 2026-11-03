import pytest
import qdrant_schema


class _FakeClient:
    def __init__(self):
        self.created = {}
        self.deleted = []
        self.indexes = []
        self._exists = set()
    async def collection_exists(self, collection_name):
        return collection_name in self._exists
    async def delete_collection(self, collection_name):
        self.deleted.append(collection_name)
        self._exists.discard(collection_name)
    async def create_collection(self, collection_name, **kwargs):
        self.created[collection_name] = kwargs
        self._exists.add(collection_name)
    async def create_payload_index(self, collection_name, field_name, field_schema):
        self.indexes.append((collection_name, field_name))


async def test_create_chunks_collection_makes_a_collection_the_writer_can_fill():
    """The schema and `search_writer.build_point` must agree: a collection created here
    that the writer cannot write to is unusable, which is the state the pipeline was in
    while it emitted V5 against a live collection."""
    from config import settings
    from qdrant_client import AsyncQdrantClient

    c = AsyncQdrantClient(location=":memory:")
    indexes = {}

    async def create_payload_index(collection_name, field_name, field_schema):
        indexes[field_name] = field_schema.value     # local mode ignores payload indexes
    c.create_payload_index = create_payload_index
    await qdrant_schema.create_chunks_collection(c, "chunks-r1")
    info = await c.get_collection("chunks-r1")
    assert info.config.params.vectors.size == settings.EMBEDDING_DIMS == 1536
    assert not info.config.params.sparse_vectors      # live has no sparse vectors
    assert indexes == {"collection": "keyword", "genre": "keyword", "issuer": "keyword",
                       "document_id": "keyword", "searchable": "bool"}


async def test_create_collection_refuses_existing_name_and_alias():
    from qdrant_client import AsyncQdrantClient, models

    c = AsyncQdrantClient(location=":memory:")
    await qdrant_schema.create_chunks_collection(c, "chunks")
    with pytest.raises(SystemExit, match="REFUSING"):
        await qdrant_schema.create_chunks_collection(c, "chunks")
    await c.update_collection_aliases(change_aliases_operations=[models.CreateAliasOperation(
        create_alias=models.CreateAlias(collection_name="chunks", alias_name="chunks_live"))])
    with pytest.raises(SystemExit, match="REFUSING"):
        await qdrant_schema.create_chunks_collection(c, "chunks_live")


@pytest.mark.asyncio
async def test_ensure_facets_and_questions_indexes():
    c = _FakeClient()
    await qdrant_schema.ensure_facets(c)
    await qdrant_schema.ensure_questions(c)
    # Facets and questions are compared against the same query vectors as `chunks`, so
    # they follow the same width.
    assert c.created["facets"]["vectors_config"].size == 1536
    assert ("facets", "kind") in c.indexes
    assert ("facets", "grounding") in c.indexes
    assert ("facets", "kind_secondary") in c.indexes
    assert ("facets", "facet_id") in c.indexes
    assert ("questions", "facet_kind") in c.indexes
    assert ("questions", "facet_grounding") in c.indexes
    assert ("questions", "facet_kind_secondary") in c.indexes
    assert ("questions", "facet_id") in c.indexes
