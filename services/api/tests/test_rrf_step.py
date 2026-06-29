import pytest
from app.rag.steps import rrf
from app.rag.steps.types import ChunkCandidate


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
    vector_results = {"bible": [[_make_row(chunk_id)]]}
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
    vector_results = {"catechism": [[_make_row(chunk_id)]]}
    fts_results = {}
    merged = rrf.run(vector_results, fts_results, quota=4)
    assert isinstance(merged["catechism"][0], ChunkCandidate)
