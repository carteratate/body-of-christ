"""Tests for collection_guarantee — injects a per-collection result and keeps
the list score-sorted (quota_cap and the streamed/persisted order depend on it)."""
from app.rag.steps.collection_guarantee import run as guarantee
from app.rag.steps.types import RankedChunk


def _rc(cid: str, collection: str, score: float) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid,
        content="content",
        reference="ref",
        collection=collection,
        document_id=cid,
        document_title="title",
        author=None,
        reranker_score=score,
    )


def test_injects_absent_collection_and_resorts():
    """An injected chunk must be merged in score order, not appended last."""
    deduped = [_rc("a", "bible", 0.9), _rc("b", "bible", 0.3)]
    all_scored = [
        _rc("a", "bible", 0.9),
        _rc("c", "catechism", 0.8),  # absent collection, high score
        _rc("b", "bible", 0.3),
    ]
    result = guarantee(deduped, all_scored, ["bible", "catechism"])

    scores = [r.reranker_score for r in result]
    assert scores == sorted(scores, reverse=True), "result must stay score-descending"
    # 0.8 catechism chunk must sit between the 0.9 and 0.3 bible chunks, not at the end
    assert [r.chunk_id for r in result] == ["a", "c", "b"]


def test_noop_when_all_collections_represented():
    deduped = [_rc("a", "bible", 0.9), _rc("c", "catechism", 0.8)]
    result = guarantee(deduped, list(deduped), ["bible", "catechism"])
    assert [r.chunk_id for r in result] == ["a", "c"]


def test_skips_injection_below_min_score():
    """A collection whose best candidate is below the 0.25 floor is not injected."""
    deduped = [_rc("a", "bible", 0.9)]
    all_scored = [_rc("a", "bible", 0.9), _rc("c", "catechism", 0.1)]
    result = guarantee(deduped, all_scored, ["bible", "catechism"])
    assert [r.chunk_id for r in result] == ["a"]
