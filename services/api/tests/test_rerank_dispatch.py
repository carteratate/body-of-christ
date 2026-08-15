"""Rerank dispatcher: mode selection, pool slicing, and the all_scored contract."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.rag.steps import rerank
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.rerank import RerankConfig
from app.rag.steps.types import ChunkCandidate, RankedChunk


def _cand(i: int, collection: str = "bible") -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content=f"c{i}", reference=None,
        collection=collection, document_id="d1", document_title="T", author=None,
        rrf_score=1.0 - i * 0.01,
    )


def _ranked(i: int, score: float, collection: str = "bible") -> RankedChunk:
    return RankedChunk(
        chunk_id=f"00000000-0000-0000-0000-{i:012d}", content=f"c{i}", reference=None,
        collection=collection, document_id="d1", document_title="T", author=None,
        reranker_score=score,
    )


# --- config validation ---

def test_no_reranker_is_rejected():
    """Would return raw RRF order as if scored — refuse rather than degrade silently."""
    with pytest.raises(ValueError, match="must enable Cohere"):
        RerankConfig(use_cohere=False, llm_provider=None)


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="Unknown llm_provider"):
        RerankConfig(use_cohere=True, llm_provider="gemini")


@pytest.mark.parametrize("cohere,llm,expected", [
    (True, None, "cohere_only"),
    (False, "haiku", "llm_only"),
    (True, "haiku", "both"),
    (True, "luna", "both"),
])
def test_mode_derivation(cohere, llm, expected):
    assert RerankConfig(use_cohere=cohere, llm_provider=llm).mode == expected


def test_every_registered_provider_constructs():
    for name in rerank.PROVIDERS:
        assert RerankConfig(use_cohere=False, llm_provider=name).mode == "llm_only"


# --- cohere_only ---

@pytest.mark.asyncio
async def test_cohere_only_returns_all_scored_leaving_dedup_room_to_work():
    """Previously this asserted `len(ranked) == 4`, pinning a real bug as intended
    behaviour: dedup and quota_cap run AFTER rerank and can only shrink the list, so
    pre-slicing to quota made the pipeline under-deliver. quota_cap applies the real
    per-collection limit downstream."""
    per_col = {"bible": [_ranked(i, 0.9 - i * 0.05) for i in range(10)]}
    with patch("app.rag.steps.rerank_cohere.run_per_collection",
               new=AsyncMock(return_value=per_col)):
        ranked, all_scored = await rerank.run(
            RerankConfig(use_cohere=True, llm_provider=None),
            {"bible": [_cand(i) for i in range(10)]}, "q", 4, CostTracker(),
        )
    assert len(ranked) == 10
    assert len(all_scored) == 10
    scores = [r.reranker_score for r in ranked]
    assert scores == sorted(scores, reverse=True)


# --- both ---

@pytest.mark.asyncio
async def test_both_keeps_quota_plus_extra_then_trims_to_pool_cap():
    quota = 4
    n_cols = 10
    per_col = {
        f"col{c}": [_ranked(c * 100 + i, 0.9, f"col{c}") for i in range(20)]
        for c in range(n_cols)
    }
    captured = {}

    async def _capture(pool, query, tracker, provider, step="x"):
        captured["pool"] = pool
        return pool

    with (
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value=per_col)),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool", new=_capture),
    ):
        _ranked_out, all_scored = await rerank.run(
            RerankConfig(use_cohere=True, llm_provider="haiku"),
            {f"col{c}": [_cand(c * 100)] for c in range(n_cols)}, "q", quota,
            CostTracker(),
        )

    # Each collection contributes at most quota+extra, and the merged pool is capped.
    assert len(captured["pool"]) == settings.llm_pool_global_cap
    # Guarantee candidates stay on the terminal reranker scale; Cohere-only
    # candidates outside the listwise pool are intentionally unavailable.
    assert len(all_scored) == settings.llm_pool_global_cap


@pytest.mark.asyncio
async def test_both_excludes_candidates_below_the_keep_floor():
    floor = settings.cohere_keep_score_floor
    per_col = {"bible": [_ranked(0, floor + 0.1), _ranked(1, floor - 0.1)]}
    captured = {}

    async def _capture(pool, query, tracker, provider, step="x"):
        captured["pool"] = pool
        return pool

    with (
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value=per_col)),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool", new=_capture),
    ):
        await rerank.run(
            RerankConfig(use_cohere=True, llm_provider="haiku"),
            {"bible": [_cand(0)]}, "q", 4, CostTracker(),
        )
    assert len(captured["pool"]) == 1


@pytest.mark.asyncio
async def test_collection_below_keep_floor_gets_terminal_reranker_seat():
    """Every active collection gets at least one terminal-reranker candidate so the
    guarantee never has to mix Cohere and LLM score scales."""
    floor = settings.cohere_keep_score_floor
    per_col = {
        "bible": [_ranked(0, 0.9, "bible")],
        "canon-law": [_ranked(1, floor - 0.2, "canon-law")],  # all below floor
    }
    captured = {}

    async def _capture(pool, query, tracker, provider, step="x"):
        captured["pool"] = pool
        return pool

    with (
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value=per_col)),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool", new=_capture),
    ):
        _out, all_scored = await rerank.run(
            RerankConfig(use_cohere=True, llm_provider="haiku"),
            {"bible": [_cand(0)], "canon-law": [_cand(1, "canon-law")]}, "q", 4,
            CostTracker(),
        )

    assert "canon-law" in {c.collection for c in captured["pool"]}
    assert "canon-law" in {c.collection for c in all_scored}


# --- llm_only ---

@pytest.mark.asyncio
async def test_llm_only_slices_to_historical_candidate_multiplier():
    """Keep historical candidate sizing for continuity, not cross-version equivalence."""
    quota = 4
    expected = quota * settings.candidate_multiplier
    captured = {}

    async def _capture(cands, query, q, tracker, provider, step="x"):
        captured["n"] = len(cands)
        return [_ranked(0, 0.9)]

    with patch("app.rag.steps.llm_rerank.pointwise.rerank_collection", new=_capture):
        ranked, all_scored = await rerank.run(
            RerankConfig(use_cohere=False, llm_provider="haiku"),
            {"bible": [_cand(i) for i in range(50)]}, "q", quota, CostTracker(),
        )
    assert captured["n"] == expected
    # llm_only has no second stage, so both returned lists are the same set.
    assert ranked == all_scored


@pytest.mark.asyncio
async def test_llm_only_one_failing_collection_does_not_lose_the_others():
    call_count = {"n": 0}

    async def _flaky(cands, query, q, tracker, provider, step="x"):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("collection exploded")
        return [_ranked(1, 0.7, "summa")]

    with patch("app.rag.steps.llm_rerank.pointwise.rerank_collection", new=_flaky):
        ranked, _ = await rerank.run(
            RerankConfig(use_cohere=False, llm_provider="haiku"),
            {"bible": [_cand(0)], "summa": [_cand(1, "summa")]}, "q", 4, CostTracker(),
        )
    assert [r.collection for r in ranked] == ["summa"]


# --- regression: silent-failure audit findings ---

@pytest.mark.asyncio
async def test_llm_rejected_chunk_is_not_resurrected_at_its_cohere_score():
    """A chunk the listwise reranker scored 0.05 must not be re-injected by
    collection_guarantee at its earlier Cohere score of 0.93 and shown as the top
    result. Reproduced before the fix: FINAL was [('canon-law','93%'),('bible','80%')]
    for a passage the reranker judged off-topic."""
    from app.rag.steps import collection_guarantee, dedup, quota_cap

    per_col = {
        "bible": [_ranked(0, 0.70, "bible")],
        "canon-law": [_ranked(1, 0.93, "canon-law")],
    }

    async def _listwise(pool, query, tracker, provider, step="x"):
        out = [_ranked(0, 0.80, "bible"), _ranked(1, 0.05, "canon-law")]
        out[1].include = False          # listwise derives include from the score
        return out

    with (
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value=per_col)),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool", new=_listwise),
    ):
        ranked, all_scored = await rerank.run(
            RerankConfig(use_cohere=True, llm_provider="haiku"),
            {"bible": [_cand(0)], "canon-law": [_cand(1, "canon-law")]}, "q", 4,
            CostTracker(),
        )

    # The rejected chunk appears in all_scored only at its LLM score, never 0.93.
    canon = [r for r in all_scored if r.collection == "canon-law"]
    assert canon and canon[0].reranker_score == 0.05

    final = quota_cap.run(
        collection_guarantee.run(await dedup.run(ranked), all_scored,
                                 ["bible", "canon-law"]), 4,
    )
    assert final[0].collection == "bible", (
        f"reranker-rejected chunk resurfaced at rank 1: "
        f"{[(r.collection, r.reranker_score) for r in final]}"
    )


@pytest.mark.asyncio
async def test_guarantee_candidates_use_terminal_reranker_scores_only():
    floor = settings.cohere_keep_score_floor
    per_col = {
        "bible": [_ranked(0, 0.90, "bible")],
        "canon-law": [_ranked(1, floor - 0.02, "canon-law")],  # below keep floor
    }

    async def _listwise(pool, query, tracker, provider, step="x"):
        return [
            _ranked(0, 0.80, "bible"),
            _ranked(1, 0.20, "canon-law"),
        ]

    with (
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value=per_col)),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool", new=_listwise),
    ):
        _r, all_scored = await rerank.run(
            RerankConfig(use_cohere=True, llm_provider="haiku"),
            {"bible": [_cand(0)], "canon-law": [_cand(1, "canon-law")]}, "q", 4,
            CostTracker(),
        )
    assert "canon-law" in {r.collection for r in all_scored}
    assert next(r for r in all_scored if r.collection == "canon-law").reranker_score == 0.20


def test_llm_pool_is_globally_score_sorted():
    """dedup, quota_cap and min_floor all document that input is sorted descending,
    and the pool is what listwise returns on every failure path. Built
    collection-by-collection it was grouped, not sorted, so those steps silently kept
    the wrong chunks."""
    from app.rag.steps.rerank import _llm_pool_from

    per_col = {
        "bible": [_ranked(0, 0.40, "bible"), _ranked(1, 0.35, "bible")],
        "summa": [_ranked(2, 0.99, "summa"), _ranked(3, 0.98, "summa")],
        "councils": [_ranked(4, 0.60, "councils")],
    }
    pool = _llm_pool_from(per_col, 4)
    scores = [r.reranker_score for r in pool]
    assert scores == sorted(scores, reverse=True), pool


@pytest.mark.asyncio
async def test_cohere_only_leaves_dedup_slack_rather_than_slicing_to_quota():
    """dedup's per-title cap and cosine drop can only shrink the list, so slicing to
    quota before them structurally under-delivers. Measured pre-fix: 6 scored chunks
    across 2 documents yielded 2 final results instead of 4."""
    from app.rag.steps import collection_guarantee, dedup, quota_cap

    six = [
        _ranked(i, 0.9 - i * 0.05, "bible")
        for i in range(6)
    ]
    for i, r in enumerate(six):
        r.document_title = "Psalms" if i < 4 else "John"

    with patch("app.rag.steps.rerank_cohere.run_per_collection",
               new=AsyncMock(return_value={"bible": six})):
        ranked, all_scored = await rerank.run(
            RerankConfig(use_cohere=True, llm_provider=None),
            {"bible": [_cand(0)]}, "q", 4, CostTracker(),
        )
    assert len(ranked) == 6, "cohere_only must not pre-slice to quota"

    final = quota_cap.run(
        collection_guarantee.run(await dedup.run(ranked), all_scored, ["bible"]), 4,
    )
    titles = [r.document_title for r in final]
    assert len(final) == 4, f"under-delivered: {titles}"
    assert "John" in titles, f"per-title cap starved the second document: {titles}"


def test_cohere_fallback_scores_cannot_outrank_a_real_score():
    """The synthetic score for a collection Cohere FAILED on must not sort above
    genuinely reranked results — otherwise the one unreranked collection ranks best."""
    from app.rag.steps.rerank_cohere import _fallback_ranked

    synthetic = _fallback_ranked([_cand(i) for i in range(5)])
    assert max(r.reranker_score for r in synthetic) < 0.6, (
        "fallback band overlaps real Cohere scores (0.6-0.9)"
    )
    # ...but stays representable rather than being silently excluded.
    assert min(r.reranker_score for r in synthetic) >= settings.cohere_include_floor
