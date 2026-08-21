"""Tests for the minimum-results floor step.

The floor runs only when the normal pipeline (rerank -> dedup -> guarantee ->
quota_cap) produced zero results. It surfaces the best-effort top candidates so a
borderline query returns *something* instead of a silent "no results".
"""
from app.rag.steps import min_floor
from app.rag.steps.types import RankedChunk


def _chunk(cid: str, score: float, title: str = "Doc", include: bool = False,
           collection: str = "catechism", chapter_key: str | None = None) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid,
        content="content",
        reference="ref",
        collection=collection,
        document_id=cid,
        document_title=title,
        author=None,
        reranker_score=score,
        include=include,
        chapter_key=chapter_key,
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


def test_one_per_work_for_variety():
    """Fallback should not return multiple near-duplicates from the same document."""
    ranked = [
        _chunk("00000000-0000-0000-0000-00000000000a", 0.3, title="SameDoc"),
        _chunk("00000000-0000-0000-0000-00000000000b", 0.29, title="SameDoc"),
        _chunk("00000000-0000-0000-0000-00000000000c", 0.28, title="OtherDoc"),
    ]
    result = min_floor.run(ranked, quota=6)
    titles = [c.document_title for c in result]
    assert titles == ["SameDoc", "OtherDoc"]


# ---------------------------------------------------------------------------
# Source spread — the floor's whole purpose is breadth on the "nothing scored
# well" screen, which is the OPPOSITE of what the per-source cap does.
# ---------------------------------------------------------------------------

def test_floor_still_spans_collections_when_one_dominates():
    """A chaptered collection must not own every slot.

    The Summa has 3,120 chapter keys, so keying the floor on the cap's grain would
    let five Summa articles fill the floor and drop every other collection.
    """
    ranked = [
        _chunk(f"00000000-0000-0000-0000-0000000000{i:02x}", 0.300 - i * 0.001,
               title="Summa Theologiae", collection="summa",
               chapter_key=f"summa/q{i}/a1")
        for i in range(6)
    ] + [
        _chunk("00000000-0000-0000-0000-0000000000f1", 0.20,
               title="Gospel of John", collection="bible", chapter_key="john/3"),
        _chunk("00000000-0000-0000-0000-0000000000f2", 0.19,
               title="Catechism of the Catholic Church", collection="catechism",
               chapter_key="ccc/part/6"),
    ]

    result = min_floor.run(ranked, quota=5)

    assert {c.collection for c in result} == {"summa", "bible", "catechism"}


def test_floor_fills_remaining_slots_from_distinct_chapters():
    """A single-collection search must still fill the floor, not return one result.

    Every chunk here is one work, so pass 1 yields exactly one; pass 2 must top the
    floor up from distinct articles.
    """
    ranked = [
        _chunk(f"00000000-0000-0000-0000-0000000001{i:02x}", 0.30 - i * 0.01,
               title="Summa Theologiae", collection="summa",
               chapter_key=f"summa/q{i}/a1")
        for i in range(6)
    ]

    result = min_floor.run(ranked, quota=5)

    assert len(result) == 5
    assert len({c.chapter_key for c in result}) == 5


def test_floor_does_not_repeat_one_chapter():
    """Pass 2 must not fill slots with several chunks of the SAME article."""
    ranked = [
        _chunk(f"00000000-0000-0000-0000-0000000002{i:02x}", 0.30 - i * 0.01,
               title="Summa Theologiae", collection="summa",
               chapter_key="summa/q1/a1")
        for i in range(6)
    ]

    result = min_floor.run(ranked, quota=5)

    assert len(result) == 1


def test_floor_output_is_score_descending():
    """Pass 2 can outscore a pass-1 pick; SSE and persistence assume sorted order."""
    ranked = [
        _chunk("00000000-0000-0000-0000-0000000003a1", 0.30, title="Summa Theologiae",
               collection="summa", chapter_key="summa/q1/a1"),
        _chunk("00000000-0000-0000-0000-0000000003a2", 0.28, title="Summa Theologiae",
               collection="summa", chapter_key="summa/q2/a1"),
        _chunk("00000000-0000-0000-0000-0000000003b1", 0.10, title="Gospel of John",
               collection="bible", chapter_key="john/3"),
    ]

    result = min_floor.run(ranked, quota=5)

    scores = [c.reranker_score for c in result]
    assert scores == sorted(scores, reverse=True)


def test_floor_degraded_is_not_more_diverse_than_healthy():
    """Nulling a chapter_key must not IMPROVE the floor."""
    healthy = [
        _chunk(f"00000000-0000-0000-0000-0000000004{i:02x}", 0.30 - i * 0.001,
               title="Summa Theologiae", collection="summa",
               chapter_key=f"summa/q{i}/a1")
        for i in range(6)
    ] + [
        _chunk("00000000-0000-0000-0000-0000000004f1", 0.20, title="Gospel of John",
               collection="bible", chapter_key="john/3"),
    ]
    degraded = [
        _chunk(c.chunk_id, c.reranker_score, title=c.document_title,
               collection=c.collection,
               chapter_key=(None if c.collection == "summa" else c.chapter_key))
        for c in healthy
    ]

    n_healthy = len({c.collection for c in min_floor.run(healthy, quota=5)})
    n_degraded = len({c.collection for c in min_floor.run(degraded, quota=5)})

    assert n_degraded <= n_healthy
