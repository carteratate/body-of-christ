"""Tests for position+cosine dedup and the per-source cap."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.dedup import _cosine_sim, apply_dedup
from app.rag.steps.types import RankedChunk


def _chunk(
    chunk_id: str,
    doc_id: str,
    doc_title: str,
    score: float,
    position: int | None = None,
    collection: str = "catechism",
    chapter_key: str | None = None,
) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id,
        content="content",
        reference="Ref 1:1",
        collection=collection,
        document_id=doc_id,
        document_title=doc_title,
        author=None,
        reranker_score=score,
        include=True,
        position=position,
        chapter_key=chapter_key,
    )


# ---------------------------------------------------------------------------
# _cosine_sim
# ---------------------------------------------------------------------------

def test_cosine_sim_identical_vectors_returns_one():
    v = [1.0, 0.0, 0.0]
    assert _cosine_sim(v, v) == pytest.approx(1.0)


def test_cosine_sim_orthogonal_vectors_returns_zero():
    assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_sim_zero_vector_returns_zero():
    assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_sim_opposite_vectors_returns_minus_one():
    assert _cosine_sim([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# apply_dedup — cosine dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dedup_drops_lower_scorer_when_close_and_cosine_high():
    """Position ≤2 apart AND cosine > 0.9 → lower scorer dropped."""
    a = _chunk("aaaa-0000-0000-0000-000000000001", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000002", "doc1", "CCC", 0.7, position=2)

    vec = [1.0] + [0.0] * 1535  # cosine(v, v) = 1.0 > 0.9

    mock_pt_a = MagicMock(); mock_pt_a.id = "aaaa-0000-0000-0000-000000000001"; mock_pt_a.vector = vec
    mock_pt_b = MagicMock(); mock_pt_b.id = "bbbb-0000-0000-0000-000000000002"; mock_pt_b.vector = vec
    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[mock_pt_a, mock_pt_b])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000001" in ids
    assert "bbbb-0000-0000-0000-000000000002" not in ids


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_cosine_below_threshold():
    """Same document, close positions, but cosine < 0.9 → keep both."""
    a = _chunk("aaaa-0000-0000-0000-000000000003", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000004", "doc1", "CCC", 0.7, position=2)

    vec_a = [1.0] + [0.0] * 1535
    vec_b = [0.0, 1.0] + [0.0] * 1534  # cosine(a, b) = 0.0

    mock_pt_a = MagicMock(); mock_pt_a.id = "aaaa-0000-0000-0000-000000000003"; mock_pt_a.vector = vec_a
    mock_pt_b = MagicMock(); mock_pt_b.id = "bbbb-0000-0000-0000-000000000004"; mock_pt_b.vector = vec_b
    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[mock_pt_a, mock_pt_b])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000003" in ids
    assert "bbbb-0000-0000-0000-000000000004" in ids


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_positions_far_apart():
    """Positions > 2 apart → skip cosine check entirely, keep both."""
    a = _chunk("aaaa-0000-0000-0000-000000000005", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000006", "doc1", "CCC", 0.7, position=10)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000005" in ids
    assert "bbbb-0000-0000-0000-000000000006" in ids
    # Qdrant should not be called when no close pairs exist
    mock_client.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_position_is_none():
    """When position is missing, cannot check proximity — keep both chunks."""
    a = _chunk("aaaa-0000-0000-0000-000000000007", "doc1", "CCC", 0.9, position=None)
    b = _chunk("bbbb-0000-0000-0000-000000000008", "doc1", "CCC", 0.7, position=None)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    assert len(result) == 2


# ---------------------------------------------------------------------------
# apply_dedup — per-source cap (title grain)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_source_cap_drops_third_chunk():
    """Max 2 results per document_title — third is dropped regardless of score."""
    # Three chunks with same title but different document_ids (different translations)
    a = _chunk("aaaa-0000-0000-0000-000000000009", "doc_a", "Summa Theologica", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000010", "doc_b", "Summa Theologica", 0.8, position=50)
    c = _chunk("cccc-0000-0000-0000-000000000011", "doc_c", "Summa Theologica", 0.7, position=100)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b, c])

    assert len(result) == 2
    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000009" in ids
    assert "bbbb-0000-0000-0000-000000000010" in ids
    assert "cccc-0000-0000-0000-000000000011" not in ids


@pytest.mark.asyncio
async def test_per_source_cap_allows_two_different_titles():
    """Different document titles are each allowed up to 2 results."""
    a = _chunk("aaaa-0000-0000-0000-000000000012", "doc1", "Summa", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000013", "doc1", "Summa", 0.8, position=50)
    c = _chunk("cccc-0000-0000-0000-000000000014", "doc2", "Catechism", 0.7, position=1)
    d = _chunk("dddd-0000-0000-0000-000000000015", "doc2", "Catechism", 0.6, position=50)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b, c, d])

    assert len(result) == 4


@pytest.mark.asyncio
async def test_dedup_graceful_on_qdrant_failure():
    """If Qdrant retrieve fails, dedup is skipped but the per-source cap still applies."""
    a = _chunk("aaaa-0000-0000-0000-000000000016", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000017", "doc1", "CCC", 0.7, position=2)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(side_effect=RuntimeError("Qdrant down"))

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    # Both survive (cosine dedup skipped), per-source cap allows 2
    assert len(result) == 2


# ---------------------------------------------------------------------------
# per-source cap — chapter-keyed (single-document) collections
#
# Regression cover for the ceiling that limited an entire single-document
# collection to _PER_SOURCE_CAP results per search. Positions are spaced beyond
# _POSITION_PROXIMITY so the cosine path never runs and these assert the cap alone.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summa_distinct_articles_are_not_capped_together():
    """Distinct Summa articles are distinct sources, so >2 may be returned.

    Before the fix all 26,750 Summa chunks shared one document_title and the
    whole collection was capped at 2 results per search.
    """
    chunks = [
        _chunk(f"aaaa-0000-0000-0000-00000000{i:04d}", "summa_doc", "Summa Theologiae",
               0.9 - i * 0.01, position=i * 100,
               collection="summa", chapter_key=f"summa/part/q{i}/a1")
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 4


@pytest.mark.asyncio
async def test_summa_same_article_still_capped():
    """Within ONE article the cap still applies — that is the diversity it protects."""
    chunks = [
        _chunk(f"bbbb-0000-0000-0000-00000000{i:04d}", "summa_doc", "Summa Theologiae",
               0.9 - i * 0.01, position=i * 100,
               collection="summa", chapter_key="summa/first-part/q42/a2")
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 2
    assert [r.reranker_score for r in result] == [0.9, 0.89]


@pytest.mark.asyncio
async def test_chapter_keyed_collection_falls_back_to_title_without_chapter_key():
    """A null chapter_key must not collapse every chunk into one bucket.

    Qdrant payloads carry no chapter_key; fetch_positions backfills it. If that
    step degrades, the cap must fall back to the old document_title behaviour
    rather than counting unrelated chunks against a single null key.
    """
    chunks = [
        _chunk(f"cccc-0000-0000-0000-00000000{i:04d}", "summa_doc", "Summa Theologiae",
               0.9 - i * 0.01, position=i * 100,
               collection="summa", chapter_key=None)
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_multi_document_collection_still_caps_on_title():
    """Multi-document collections are unchanged: chapter_key must NOT loosen them.

    One encyclical is one source however many sections match.
    """
    chunks = [
        _chunk(f"dddd-0000-0000-0000-00000000{i:04d}", "enc_doc", "Rerum Novarum",
               0.9 - i * 0.01, position=i * 100,
               collection="encyclicals", chapter_key=f"rerum-novarum/sec-{i}")
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 2


def test_chapter_keyed_collections_are_valid_collection_names():
    """Guard against a typo or a renamed collection silently disabling the fix."""
    from app.rag.constants import VALID_COLLECTIONS
    from app.rag.dedup import _CHAPTER_KEYED_COLLECTIONS

    assert _CHAPTER_KEYED_COLLECTIONS <= VALID_COLLECTIONS


def test_source_key_cannot_collide_across_kinds():
    """A document titled like a chapter key must not share a bucket with one."""
    from app.rag.dedup import _CHAPTER_KEYED_COLLECTIONS, source_key

    chaptered = _chunk("e1", "d", "Summa Theologiae", 0.9,
                       collection="summa", chapter_key="x")
    titled = _chunk("e2", "d", "Summa Theologiae/x", 0.9,
                    collection="encyclicals", chapter_key=None)

    assert source_key(chaptered, _CHAPTER_KEYED_COLLECTIONS) != source_key(
        titled, _CHAPTER_KEYED_COLLECTIONS
    )


@pytest.mark.asyncio
async def test_mixed_chapter_key_does_not_loosen_the_cap():
    """A PARTIAL chapter_key backfill must not admit more than a complete one.

    Qdrant candidates arrive with chapter_key=None and fetch_positions backfills
    them from Postgres; on a degraded backfill only the FTS-sourced chunks keep a
    key. Deciding the grain per chunk would open two disjoint buckets for one
    collection and admit 2 from each — four chunks of ONE Summa article.
    """
    chunks = [
        _chunk("eeee-0000-0000-0000-000000000001", "summa_doc", "Summa Theologiae",
               0.9, position=100, collection="summa",
               chapter_key="summa/first-part/q42/a2"),
        _chunk("eeee-0000-0000-0000-000000000002", "summa_doc", "Summa Theologiae",
               0.8, position=200, collection="summa",
               chapter_key="summa/first-part/q42/a2"),
        # Same article, but these came from Qdrant and were never backfilled.
        _chunk("eeee-0000-0000-0000-000000000003", "summa_doc", "Summa Theologiae",
               0.7, position=300, collection="summa", chapter_key=None),
        _chunk("eeee-0000-0000-0000-000000000004", "summa_doc", "Summa Theologiae",
               0.6, position=400, collection="summa", chapter_key=None),
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_degraded_never_returns_more_than_healthy():
    """The ordering invariant the mixed-state bug inverted."""
    healthy = [
        _chunk(f"ffff-0000-0000-0000-00000000{i:04d}", "summa_doc", "Summa Theologiae",
               0.9 - i * 0.01, position=i * 100, collection="summa",
               chapter_key="summa/first-part/q42/a2")
        for i in range(4)
    ]
    degraded = [
        _chunk(f"ffff-0000-0000-0000-00000000{i:04d}", "summa_doc", "Summa Theologiae",
               0.9 - i * 0.01, position=i * 100, collection="summa",
               chapter_key=("summa/first-part/q42/a2" if i < 2 else None))
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        n_healthy = len(await apply_dedup(healthy))
        n_degraded = len(await apply_dedup(degraded))

    assert n_degraded <= n_healthy


@pytest.mark.asyncio
async def test_two_documents_sharing_a_chapter_key_are_distinct_sources():
    """Chapter keys are only unique within a document.

    The 1917 Code beside the 1983 Code would reuse chapter keys under distinct
    titles; keying on chapter_key alone would merge them and make the cap STRICTER
    than before the change. (Two *translations* of one work share a title and are
    merged deliberately — see test_translations_share_a_bucket_under_the_chapter_grain.)
    """
    chunks = [
        _chunk("1111-0000-0000-0000-000000000001", "doc_1983", "Code of Canon Law (1983)",
               0.9, position=100, collection="canon-law", chapter_key="canon-law/ch3"),
        _chunk("1111-0000-0000-0000-000000000002", "doc_1983", "Code of Canon Law (1983)",
               0.8, position=200, collection="canon-law", chapter_key="canon-law/ch3"),
        _chunk("1111-0000-0000-0000-000000000003", "doc_1917", "Code of Canon Law (1917)",
               0.7, position=300, collection="canon-law", chapter_key="canon-law/ch3"),
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 3
    assert "1111-0000-0000-0000-000000000003" in [r.chunk_id for r in result]


@pytest.mark.asyncio
async def test_translations_of_one_work_still_share_a_bucket():
    """Two translations of one work must NOT each claim a full cap allowance.

    Migration 0008 permits one document per translation under a shared title;
    collapsing them is why both branches key on document_title, not document_id.
    """
    chunks = [
        _chunk(f"2222-0000-0000-0000-00000000{i:04d}", f"doc_tr{i}", "Confessions",
               0.9 - i * 0.01, position=i * 100, collection="church-fathers",
               chapter_key=f"confessions/book-{i}")
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_shared_title_across_collections_does_not_invert_degradation():
    """Two collections sharing a title must not let a degraded run beat a healthy one.

    Round-2 regression: with collection absent from the key, a chaptered collection
    that demoted to the title grain LEFT the chapter bucket it was colliding in and
    landed in a fresh title bucket, admitting a chunk the healthy path rejected.
    """
    def build(canon_chapter_key):
        return [
            _chunk("3333-0000-0000-0000-000000000001", "d1", "Shared Title", 0.90,
                   position=100, collection="summa", chapter_key="b"),
            _chunk("3333-0000-0000-0000-000000000002", "d2", "Shared Title", 0.80,
                   position=200, collection="canon-law", chapter_key=canon_chapter_key),
            _chunk("3333-0000-0000-0000-000000000003", "d2", "Shared Title", 0.70,
                   position=300, collection="canon-law", chapter_key=canon_chapter_key),
        ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        healthy = len(await apply_dedup(build("b")))
        degraded = len(await apply_dedup(build(None)))

    assert degraded <= healthy


@pytest.mark.asyncio
async def test_translations_share_a_bucket_under_the_chapter_grain():
    """Translations must share an allowance on the chapter branch too, not just title.

    `source_key` keys on document_title precisely so two translations of one work
    (permitted by the `translation` column added in migration 0008) cannot each claim a full cap.
    """
    chunks = [
        _chunk(f"4444-0000-0000-0000-00000000{i:04d}", f"doc_tr{i % 2}",
               "Summa Theologiae", 0.9 - i * 0.01, position=i * 100,
               collection="summa", chapter_key="summa/first-part/q42/a2")
        for i in range(4)
    ]

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup(chunks)

    assert len(result) == 2
