"""Re-ranking using Cohere Rerank v4.0 Pro, one call per collection.

One call per collection rather than one global call: Cohere bills per query plus up
to 100 documents, so per-collection calls cost more in total (10 collections = 10
units vs 6 for one 600-doc global call) but let each collection be reranked against
its own candidate set and sliced independently. `budget.cohere_pool` packs each call
up to the one-search-unit boundary so the extra headroom is not wasted.

A failed collection degrades to RRF order for that collection only — never fails the
whole query.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from collections import deque

import cohere

from app.config import settings
from app.rag.steps import budget, degradation
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.rerank_docs import cohere_document
from app.rag.steps.types import ChunkCandidate, RankedChunk

logger = logging.getLogger(__name__)

_client: cohere.AsyncClientV2 | None = None


class _RateLimiter:
    """Sliding-window throttle over a shared call budget.

    Cohere's limit is per key, not per connection, so the window has to be shared
    across every concurrent collection task — hence module-level state behind a lock.
    Exists because a 429 here is not a loud failure: it degrades one collection to
    unreranked RRF order, which looks like a working search but silently invalidates
    any quality measurement.
    """

    def __init__(self) -> None:
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        limit = settings.cohere_max_calls_per_minute
        if limit <= 0:
            return
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 60.0:
                    self._calls.popleft()
                if len(self._calls) < limit:
                    self._calls.append(now)
                    return
                wait = 60.0 - (now - self._calls[0]) + 0.05
            logger.info(
                "rerank_cohere: throttling %.1fs to stay under %d calls/min",
                wait, limit,
            )
            _record_wait(wait)
            await asyncio.sleep(wait)


_rate_limiter = _RateLimiter()

# Per-request accumulator for time spent NOT calling Cohere — throttle waits and
# 429 backoff. A ContextVar holding a mutable list, so the concurrent per-collection
# tasks (which inherit a copy of the context but the same list object) all append to
# one place.
#
# This exists because throttle time lands inside the `rerank` step and therefore
# inside wall-clock, silently inflating every latency measurement taken while rate
# limited. Reporting it separately is what makes a throttled batch run usable for
# latency at all: subtract it to recover the latency a non-throttled key would give.
_throttle_wait: contextvars.ContextVar[list[float] | None] = contextvars.ContextVar(
    "cohere_throttle_wait", default=None,
)


def begin_throttle_accounting() -> list[tuple[float, float]]:
    """Start a fresh throttle-wait accumulator for this request."""
    box: list[tuple[float, float]] = []
    _throttle_wait.set(box)
    return box


def _record_wait(seconds: float) -> None:
    """Record a throttle wait as a (start, end) interval on the monotonic clock.

    Intervals, not a running sum: the per-collection tasks wait CONCURRENTLY on one
    shared window, so summing gave 5 x 20s = 100s of "wait" inside a 20s span — and
    subtracting that from wall clock produced negative latencies in a real run.
    """
    box = _throttle_wait.get()
    if box is not None:
        now = time.monotonic()
        box.append((now, now + seconds))


def throttle_wait_seconds() -> float:
    """Wall-clock seconds during which AT LEAST ONE task was throttled.

    Overlapping intervals are merged, so this can be subtracted from a pipeline's
    wall time to recover the latency an unthrottled key would have produced.
    """
    box = _throttle_wait.get()
    if not box:
        return 0.0
    merged_total = 0.0
    cur_start, cur_end = None, None
    for start, end in sorted(box):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                merged_total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        merged_total += cur_end - cur_start
    return merged_total


def _is_rate_limit(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    return status == 429 or "429" in str(exc)[:200]


async def _rerank_with_retry(**kwargs):
    """Call Cohere, retrying only on 429 with exponential backoff.

    A 429 is transient and worth waiting out; anything else (bad request, auth,
    5xx) fails fast so the caller's RRF fallback engages and gets logged.
    """
    attempts = settings.cohere_max_retries_429 + 1
    for attempt in range(attempts):
        await _rate_limiter.acquire()
        try:
            return await _client.rerank(**kwargs)
        except Exception as exc:
            if not _is_rate_limit(exc) or attempt == attempts - 1:
                raise
            backoff = min(60.0, 5.0 * (2 ** attempt))
            logger.warning(
                "rerank_cohere: 429 rate-limited (attempt %d/%d) — backing off %.0fs",
                attempt + 1, attempts, backoff,
            )
            _record_wait(backoff)
            await asyncio.sleep(backoff)
    raise RuntimeError("unreachable")


def init_cohere() -> None:
    global _client
    _client = None
    if settings.cohere_api_key:
        _client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
    else:
        logger.warning(
            "COHERE_API_KEY is not set; searches will use the RRF fallback before terminal reranking"
        )


def is_ready() -> bool:
    return _client is not None


async def close_cohere() -> None:
    global _client
    _client = None


def _as_ranked(
    candidate: ChunkCandidate, score: float, score_source: str = "cohere",
) -> RankedChunk:
    return RankedChunk(
        chunk_id=candidate.chunk_id,
        content=candidate.content,
        reference=candidate.reference,
        collection=candidate.collection,
        document_id=candidate.document_id,
        document_title=candidate.document_title,
        author=candidate.author,
        reranker_score=score,
        include=score >= settings.cohere_include_floor,
        anchor=candidate.anchor,
        position=candidate.position,
        annotation=candidate.annotation,
        score_source=score_source,
    )


def _fallback_ranked(candidates: list[ChunkCandidate]) -> list[RankedChunk]:
    """RRF order with synthetic scores, for a collection Cohere failed on.

    These scores are NOT relevance measurements — nothing scored these candidates.
    They sit in a deliberately modest band starting at `cohere_fallback_score_base`
    (0.40 by default): above the include floors so a failed collection is still
    represented rather than vanishing, but below the 0.6-0.9 a genuinely strong
    Cohere match earns, so an unreranked collection cannot outrank reranked ones.

    An earlier version started at 0.99 and claimed in this docstring that it
    therefore could not outrank a real score. That was wrong — real scores are
    routinely well below 0.99 — and the effect was that the single collection which
    failed to be reranked sorted to the top of the results, i.e. ranked better for
    having failed. The scores also reach the UI and `retrievals.reranker_score`, so
    0.99 was rendered to users as "99% relevance" for an unranked passage.
    """
    base = settings.cohere_fallback_score_base
    return [
        _as_ranked(c, max(0.0, base - i * 0.01), "rrf_fallback")
        for i, c in enumerate(candidates)
    ]


def _billed_units(response) -> tuple[int, bool]:
    """Read billed search units off the response, defaulting to 1.

    A call can bill several units (documents over 500 tokens split into chunks that
    each count toward the 100-per-unit limit), so the real number matters for cost
    comparisons between per-collection and global shapes.
    """
    try:
        units = response.meta.billed_units.search_units
    except AttributeError:
        return 1, False
    if units is None:
        return 1, False
    return max(1, int(units)), True


async def _rerank_one_collection(
    collection: str,
    candidates: list[ChunkCandidate],
    query: str,
    cost_tracker: CostTracker,
    semaphore: asyncio.Semaphore,
) -> list[RankedChunk]:
    if not candidates:
        return []

    query_tokens = budget.estimate_tokens(query)
    documents = [cohere_document(c) for c in candidates]
    doc_sizes = [budget.estimate_tokens(d) for d in documents]
    pool = budget.cohere_pool(doc_sizes, query_tokens)

    sent = candidates[:pool]
    sent_docs = documents[:pool]
    logger.info(
        "rerank_cohere: collection=%s candidates=%d sent=%d est_chunks=%d",
        collection, len(candidates), len(sent),
        sum(budget.billing_chunks(t, query_tokens) for t in doc_sizes[:pool]),
    )

    async with semaphore:
        response = await _rerank_with_retry(
            model="rerank-v4.0-pro",
            query=query,
            documents=sent_docs,
            top_n=len(sent_docs),
            max_tokens_per_doc=settings.cohere_max_tokens_per_doc,
        )

    units, billing_reliable = _billed_units(response)
    cost_tracker.record_cohere("rerank_cohere", units)
    logger.info("rerank_cohere: collection=%s billed_search_units=%d", collection, units)
    if not billing_reliable:
        degradation.record(
            "rerank_cohere", "billing_metadata_missing", "cost_estimated",
            scope=collection,
        )
    elif units > 1:
        degradation.record(
            "rerank_cohere", "packing_exceeded_one_unit", "actual_cost_recorded",
            scope=collection, details={"billed_search_units": units, "sent": len(sent)},
        )

    score_map = {r.index: r.relevance_score for r in response.results}
    ranked = [_as_ranked(c, score_map.get(i, 0.0)) for i, c in enumerate(sent)]
    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return ranked


async def run_per_collection(
    candidates: dict[str, list[ChunkCandidate]],
    query: str,
    quota: int,
    cost_tracker: CostTracker,
) -> dict[str, list[RankedChunk]]:
    """Rerank each collection in its own Cohere call; returns per-collection lists.

    Per-collection rather than flat so the caller can slice `quota` (terminal) or
    `quota + extra` (feeding an LLM reranker) independently per collection.
    """
    active = {c: cands for c, cands in candidates.items() if cands}
    if not active:
        return {}

    if _client is None:
        # A missing or temporarily unavailable optional reranker must not erase a
        # healthy retrieval result. Preserve each collection's RRF order and let
        # the terminal LLM reranker improve it when that stage is configured.
        logger.error(
            "rerank_cohere: client not initialized — using RRF fallback for %d collections",
            len(active),
        )
        out: dict[str, list[RankedChunk]] = {}
        for col, col_candidates in active.items():
            degradation.record(
                "rerank_cohere",
                "client_not_initialized",
                "rrf_fallback_used",
                scope=col,
                details={"hint": "Set COHERE_API_KEY to enable Cohere reranking."},
            )
            out[col] = _fallback_ranked(col_candidates)
        return out

    semaphore = asyncio.Semaphore(settings.cohere_concurrency)
    cols = list(active)
    results = await asyncio.gather(
        *[
            _rerank_one_collection(c, active[c], query, cost_tracker, semaphore)
            for c in cols
        ],
        return_exceptions=True,
    )

    out: dict[str, list[RankedChunk]] = {}
    for col, result in zip(cols, results):
        if isinstance(result, BaseException):
            # Degrade this collection to RRF order rather than losing the query.
            logger.warning(
                "rerank_cohere: collection=%s failed (%s) — falling back to RRF order",
                col, result,
            )
            degradation.record(
                "rerank_cohere", type(result).__name__, "rrf_fallback_used",
                scope=col, details={"message": str(result)[:300]},
            )
            out[col] = _fallback_ranked(active[col])
        else:
            out[col] = result
    return out
