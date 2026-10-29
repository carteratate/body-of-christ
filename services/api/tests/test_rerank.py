"""RankedChunk carries the passage position downstream dedup needs."""


def test_ranked_chunk_has_position_field():
    """RankedChunk must carry a position field for downstream dedup."""
    from app.rag.steps.types import RankedChunk
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000010",
        content="test",
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        reranker_score=0.8,
        position=5,
    )
    assert chunk.position == 5


def test_ranked_chunk_position_defaults_to_none():
    """position must default to None so existing callers don't need to change."""
    from app.rag.steps.types import RankedChunk
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000011",
        content="test",
        reference=None,
        collection="catechism",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="CCC",
        author=None,
        reranker_score=0.5,
    )
    assert chunk.position is None
