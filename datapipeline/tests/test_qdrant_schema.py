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


@pytest.mark.asyncio
async def test_recreate_chunks_deletes_then_creates_named_and_sparse():
    c = _FakeClient(); c._exists.add("chunks")
    await qdrant_schema.recreate_chunks(c)
    assert "chunks" in c.deleted
    cfg = c.created["chunks"]
    assert "dense" in cfg["vectors_config"]
    assert cfg["vectors_config"]["dense"].size == 3072
    assert set(cfg["sparse_vectors_config"].keys()) == {"sparse_content", "sparse_annotation"}
    assert ("chunks", "collection") in c.indexes


@pytest.mark.asyncio
async def test_ensure_facets_and_questions_indexes():
    c = _FakeClient()
    await qdrant_schema.ensure_facets(c)
    await qdrant_schema.ensure_questions(c)
    assert c.created["facets"]["vectors_config"].size == 3072
    assert ("facets", "kind") in c.indexes
    assert ("facets", "grounding") in c.indexes
    assert ("facets", "kind_secondary") in c.indexes
    assert ("questions", "facet_kind") in c.indexes
    assert ("questions", "facet_grounding") in c.indexes
    assert ("questions", "facet_kind_secondary") in c.indexes
