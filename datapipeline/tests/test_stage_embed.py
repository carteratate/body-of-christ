import dataclasses

import pytest
from model import Document, Passage
from cache import Cache
from config import settings as base_settings
import stages.embed as embed_mod
from stages.embed import content_embedding_input, embed_chunk, EmbedDeps


class _StubEmbed:
    def __init__(self): self.calls = 0
    async def embed(self, texts):
        self.calls += 1
        return [[float(len(t))] * 1 for t in texts]  # deterministic, 1-dim for test


def _doc():
    ps = [Passage(content=f"content {i}", reference=f"r{i}", anchor=f"a{i}",
                  chapter_key="c", chapter_label="Chap", position=i) for i in range(2)]
    return Document(id="d1", collection="summa", title="Summa", author="Aquinas", passages=ps)


def test_content_input_has_prefix():
    doc = _doc()
    s = content_embedding_input(doc.passages, 0, doc)
    assert s.startswith("Aquinas — Summa, Chap")
    assert "content 0" in s


def test_content_input_no_author():
    ps = [Passage(content=f"content {i}", reference=f"r{i}", anchor=f"a{i}",
                  chapter_key="c", chapter_label="Chap", position=i) for i in range(2)]
    doc = Document(id="d1", collection="summa", title="Summa", author=None, passages=ps)
    s = content_embedding_input(doc.passages, 0, doc)
    assert s.startswith("Summa, Chap ")
    assert not s.startswith(" —")
    assert "  " not in s  # no double-spaces
    assert "content 0" in s


def _deps(tmp_path, *, embed_client=None):
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    chunk_points, facet_points, question_points = [], [], []
    deleted_calls = []

    async def _upsert_chunk_point(pt):
        chunk_points.append(pt)

    async def _upsert_points_named(col, pts):
        (facet_points if col == "facets" else question_points).extend(pts)

    async def _delete_points_by_chunk(collection, chunk_id):
        deleted_calls.append((collection, chunk_id))

    deps = EmbedDeps(
        cache=cache, embed_client=embed_client or _StubEmbed(), qdrant=None,
        upsert_chunk_point=_upsert_chunk_point,
        upsert_points_named=_upsert_points_named,
        delete_points_by_chunk=_delete_points_by_chunk,
    )
    return deps, chunk_points, facet_points, question_points, deleted_calls


@pytest.mark.asyncio
async def test_embed_chunk_embeds_content_facets_questions(tmp_path):
    doc = _doc()
    deps, chunk_points, facet_points, question_points, _deleted = _deps(tmp_path)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?"},
              {"grounding": "settled", "evidence": "e1", "kind": "moral", "kind_secondary": "devotional",
               "text": "facet B", "question": "Q B?"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert len(chunk_points) == 1
    # Shape follows settings.QDRANT_FORMAT; "live" is a single unnamed vector.
    assert isinstance(chunk_points[0].vector, list)
    assert len(facet_points) == 2 and len(question_points) == 2
    assert facet_points[0].payload["kind"] == "doctrinal"
    assert facet_points[0].payload["grounding"] == "explicit"
    assert facet_points[0].payload["evidence"] == "e0"
    assert facet_points[1].payload["kind_secondary"] == "devotional"
    assert facet_points[0].payload["working_text"] is None  # not in PILOT_MODE
    assert question_points[0].payload["question"] == "Q A?"
    assert question_points[0].payload["facet_grounding"] == "explicit"
    assert question_points[1].payload["facet_kind_secondary"] == "devotional"
    # second run hits cache -> no new embed calls beyond first
    calls_after = deps.embed_client.calls
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert deps.embed_client.calls == calls_after


@pytest.mark.asyncio
async def test_embed_chunk_carries_working_text_when_present(tmp_path):
    doc = _doc()
    deps, _chunk_points, facet_points, _question_points, _deleted = _deps(tmp_path)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?", "working_text": "the raw working treatment"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert facet_points[0].payload["working_text"] == "the raw working treatment"


# --- embedding-cache identity: exact input text + model + dimensions, never
# chunk_id/content_hash/array position ---

@pytest.mark.asyncio
async def test_same_facet_text_and_config_is_a_cache_hit(tmp_path):
    doc = _doc()
    deps, *_ = _deps(tmp_path)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    calls_before = deps.embed_client.calls
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert deps.embed_client.calls == calls_before  # identical text -> cache hit, no new embed call


@pytest.mark.asyncio
async def test_changed_facet_text_at_same_position_is_a_cache_miss(tmp_path):
    """The core bug this fixes: new facet text at the same array position must
    never reuse a stale vector computed for the old text."""
    doc = _doc()
    deps, _chunk_points, facet_points, _question_points, _deleted = _deps(tmp_path)
    v1 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "original facet text", "question": "Q A?"}]
    await embed_chunk(doc, doc.passages, 0, v1, deps)
    first_vector = facet_points[0].vector

    facet_points.clear()
    v2 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "a completely different facet text after re-enrichment", "question": "Q A?"}]
    await embed_chunk(doc, doc.passages, 0, v2, deps)
    assert facet_points[0].vector != first_vector
    assert facet_points[0].payload["facet_text"] == v2[0]["text"]


@pytest.mark.asyncio
async def test_changed_question_text_at_same_position_is_a_cache_miss(tmp_path):
    doc = _doc()
    deps, _chunk_points, _facet_points, question_points, _deleted = _deps(tmp_path)
    v1 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "facet A", "question": "original question text"}]
    await embed_chunk(doc, doc.passages, 0, v1, deps)
    first_vector = question_points[0].vector

    question_points.clear()
    v2 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "facet A", "question": "a completely different question"}]
    await embed_chunk(doc, doc.passages, 0, v2, deps)
    assert question_points[0].vector != first_vector
    assert question_points[0].payload["question"] == v2[0]["question"]


@pytest.mark.asyncio
async def test_same_text_different_model_is_a_cache_miss(tmp_path, monkeypatch):
    doc = _doc()
    deps, _chunk_points, facet_points, _question_points, _deleted = _deps(tmp_path)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    calls_before = deps.embed_client.calls

    patched = dataclasses.replace(base_settings, EMBEDDING_MODEL="text-embedding-3-small")
    monkeypatch.setattr(embed_mod, "settings", patched)
    facet_points.clear()
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert deps.embed_client.calls == calls_before + 3  # miss -> content+facet+question all recomputed


@pytest.mark.asyncio
async def test_same_text_different_dimensions_is_a_cache_miss(tmp_path, monkeypatch):
    doc = _doc()
    deps, _chunk_points, facet_points, _question_points, _deleted = _deps(tmp_path)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    calls_before = deps.embed_client.calls

    # EMBEDDING_DIMS derives from QDRANT_FORMAT, so the format is what moves it:
    # live is 1536, v5 is 3072.
    patched = dataclasses.replace(base_settings, QDRANT_FORMAT="v5")
    monkeypatch.setattr(embed_mod, "settings", patched)
    facet_points.clear()
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert deps.embed_client.calls == calls_before + 3  # miss -> content+facet+question all recomputed


@pytest.mark.asyncio
async def test_changed_content_overlap_changes_embedding_input_and_misses_cache(tmp_path, monkeypatch):
    doc = _doc()
    deps, chunk_points, _facet_points, _question_points, _deleted = _deps(tmp_path)
    merged = []
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    calls_before = deps.embed_client.calls

    # Changing the per-collection overlap changes content_embedding_input's
    # output text, which must therefore miss the embedding cache.
    patched = dataclasses.replace(
        base_settings, PER_COLLECTION_OVERLAP={**base_settings.PER_COLLECTION_OVERLAP, "summa": (50, 50)})
    monkeypatch.setattr(embed_mod, "settings", patched)
    chunk_points.clear()
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert deps.embed_client.calls == calls_before + 1  # no facets here -> only content re-embedded


@pytest.mark.asyncio
async def test_reordered_facets_do_not_receive_each_others_cached_vectors(tmp_path):
    doc = _doc()
    deps, _chunk_points, facet_points, _question_points, _deleted = _deps(tmp_path)
    v1 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "alpha facet text", "question": "Q1?"},
          {"grounding": "settled", "evidence": "e1", "kind": "moral", "kind_secondary": None,
           "text": "beta facet text", "question": "Q2?"}]
    await embed_chunk(doc, doc.passages, 0, v1, deps)
    alpha_vector = facet_points[0].vector
    beta_vector = facet_points[1].vector
    assert alpha_vector != beta_vector

    facet_points.clear()
    v2 = list(reversed(v1))  # beta now at position 0, alpha at position 1
    await embed_chunk(doc, doc.passages, 0, v2, deps)
    # position 0 (now beta) must get beta's vector, not alpha's stale one
    assert facet_points[0].vector == beta_vector
    assert facet_points[1].vector == alpha_vector


@pytest.mark.asyncio
async def test_qdrant_payload_text_matches_the_exact_text_embedded(tmp_path):
    doc = _doc()
    deps, _chunk_points, facet_points, question_points, _deleted = _deps(tmp_path)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "the exact facet text", "question": "the exact question text"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert facet_points[0].payload["facet_text"] == "the exact facet text"
    assert question_points[0].payload["facet_text"] == "the exact facet text"
    assert question_points[0].payload["question"] == "the exact question text"


@pytest.mark.asyncio
async def test_reenrichment_deletes_existing_points_before_upserting_fresh_set(tmp_path):
    """Re-enrichment with a smaller facet set must not leave orphaned points
    behind. embed_chunk always deletes existing facet/question points for the
    chunk before upserting the current set, so shrinking is safe by
    construction rather than by chance."""
    doc = _doc()
    deps, _chunk_points, facet_points, _question_points, deleted_calls = _deps(tmp_path)
    v1 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "facet A", "question": "Q A?"},
          {"grounding": "settled", "evidence": "e1", "kind": "moral", "kind_secondary": None,
           "text": "facet B", "question": "Q B?"}]
    await embed_chunk(doc, doc.passages, 0, v1, deps)

    deleted_calls.clear()
    facet_points.clear()
    v2 = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
           "text": "facet A", "question": "Q A?"}]  # only one facet now
    await embed_chunk(doc, doc.passages, 0, v2, deps)
    # delete_points_by_chunk was called for both facets and questions before
    # the (smaller) fresh set was upserted
    collections_deleted = {c for c, _cid in deleted_calls}
    assert collections_deleted == {"facets", "questions"}
    assert len(facet_points) == 1
