"""Derives how many documents flow through each rerank stage.

Every pool size in the rerank path is computed here rather than hardcoded, so the
number of documents adapts to the strategy actually being run: how many retrieval
paths are active, how many collections the user selected, their quota, and — for
Cohere — how large the documents themselves are.

The Cohere sizing is the interesting one. Cohere bills one *search unit* per query
plus up to 100 documents, and splits any document longer than 500 tokens (the query
length counts toward that) into chunks which each count toward the 100. So the
number of documents that fits inside a single billing unit depends on document size:
measured against real corpus chunks, plain content packs ~71 documents per unit,
while annotation+content packs ~50. Rather than pick one conservative constant and
overpay for unenriched collections, `cohere_pool` packs greedily up to the unit
boundary — cost per collection stays pinned at one search unit and the document
count floats to fill it.

`llm_only` mode is deliberately NOT sized here: it must keep the historical
`quota * candidate_multiplier` so it remains a valid A/B baseline. See
`retrieval_k`/`rrf_top_n` callers in pipelines/runner.py.
"""
from __future__ import annotations

import logging
import math

from app.config import settings

logger = logging.getLogger(__name__)

# Cohere splits a document into billing chunks of this many tokens, with the query
# length counted against each document.
_COHERE_CHUNK_TOKENS = 500
# Documents (post-split chunks) that fit in one billed search unit.
_COHERE_CHUNKS_PER_UNIT = 100


def estimate_tokens(text: str) -> int:
    """Rough token count for budgeting only.

    Deliberately a heuristic: `tiktoken` is not an API-service dependency and
    Cohere's tokenizer is not `cl100k` anyway, so an exact count is not available at
    this layer. Consumers apply `cohere_pool_safety` so the estimate errs toward
    sending fewer documents.

    ⚠️ UNVALIDATED against real traffic. chars/4 is optimistic for dense theological
    English (closer to 3.5), so the estimate can run low and push a call past the
    100-chunk boundary, doubling that collection's Cohere spend. The authority is
    `meta.billed_units.search_units` on the response, which `rerank_cohere` records
    and logs per collection — compare it against `cohere_max_pool` after a real run
    and lower `cohere_pool_safety` if calls are billing more than one unit.
    """
    return max(1, len(text) // 4)


def billing_chunks(doc_tokens: int, query_tokens: int) -> int:
    """Billing chunks one document costs, per Cohere's 500-token split rule.

    `doc_tokens` is clamped to `cohere_max_tokens_per_doc` because the API call
    passes that as `max_tokens_per_doc` and Cohere truncates before billing. Without
    the clamp a 4000-token Summa article was budgeted at 8 chunks but billed ~4, so
    the greedy packer stopped at roughly half the documents it could afford —
    silently halving how much of the RRF pool got reranked for exactly the
    long-document collections where pool depth matters most.
    """
    effective = min(doc_tokens, settings.cohere_max_tokens_per_doc)
    return max(1, math.ceil((effective + query_tokens) / _COHERE_CHUNK_TOKENS))


def cohere_pool(doc_token_sizes: list[int], query_tokens: int) -> int:
    """How many documents to send in one Cohere call.

    Greedily accumulates documents while the estimated billing-chunk total stays
    inside one search unit (scaled by `cohere_pool_safety`), capped by
    `cohere_max_pool`. Returns at least 1 whenever any document was offered — a
    single oversized document is still worth reranking, and returning 0 would
    silently drop the collection.
    """
    if not doc_token_sizes:
        return 0

    budget = _COHERE_CHUNKS_PER_UNIT * settings.cohere_pool_safety
    used = 0.0
    count = 0
    for doc_tokens in doc_token_sizes:
        cost = billing_chunks(doc_tokens, query_tokens)
        if count > 0 and used + cost > budget:
            break
        used += cost
        count += 1
        if count >= settings.cohere_max_pool:
            break
    return count


def retrieval_k(pool_target: int, n_paths: int) -> int:
    """Per-strategy retrieval limit for dynamic (non-`llm_only`) modes.

    Each active retrieval path returns its own ranked list and RRF dedupes across
    them, so the per-path limit shrinks as paths are added: asking 5 paths for 50
    each buys latency for candidates RRF discards. The 1.5 factor is overlap
    headroom — paths agree substantially, so the union is well below the sum.
    """
    if n_paths <= 0:
        return settings.retrieval_k_min
    raw = math.ceil(pool_target / n_paths * 1.5)
    return max(settings.retrieval_k_min, min(settings.retrieval_k_max, raw))


def cohere_keep(quota: int, *, with_llm: bool) -> int:
    """Documents Cohere keeps per collection.

    `both` keeps quota+extra so downstream dedup, per-title caps and the collection
    guarantee have slack; `cohere_only` is terminal, so quota is exactly right.
    """
    return quota + settings.cohere_keep_extra if with_llm else quota


def llm_pool(per_collection_counts: dict[str, int]) -> dict[str, int]:
    """Trim per-collection Cohere keeps to a global listwise budget.

    Returns how many candidates to take from each collection. Every collection that
    contributed anything keeps at least `llm_pool_floor_per_col`, so a strong
    collection cannot crowd a weaker one out of the pool entirely; the remainder is
    allocated largest-first. Listwise attention degrades as the list grows, which is
    why there is a global cap at all rather than simply sending every keep.
    """
    # A collection that contributed nothing must never appear in the allocation —
    # callers index their own candidate lists by these keys.
    contributing = {c: n for c, n in per_collection_counts.items() if n > 0}
    if not contributing:
        return {}

    cap = settings.llm_pool_global_cap
    if sum(contributing.values()) <= cap:
        return contributing

    floor = settings.llm_pool_floor_per_col
    allocation = {c: min(floor, n) for c, n in contributing.items()}
    floor_total = sum(allocation.values())

    if floor_total > cap:
        # More collections than the cap can seat at the floor. Honour the cap — it
        # exists because listwise ranking degrades on long lists — and seat the
        # largest contributors first, one slot each. Reachable only if collections
        # are added or the cap lowered, so it is a misconfiguration, not routine.
        logger.warning(
            "budget.llm_pool: %d contributing collections cannot all be seated at "
            "floor=%d within cap=%d; seating the %d largest at 1 slot each",
            len(allocation), floor, cap, cap,
        )
        ordered = sorted(contributing, key=lambda c: contributing[c], reverse=True)
        return {c: 1 for c in ordered[:cap]}

    remaining = cap - floor_total

    # Round-robin the remainder so the cap is distributed evenly rather than
    # exhausted by whichever collection happens to be largest.
    headroom = {c: contributing[c] - allocation[c] for c in allocation}
    while remaining > 0 and any(v > 0 for v in headroom.values()):
        for col in sorted(headroom, key=lambda c: headroom[c], reverse=True):
            if remaining <= 0:
                break
            if headroom[col] <= 0:
                continue
            allocation[col] += 1
            headroom[col] -= 1
            remaining -= 1
    return allocation
