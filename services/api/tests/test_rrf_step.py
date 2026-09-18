import pytest
from app.rag.steps import rrf
from app.rag.steps.types import ChunkCandidate, RetrievalPath


def _make_row(chunk_id: str, content: str = "x") -> dict:
    return {
        "id": chunk_id,
        "content": content,
        "reference": None,
        "collection": "bible",
        "document_id": "doc1",
        "document_title": "Title",
        "author": None,
        "anchor": None,
        "position": None,
        "annotation": None,
    }


def test_rrf_shared_chunk_gets_higher_score():
    chunk_id = "00000000-0000-0000-0000-000000000001"
    vector_results = {"bible": [RetrievalPath("hyde", [_make_row(chunk_id)])]}
    fts_results = {"bible": [_make_row(chunk_id)]}
    merged = rrf.run(vector_results, fts_results, quota=4)
    assert "bible" in merged
    assert len(merged["bible"]) == 1
    assert merged["bible"][0].chunk_id == chunk_id
    assert merged["bible"][0].rrf_score > 1 / (60 + 1)  # higher than single-list score


def test_rrf_empty_inputs_returns_empty():
    merged = rrf.run({}, {}, quota=4)
    assert merged == {}


def test_rrf_returns_chunk_candidates():
    chunk_id = "00000000-0000-0000-0000-000000000002"
    vector_results = {"catechism": [RetrievalPath("hyde", [_make_row(chunk_id)])]}
    fts_results = {}
    merged = rrf.run(vector_results, fts_results, quota=4)
    assert isinstance(merged["catechism"][0], ChunkCandidate)


def test_bible_hyde_genres_share_one_best_rank_vote():
    shared = _make_row("shared")
    paths = [
        RetrievalPath("hyde", [shared]),
        RetrievalPath("hyde", [_make_row("other"), shared]),
        RetrievalPath("hyde", [shared]),
        RetrievalPath("query", [shared]),
    ]
    merged = rrf.run({"bible": paths}, {"bible": [shared]}, quota=4)
    assert merged["bible"][0].rrf_score == pytest.approx(3 / 61)


def test_bible_hyde_only_agreement_does_not_outrank_query_and_fts_agreement():
    hyde_only = _make_row("hyde-only")
    cross_family = _make_row("cross-family")
    paths = [
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("query", [cross_family]),
    ]
    merged = rrf.run({"bible": paths}, {"bible": [cross_family]}, quota=4)
    assert [row.chunk_id for row in merged["bible"]] == ["cross-family", "hyde-only"]
    assert merged["bible"][1].rrf_score == pytest.approx(1 / 61)
