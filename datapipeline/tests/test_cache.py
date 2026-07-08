import pytest
from cache import Cache


@pytest.fixture
def cache(tmp_path):
    c = Cache(str(tmp_path / "cache.db"))
    c.init_schema()
    yield c
    c.close()


def test_content_hash_is_stable_and_sensitive():
    assert Cache.content_hash("abc") == Cache.content_hash("abc")
    assert Cache.content_hash("abc") != Cache.content_hash("abd")
    assert len(Cache.content_hash("abc")) == 64


def test_generation_roundtrip_and_miss(cache):
    assert cache.get_generation("c1", "h1") is None
    cache.put_generation("c1", "h1", [{"text": "t", "question": "q"}], "SUMMARY: ...", "p1")
    got = cache.get_generation("c1", "h1")
    assert got["raw_facets"] == [{"text": "t", "question": "q"}]
    assert got["annotation"].startswith("SUMMARY")
    assert got["prompt_hash"] == "p1"


def test_generation_replace_on_new_prompt(cache):
    cache.put_generation("c1", "h1", [{"text": "a", "question": "q"}], "A", "p1")
    cache.put_generation("c1", "h1", [{"text": "b", "question": "q"}], "B", "p2")
    got = cache.get_generation("c1", "h1")
    assert got["raw_facets"][0]["text"] == "b"
    assert got["prompt_hash"] == "p2"


def test_classification_roundtrip(cache):
    cache.put_classification("c1", "h1", [{"confidence": "explicit", "kind": "doctrinal"}], "cp1")
    got = cache.get_classification("c1", "h1")
    assert got["labels"][0]["kind"] == "doctrinal"
    assert got["prompt_hash"] == "cp1"


def test_enrichment_roundtrip(cache):
    facets = [{"confidence": "traditional", "kind": "typological", "text": "t", "question": "q"}]
    cache.put_enrichment("c1", "h1", facets, "SUMMARY: x")
    got = cache.get_enrichment("c1", "h1")
    assert got["facets"] == facets
    assert got["annotation"] == "SUMMARY: x"


def test_embedding_roundtrip(cache):
    assert cache.get_embedding("c1", "h1", "content") is None
    cache.put_embedding("c1", "h1", "content", [0.1, 0.2, 0.3])
    got = cache.get_embedding("c1", "h1", "content")
    assert got == pytest.approx([0.1, 0.2, 0.3])


def test_collection_status(cache):
    assert cache.get_collection_status("bible") is None
    cache.set_collection_status("bible", total_chunks=100, enriched=40, complete=False)
    st = cache.get_collection_status("bible")
    assert st["total_chunks"] == 100 and st["enriched"] == 40 and st["complete"] == 0
    cache.set_collection_status("bible", total_chunks=100, enriched=100, complete=True)
    assert cache.get_collection_status("bible")["complete"] == 1
