from writers.qdrant import collection_filter, QDRANT_COLLECTION, EMBEDDING_DIMS


def test_collection_filter_targets_payload_collection():
    f = collection_filter("church-fathers")
    cond = f.must[0]
    assert cond.key == "collection"
    assert cond.match.value == "church-fathers"


def test_constants():
    assert QDRANT_COLLECTION == "chunks"
    assert EMBEDDING_DIMS == 3072
