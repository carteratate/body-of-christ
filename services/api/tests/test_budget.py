"""Budget derivation: pool sizes must adapt to strategy without ever returning 0."""
from __future__ import annotations

import pytest

from app.config import settings
from app.rag.steps import budget


# --- billing_chunks / cohere_pool ---

def test_billing_chunks_counts_query_against_each_document():
    # 400-token doc + 150-token query = 550 -> 2 chunks, not 1.
    assert budget.billing_chunks(400, 150) == 2
    assert budget.billing_chunks(400, 17) == 1


def test_billing_chunks_never_zero_for_empty_doc():
    assert budget.billing_chunks(0, 0) == 1


def test_cohere_pool_packs_more_unenriched_than_enriched_documents():
    """The whole point of packing: cost per collection is pinned at one search unit
    and the document count floats with document size."""
    unenriched = budget.cohere_pool([406] * 200, query_tokens=17)
    enriched = budget.cohere_pool([715] * 200, query_tokens=17)
    assert unenriched > enriched
    # Both must stay inside one billed unit (100 chunks, minus the safety margin).
    for size, n in ((406, unenriched), (715, enriched)):
        assert sum(budget.billing_chunks(size, 17) for _ in range(n)) <= 100


def test_cohere_pool_is_bounded_even_for_tiny_documents():
    """With minimal documents the chunk budget binds before the document cap.

    Every document costs at least one billing chunk, so the effective ceiling is
    `100 * cohere_pool_safety` chunks (90 by default) rather than `cohere_max_pool`
    (100 documents). `cohere_max_pool` only becomes the binding constraint if the
    safety margin is raised to 1.0 — it is retained as a hard stop, not as the
    normally-active limit.
    """
    n = budget.cohere_pool([1] * 5000, query_tokens=1)
    assert n <= settings.cohere_max_pool
    assert n == int(100 * settings.cohere_pool_safety)


def test_cohere_pool_returns_zero_only_for_no_candidates():
    assert budget.cohere_pool([], query_tokens=17) == 0


def test_cohere_pool_sends_one_oversized_document_rather_than_none():
    """A single document larger than the whole budget must still be reranked —
    returning 0 would silently drop the collection."""
    assert budget.cohere_pool([500_000], query_tokens=17) == 1


# --- retrieval_k ---

def test_retrieval_k_shrinks_as_paths_are_added():
    two = budget.retrieval_k(100, n_paths=2)
    five = budget.retrieval_k(100, n_paths=5)
    assert two > five


def test_retrieval_k_respects_clamps():
    assert budget.retrieval_k(1, n_paths=50) == settings.retrieval_k_min
    assert budget.retrieval_k(100_000, n_paths=1) == settings.retrieval_k_max
    assert budget.retrieval_k(100, n_paths=0) == settings.retrieval_k_min


# --- cohere_keep ---

def test_cohere_keep_adds_slack_only_when_an_llm_follows():
    assert budget.cohere_keep(4, with_llm=False) == 4
    assert budget.cohere_keep(4, with_llm=True) == 4 + settings.cohere_keep_extra


# --- llm_pool ---

def test_llm_pool_passes_through_when_under_cap():
    counts = {"bible": 5, "summa": 4}
    assert budget.llm_pool(counts) == counts


def test_llm_pool_trims_to_global_cap():
    counts = {f"c{i}": 8 for i in range(10)}  # 80 total
    allocation = budget.llm_pool(counts)
    assert sum(allocation.values()) == settings.llm_pool_global_cap


def test_llm_pool_guarantees_a_floor_per_contributing_collection():
    """A strong collection must not crowd a weaker one out of the pool entirely."""
    counts = {"bible": 60, "canon-law": 2}
    allocation = budget.llm_pool(counts)
    assert allocation["canon-law"] >= min(settings.llm_pool_floor_per_col, 2)
    assert sum(allocation.values()) <= settings.llm_pool_global_cap


def test_llm_pool_never_allocates_more_than_a_collection_has():
    counts = {"bible": 1, "summa": 1}
    assert budget.llm_pool(counts) == {"bible": 1, "summa": 1}


def test_llm_pool_handles_empty_input():
    assert budget.llm_pool({}) == {}


def test_llm_pool_ignores_collections_that_contributed_nothing():
    allocation = budget.llm_pool({f"c{i}": 8 for i in range(10)} | {"empty": 0})
    assert "empty" not in allocation


@pytest.mark.parametrize("n_cols,per_col", [(10, 8), (4, 20), (2, 50)])
def test_llm_pool_allocation_never_exceeds_cap(n_cols, per_col):
    counts = {f"c{i}": per_col for i in range(n_cols)}
    assert sum(budget.llm_pool(counts).values()) <= settings.llm_pool_global_cap


# --- regression: bugs found by randomized stress testing ---

def test_llm_pool_excludes_zero_count_collections_in_the_passthrough_branch():
    """Callers index their own candidate lists by these keys, so a collection that
    contributed nothing must never appear. The trimming branch filtered these out but
    the under-cap passthrough branch did not."""
    assert budget.llm_pool({"bible": 5, "empty": 0}) == {"bible": 5}


def test_llm_pool_honours_the_cap_when_the_floor_alone_would_exceed_it():
    """With more contributing collections than cap/floor, the per-collection floor
    summed past the global cap and the function returned an over-cap allocation —
    defeating the cap that exists because listwise ranking degrades on long lists."""
    counts = {f"c{i}": 1 for i in range(100)}
    allocation = budget.llm_pool(counts)
    assert sum(allocation.values()) == settings.llm_pool_global_cap
    assert all(v >= 1 for v in allocation.values())


def test_llm_pool_seats_largest_contributors_when_over_subscribed():
    counts = {"tiny": 1, "big": 50, "mid": 10}
    with_cap = {"llm_pool_global_cap": 2}
    original = settings.llm_pool_global_cap
    try:
        settings.llm_pool_global_cap = with_cap["llm_pool_global_cap"]
        allocation = budget.llm_pool(counts)
        assert set(allocation) == {"big", "mid"}
    finally:
        settings.llm_pool_global_cap = original


def test_llm_pool_never_exceeds_cap_or_over_allocates_across_random_shapes():
    """Property test: the two bugs above were only visible under randomized input."""
    import random

    random.seed(11)
    for _ in range(2000):
        counts = {
            f"c{i}": random.randint(0, 60)
            for i in range(random.randint(1, 120))
        }
        allocation = budget.llm_pool(counts)
        assert sum(allocation.values()) <= settings.llm_pool_global_cap
        for col, n in allocation.items():
            assert 0 < n <= counts[col]


def test_billing_chunks_accounts_for_max_tokens_per_doc_truncation():
    """Cohere truncates at max_tokens_per_doc before billing, so budgeting the full
    document size made the packer stop at ~half the documents it could afford."""
    huge = 8000
    assert huge > settings.cohere_max_tokens_per_doc
    clamped = budget.billing_chunks(huge, 17)
    at_cap = budget.billing_chunks(settings.cohere_max_tokens_per_doc, 17)
    assert clamped == at_cap, "oversized doc must bill as if truncated at the cap"


def test_long_document_collection_packs_more_after_the_clamp():
    """Regression: long-doc collections sent ~half the pool they could afford.

    A 4000-token Summa article billed as 9 chunks un-clamped (10 docs/unit) but only
    4 once truncated at the 1500-token cap (22 docs/unit) — so >2x more of the RRF
    pool now reaches Cohere for exactly the collections where depth matters most.
    """
    packed = budget.cohere_pool([4000] * 200, 17)
    assert packed >= 20, f"long-doc packing regressed to {packed}"

    # Short documents are unaffected — the clamp only binds above the cap.
    assert budget.cohere_pool([406] * 200, 17) == 90
