"""Tests for the minimum-results floor step.

The floor runs only when the normal pipeline (rerank -> dedup -> guarantee ->
quota_cap) produced zero results. It surfaces the best-effort top candidates so a
borderline query returns *something* instead of a silent "no results".
"""
from app.rag.steps import min_floor
from app.rag.steps.types import RankedChunk


def _chunk(cid: str, score: float, title: str = "Doc", include: bool = False) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid,
        content="content",
        reference="ref",
        collection="catechism",
        document_id=cid,
        document_title=title,
        author=None,
        reranker_score=score,
        include=include,
    )


def test_empty_ranked_returns_empty():
    assert min_floor.run([], quota=6) == []


def test_surfaces_top_scored_even_when_all_excluded():
    """Every chunk scored below threshold (include=False) — floor still returns the best ones."""
    ranked = [
        _chunk("00000000-0000-0000-0000-00000000000a", 0.22, title="A"),
        _chunk("00000000-0000-0000-0000-00000000000b", 0.18, title="B"),
        _chunk("00000000-0000-0000-0000-00000000000c", 0.05, title="C"),
    ]
    result = min_floor.run(ranked, quota=6)
    assert len(result) == 3
    # Highest score first, all surfaced despite include=False
    assert result[0].reranker_score == 0.22
    assert all(not c.include or c.include for c in result)  # include state irrelevant here


def test_caps_at_floor_limit():
    """Never returns more than the floor cap even if quota is large."""
    ranked = [
        _chunk(f"00000000-0000-0000-0000-0000000000{i:02x}", 0.3 - i * 0.01, title=f"T{i}")
        for i in range(20)
    ]
    result = min_floor.run(ranked, quota=50)
    assert len(result) == min_floor._FLOOR_N


def test_respects_quota_when_smaller_than_floor():
    ranked = [
        _chunk(f"00000000-0000-0000-0000-0000000000{i:02x}", 0.3 - i * 0.01, title=f"T{i}")
        for i in range(20)
    ]
    result = min_floor.run(ranked, quota=2)
    assert len(result) == 2


def test_one_per_title_for_variety():
    """Fallback should not return multiple near-duplicates from the same document."""
    ranked = [
        _chunk("00000000-0000-0000-0000-00000000000a", 0.3, title="SameDoc"),
        _chunk("00000000-0000-0000-0000-00000000000b", 0.29, title="SameDoc"),
        _chunk("00000000-0000-0000-0000-00000000000c", 0.28, title="OtherDoc"),
    ]
    result = min_floor.run(ranked, quota=6)
    titles = [c.document_title for c in result]
    assert titles == ["SameDoc", "OtherDoc"]
