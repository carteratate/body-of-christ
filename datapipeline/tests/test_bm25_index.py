import asyncio
import json

import pytest
from stages.bm25_index import encode, build_sparse_update, index_collection


class _Sparse:
    def __init__(self, indices, values): self.indices = indices; self.values = values


class _Model:
    def embed(self, texts):
        return [_Sparse([1, 5, 9], [0.2, 0.5, 0.1]) for _ in texts]


class _RecordingModel:
    """Like _Model, but remembers exactly what text it was asked to embed, so tests
    can assert on the post-json.loads() prose rather than just checking for crashes."""
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.extend(texts)
        return [_Sparse([1, 5, 9], [0.2, 0.5, 0.1]) for _ in texts]


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        return self._rows


class _FakeQdrant:
    def __init__(self):
        self.calls = []

    async def update_vectors(self, collection_name, points, wait=True):
        self.calls.append((collection_name, points))


def test_encode_returns_indices_and_values():
    idx, vals = encode(_Model(), "the eucharist")
    assert idx == [1, 5, 9] and vals == [0.2, 0.5, 0.1]


def test_build_sparse_update_names_both_vectors():
    upd = build_sparse_update("cid1", [1, 2], [0.1, 0.2], [3, 4], [0.3, 0.4])
    assert upd["id"] == "cid1"
    assert set(upd["vector"].keys()) == {"sparse_content", "sparse_annotation"}
    assert upd["vector"]["sparse_content"].indices == [1, 2]
    assert upd["vector"]["sparse_annotation"].values == [0.3, 0.4]


def test_index_collection_decodes_jsonb_annotation_before_encoding():
    # r["annotation"] as returned by asyncpg for a jsonb column is the raw JSON-encoded
    # text (quotes + literal \n escapes), since no set_type_codec is registered in this
    # codebase. index_collection must json.loads() it before annotation_prose() strips
    # the [KIND | grounding]: label — otherwise the sparse annotation embedding would
    # be built from mangled text instead of clean prose.
    from stages.enrich_io import annotation_prose

    raw_prose = "SUMMARY: test\n\n[DOCTRINAL | explicit]: body"
    rows = [{
        "id": "cid1",
        "content": "the eucharist",
        "annotation": json.dumps(raw_prose),
    }]
    conn = _FakeConn(rows)
    qdrant = _FakeQdrant()
    content_model = _RecordingModel()
    annotation_model = _RecordingModel()

    count = asyncio.run(
        index_collection("bible", conn, qdrant, content_model, annotation_model))

    assert count == 1
    assert content_model.calls == ["the eucharist"]
    assert annotation_model.calls == [annotation_prose(raw_prose)]
    assert "[DOCTRINAL | explicit]:" not in annotation_model.calls[0]
    assert len(qdrant.calls) == 1
    collection_name, points = qdrant.calls[0]
    assert collection_name == "chunks"
    assert points[0].id == "cid1"
