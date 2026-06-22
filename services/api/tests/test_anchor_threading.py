from app.rag.retrieve import ChunkCandidate
from app.rag.rerank import RankedChunk


def test_chunk_candidate_has_anchor():
    c = ChunkCandidate(
        chunk_id="c", content="x", reference="r", collection="bible",
        document_id="d", document_title="John", author=None, rrf_score=0.1,
        anchor="john/3/16",
    )
    assert c.anchor == "john/3/16"


def test_ranked_chunk_has_anchor():
    r = RankedChunk(
        chunk_id="c", content="x", reference="r", collection="bible",
        document_id="d", document_title="John", author=None, reranker_score=0.9,
        anchor="john/3/16",
    )
    assert r.anchor == "john/3/16"
