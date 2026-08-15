"""Rerank dispatcher: composes Cohere and/or an LLM reranker per pipeline config.

Three modes, selected by which rerankers a pipeline enables:

- `cohere_only`  — Cohere per collection, keep top `quota`. Terminal.
- `llm_only`     — structured pointwise LLM, one call per collection. Candidate
                   sizing is historical, but the output contract is versioned and
                   must not be compared across the structured-output rollout as if
                   it were an unchanged experimental baseline.
- `both`         — Cohere per collection keeping `quota + extra`, merged and trimmed
                   to a global cap, then ONE listwise LLM call over the whole pool.

`both` returns two lists. The second is every Cohere-scored candidate, which
`collection_guarantee` needs: it injects a result for any selected collection missing
after dedup, and a collection whose candidates all fell below the keep floor
contributes nothing to the listwise pool. Handing the guarantee only the pool would
silently disable it for exactly the weak collections it exists to protect.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings
from app.rag.steps import budget, degradation, rerank_cohere
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import listwise, pointwise
from app.rag.steps.llm_rerank.openai_provider import PROVIDER as LUNA_PROVIDER
from app.rag.steps.rerank_haiku import PROVIDER as HAIKU_PROVIDER
from app.rag.steps.types import ChunkCandidate, RankedChunk

logger = logging.getLogger(__name__)

# Pipeline names remain stable API, but earlier free-text UUID runs are a different
# methodology and must be segmented in evaluation/reporting.
LLM_RERANK_CONTRACT_VERSION = "structured-positional-v1"

# Each provider instance is owned by the module that owns its client, so there is
# exactly one client per API and one place it is initialised. See
# rerank_haiku._HaikuClientProvider for why Haiku's lives outside llm_rerank/.
PROVIDERS = {
    HAIKU_PROVIDER.name: HAIKU_PROVIDER,
    LUNA_PROVIDER.name: LUNA_PROVIDER,
}


@dataclass(frozen=True)
class RerankConfig:
    """Which rerankers a pipeline runs.

    `use_cohere=False, llm_provider=None` would mean no reranking at all, which
    would return raw RRF order as if it had been scored — rejected at construction
    rather than silently degrading.
    """

    use_cohere: bool
    llm_provider: str | None

    def __post_init__(self) -> None:
        if not self.use_cohere and self.llm_provider is None:
            raise ValueError(
                "RerankConfig must enable Cohere, an LLM provider, or both — "
                "no-reranker configurations are not valid."
            )
        if self.llm_provider is not None and self.llm_provider not in PROVIDERS:
            raise ValueError(
                f"Unknown llm_provider {self.llm_provider!r}. "
                f"Valid: {sorted(PROVIDERS)}"
            )

    @property
    def mode(self) -> str:
        if self.use_cohere and self.llm_provider:
            return "both"
        return "cohere_only" if self.use_cohere else "llm_only"


def _llm_pool_from(
    per_collection: dict[str, list[RankedChunk]], quota: int
) -> list[RankedChunk]:
    """Slice each collection to quota+extra above the keep floor, then trim globally.

    The returned pool is sorted globally by score. That matters because it is also
    what `listwise.rerank_pool` returns on any failure, and `dedup`, `quota_cap` and
    `min_floor` all document that their input is score-sorted descending — building
    it collection-by-collection would hand them a list grouped by collection, and
    each would then keep the wrong chunks without any error.
    """
    keep = budget.cohere_keep(quota, with_llm=True)
    kept: dict[str, list[RankedChunk]] = {}
    for col, ranked in per_collection.items():
        eligible = [
            r for r in ranked if r.reranker_score >= settings.cohere_keep_score_floor
        ]
        if eligible:
            kept[col] = eligible[:keep]
        elif ranked:
            # Seat the collection's best candidate in the terminal listwise call even
            # below the Cohere keep floor. This lets collection_guarantee operate
            # entirely on terminal-reranker scores rather than injecting a Cohere
            # score into an LLM-scored global ranking.
            kept[col] = ranked[:1]

    allocation = budget.llm_pool({c: len(v) for c, v in kept.items()})
    pool: list[RankedChunk] = []
    for col, n in allocation.items():
        pool.extend(kept[col][:n])
    pool.sort(key=lambda r: r.reranker_score, reverse=True)
    logger.info(
        "rerank: llm pool=%d from %d collection(s) (allocation=%s)",
        len(pool), len(allocation), allocation,
    )
    return pool


def _all_scored_for_guarantee(
    per_collection: dict[str, list[RankedChunk]],
    llm_ranked: list[RankedChunk],
) -> list[RankedChunk]:
    """Candidates eligible for guarantee, all on the terminal LLM score scale.

    ``_llm_pool_from`` seats at least one candidate from every active collection, so
    there is no need to expose never-pooled Cohere scores to the global guarantee.
    """
    return list(llm_ranked)


async def run(
    config: RerankConfig,
    candidates: dict[str, list[ChunkCandidate]],
    query: str,
    quota: int,
    cost_tracker: CostTracker,
) -> tuple[list[RankedChunk], list[RankedChunk]]:
    """Rerank per `config`.

    Returns `(ranked, all_scored)`. `ranked` drives ordering and dedup; `all_scored`
    is the widest scored set available, for `collection_guarantee`. They are the same
    list except in `both` mode.
    """
    mode = config.mode

    if mode == "llm_only":
        provider = PROVIDERS[config.llm_provider]
        # Preserve historical candidate sizing for continuity. Scoring/output uses
        # LLM_RERANK_CONTRACT_VERSION and is not methodologically interchangeable
        # with runs from the former free-text UUID contract.
        max_per_col = quota * settings.candidate_multiplier
        import asyncio

        results = await asyncio.gather(
            *[
                pointwise.rerank_collection(
                    col_cands[:max_per_col], query, quota, cost_tracker, provider,
                    step=f"rerank_{provider.name}",
                )
                for col_cands in candidates.values()
            ],
            return_exceptions=True,
        )
        ranked: list[RankedChunk] = []
        for collection, result in zip(candidates, results):
            if isinstance(result, BaseException):
                logger.warning("rerank: collection failed: %s", result)
                degradation.record(
                    f"rerank_{provider.name}",
                    type(result).__name__,
                    "collection_omitted",
                    scope=collection,
                    details={"message": str(result)[:300]},
                )
            else:
                ranked.extend(result)
        ranked.sort(key=lambda r: r.reranker_score, reverse=True)
        return ranked, ranked

    per_collection = await rerank_cohere.run_per_collection(
        candidates, query, quota, cost_tracker,
    )
    all_scored = [c for chunks in per_collection.values() for c in chunks]
    all_scored.sort(key=lambda r: r.reranker_score, reverse=True)

    if mode == "cohere_only":
        # Return every scored candidate, NOT a quota slice. dedup (cosine + a 2-per
        # -title cap) and quota_cap run downstream and can only shrink the list, so
        # slicing to quota here would structurally under-deliver: measured, 6 scored
        # bible chunks clustered in 2 documents yielded 4 final results unsliced and
        # only 2 when sliced to quota first. quota_cap applies the real per-collection
        # limit after dedup has had candidates to work with.
        return all_scored, all_scored

    # both
    pool = _llm_pool_from(per_collection, quota)
    provider = PROVIDERS[config.llm_provider]
    ranked = await listwise.rerank_pool(
        pool, query, cost_tracker, provider, step=f"rerank_listwise_{provider.name}",
    )
    return ranked, _all_scored_for_guarantee(per_collection, ranked)
