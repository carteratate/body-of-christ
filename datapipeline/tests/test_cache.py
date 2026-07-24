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


# --- Cache.canonical_hash: the dependency-artifact hash used to invalidate
# downstream stages when an upstream artifact (facets, labels) actually changes ---

def test_canonical_hash_is_deterministic():
    data = [{"id": "f1", "text": "t", "takeaway": "tk", "question": "q"}]
    assert Cache.canonical_hash(data) == Cache.canonical_hash(data)


def test_canonical_hash_ignores_dict_key_order():
    a = [{"id": "f1", "text": "t", "takeaway": "tk", "question": "q"}]
    b = [{"question": "q", "takeaway": "tk", "text": "t", "id": "f1"}]
    assert Cache.canonical_hash(a) == Cache.canonical_hash(b)


def test_canonical_hash_sensitive_to_facet_reordering():
    facets = [{"id": "f1", "text": "a"}, {"id": "f2", "text": "b"}]
    reordered = [{"id": "f2", "text": "b"}, {"id": "f1", "text": "a"}]
    assert Cache.canonical_hash(facets) != Cache.canonical_hash(reordered)


def test_canonical_hash_sensitive_to_facet_id_change():
    a = [{"id": "f1", "text": "a"}]
    b = [{"id": "f2", "text": "a"}]
    assert Cache.canonical_hash(a) != Cache.canonical_hash(b)


def test_canonical_hash_sensitive_to_any_facet_field_change():
    base = {"id": "f1", "text": "a", "takeaway": "tk", "question": "q"}
    for field, changed in [("text", "a2"), ("takeaway", "tk2"), ("question", "q2")]:
        variant = {**base, field: changed}
        assert Cache.canonical_hash([base]) != Cache.canonical_hash([variant])


def test_canonical_hash_unaffected_by_fields_never_included_in_the_artifact():
    # Volatile fields (timestamps, usage, request ids) are never part of the
    # dicts this project hashes (IdentifiedFacet/Label/annotation-text only),
    # so canonical_hash naturally excludes them simply by callers never
    # passing them in. This locks in that two structurally-identical facet
    # lists hash the same regardless of what a caller might have alongside
    # them in memory.
    a = [{"id": "f1", "text": "t", "takeaway": "tk", "question": "q"}]
    b = [{"id": "f1", "text": "t", "takeaway": "tk", "question": "q"}]
    assert Cache.canonical_hash(a) == Cache.canonical_hash(b)


def test_canonical_hash_works_on_plain_strings_for_annotation_text():
    assert Cache.canonical_hash("SUMMARY: x") == Cache.canonical_hash("SUMMARY: x")
    assert Cache.canonical_hash("SUMMARY: x") != Cache.canonical_hash("SUMMARY: y")


def test_embedding_input_hash_is_stable_and_sensitive():
    assert Cache.embedding_input_hash("facet text") == Cache.embedding_input_hash("facet text")
    assert Cache.embedding_input_hash("facet text") != Cache.embedding_input_hash("different text")


def test_generation_roundtrip_and_miss(cache):
    assert cache.get_generation("c1", "h1") is None
    cache.put_generation("c1", "h1", [{"text": "t", "question": "q"}], "p1", "claude-opus-4-8")
    got = cache.get_generation("c1", "h1")
    assert got["raw_facets"] == [{"text": "t", "question": "q"}]
    assert got["prompt_hash"] == "p1"
    assert got["model"] == "claude-opus-4-8"


def test_generation_roundtrip_carries_temperature_and_schema_version(cache):
    cache.put_generation("c1", "h1", [{"text": "t"}], "p1", "claude-opus-4-8",
                         temperature=1.0, schema_version=1)
    got = cache.get_generation("c1", "h1")
    assert got["temperature"] == 1.0
    assert got["schema_version"] == 1


def test_generation_row_without_dependency_fields_reads_back_as_none(cache):
    # A "legacy" row written the old way (no temperature/schema_version kwargs)
    # must read back with those fields as None, not some default that could
    # accidentally compare equal to a real config value.
    cache.put_generation("c1", "h1", [{"text": "t"}], "p1", "claude-opus-4-8")
    got = cache.get_generation("c1", "h1")
    assert got["temperature"] is None
    assert got["schema_version"] is None


def test_generation_replace_on_new_prompt(cache):
    cache.put_generation("c1", "h1", [{"text": "a", "question": "q"}], "p1", "claude-opus-4-8")
    cache.put_generation("c1", "h1", [{"text": "b", "question": "q"}], "p2", "claude-opus-4-8")
    got = cache.get_generation("c1", "h1")
    assert got["raw_facets"][0]["text"] == "b"
    assert got["prompt_hash"] == "p2"


def test_classification_roundtrip(cache):
    cache.put_classification(
        "c1", "h1",
        [{"grounding": "explicit", "evidence": "e", "kind": "doctrinal"}],
        "cp1", "claude-sonnet-4-6")
    got = cache.get_classification("c1", "h1")
    assert got["labels"][0]["kind"] == "doctrinal"
    assert got["labels"][0]["grounding"] == "explicit"
    assert got["prompt_hash"] == "cp1"
    assert got["model"] == "claude-sonnet-4-6"


def test_classification_roundtrip_carries_generation_hash(cache):
    cache.put_classification(
        "c1", "h1", [{"grounding": "explicit", "evidence": "e", "kind": "doctrinal"}],
        "cp1", "claude-sonnet-4-6", temperature=0.0, schema_version=1,
        generation_hash="genhash123")
    got = cache.get_classification("c1", "h1")
    assert got["generation_hash"] == "genhash123"
    assert got["temperature"] == 0.0
    assert got["schema_version"] == 1


def test_classification_row_without_dependency_fields_reads_back_as_none(cache):
    cache.put_classification(
        "c1", "h1", [{"grounding": "explicit", "evidence": "e", "kind": "doctrinal"}],
        "cp1", "claude-sonnet-4-6")
    got = cache.get_classification("c1", "h1")
    assert got["generation_hash"] is None
    assert got["temperature"] is None
    assert got["schema_version"] is None


def test_annotation_roundtrip_and_miss(cache):
    assert cache.get_annotation("c1", "h1") is None
    cache.put_annotation("c1", "h1", "SUMMARY: x", "ap1", "claude-sonnet-4-6")
    got = cache.get_annotation("c1", "h1")
    assert got["annotation"] == "SUMMARY: x"
    assert got["prompt_hash"] == "ap1"
    assert got["model"] == "claude-sonnet-4-6"


def test_annotation_roundtrip_carries_upstream_hashes(cache):
    cache.put_annotation("c1", "h1", "SUMMARY: x", "ap1", "claude-sonnet-4-6",
                         temperature=0.3, schema_version=1,
                         generation_hash="genhash", classification_hash="clshash")
    got = cache.get_annotation("c1", "h1")
    assert got["generation_hash"] == "genhash"
    assert got["classification_hash"] == "clshash"
    assert got["temperature"] == 0.3
    assert got["schema_version"] == 1


def test_annotation_row_without_dependency_fields_reads_back_as_none(cache):
    cache.put_annotation("c1", "h1", "SUMMARY: x", "ap1", "claude-sonnet-4-6")
    got = cache.get_annotation("c1", "h1")
    assert got["generation_hash"] is None
    assert got["classification_hash"] is None


def test_annotation_independently_rerunnable_without_touching_generation(cache):
    cache.put_generation("c1", "h1", [{"text": "a", "question": "q"}], "p1", "claude-opus-4-8")
    cache.put_annotation("c1", "h1", "SUMMARY: first", "ap1", "claude-sonnet-4-6")
    cache.put_annotation("c1", "h1", "SUMMARY: second", "ap2", "claude-sonnet-4-6")
    assert cache.get_annotation("c1", "h1")["annotation"] == "SUMMARY: second"
    assert cache.get_generation("c1", "h1")["raw_facets"][0]["text"] == "a"


def test_enrichment_roundtrip(cache):
    facets = [{"grounding": "settled", "evidence": "e", "kind": "typological", "text": "t", "question": "q"}]
    cache.put_enrichment("c1", "h1", facets, "SUMMARY: x")
    got = cache.get_enrichment("c1", "h1")
    assert got["facets"] == facets
    assert got["annotation"] == "SUMMARY: x"


def test_enrichment_roundtrip_carries_all_three_dependency_hashes(cache):
    facets = [{"grounding": "settled", "evidence": "e", "kind": "typological", "text": "t", "question": "q"}]
    cache.put_enrichment("c1", "h1", facets, "SUMMARY: x",
                         generation_hash="g", classification_hash="c",
                         annotation_hash="a", schema_version=1)
    got = cache.get_enrichment("c1", "h1")
    assert got["generation_hash"] == "g"
    assert got["classification_hash"] == "c"
    assert got["annotation_hash"] == "a"
    assert got["schema_version"] == 1


def test_enrichment_row_without_dependency_fields_reads_back_as_none(cache):
    cache.put_enrichment("c1", "h1", [], "SUMMARY: x")
    got = cache.get_enrichment("c1", "h1")
    assert got["generation_hash"] is None
    assert got["classification_hash"] is None
    assert got["annotation_hash"] is None


# --- embeddings: content-addressed (exact input text + model + dimensions) ---

def test_embedding_roundtrip(cache):
    input_hash = Cache.embedding_input_hash("some facet text")
    assert cache.get_embedding(input_hash, "text-embedding-3-large", 3072) is None
    cache.put_embedding(input_hash, "text-embedding-3-large", 3072, [0.1, 0.2, 0.3])
    got = cache.get_embedding(input_hash, "text-embedding-3-large", 3072)
    assert got == pytest.approx([0.1, 0.2, 0.3])


def test_embedding_different_text_is_a_miss_even_at_same_position(cache):
    hash_a = Cache.embedding_input_hash("facet text version A")
    hash_b = Cache.embedding_input_hash("facet text version B")
    cache.put_embedding(hash_a, "text-embedding-3-large", 3072, [0.1, 0.2])
    assert cache.get_embedding(hash_b, "text-embedding-3-large", 3072) is None


def test_embedding_different_model_is_a_miss_for_same_text(cache):
    input_hash = Cache.embedding_input_hash("some facet text")
    cache.put_embedding(input_hash, "text-embedding-3-large", 3072, [0.1, 0.2])
    assert cache.get_embedding(input_hash, "text-embedding-3-small", 3072) is None


def test_embedding_different_dimensions_is_a_miss_for_same_text_and_model(cache):
    input_hash = Cache.embedding_input_hash("some facet text")
    cache.put_embedding(input_hash, "text-embedding-3-large", 3072, [0.1, 0.2])
    assert cache.get_embedding(input_hash, "text-embedding-3-large", 1536) is None


def test_embedding_identical_text_reused_across_different_chunks(cache):
    # Content-addressed: identical exact input under identical configuration
    # is reused regardless of which chunk/facet position first produced it.
    input_hash = Cache.embedding_input_hash("Christ is risen")
    cache.put_embedding(input_hash, "text-embedding-3-large", 3072, [0.4, 0.5])
    # A second, unrelated caller computing the same hash for the same text
    # gets the same cached vector.
    assert cache.get_embedding(Cache.embedding_input_hash("Christ is risen"),
                               "text-embedding-3-large", 3072) == pytest.approx([0.4, 0.5])


def test_collection_status(cache):
    assert cache.get_collection_status("bible") is None
    cache.set_collection_status("bible", total_chunks=100, enriched=40, complete=False)
    st = cache.get_collection_status("bible")
    assert st["total_chunks"] == 100 and st["enriched"] == 40 and st["complete"] == 0
    cache.set_collection_status("bible", total_chunks=100, enriched=100, complete=True)
    assert cache.get_collection_status("bible")["complete"] == 1


def test_chunk_status_roundtrip_and_miss(cache):
    assert cache.get_chunk_status("c1", "h1") is None
    cache.set_chunk_status("c1", "h1", "classification_failed",
                           raw_response='{"labels": []}', validation_errors="count mismatch")
    st = cache.get_chunk_status("c1", "h1")
    assert st["status"] == "classification_failed"
    assert st["raw_response"] == '{"labels": []}'
    assert st["validation_errors"] == "count mismatch"


def test_chunk_status_replace(cache):
    cache.set_chunk_status("c1", "h1", "classification_failed", raw_response="a", validation_errors="x")
    cache.set_chunk_status("c1", "h1", "annotation_failed", raw_response="b", validation_errors="y")
    st = cache.get_chunk_status("c1", "h1")
    assert st["status"] == "annotation_failed"
    assert st["raw_response"] == "b"
