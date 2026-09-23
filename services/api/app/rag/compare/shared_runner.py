"""Controlled evaluation capture/replay for pipelines with shared retrieval.

The live product still uses ``pipelines.runner.run`` end to end. Evaluation captures
the expensive stochastic upstream work once, derives each configured candidate pool
from the same ranked retrieval lists, and replays only pipeline-specific reranking.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import time
from dataclasses import dataclass

from app.config import settings
from app.rag.pipelines.registry import PipelineConfig
from app.rag.pipelines.runner import _pool_sizes, hyde_overrides, run_from_candidates
from app.rag.steps import degradation, embed, fetch_positions, hyde_s25, retrieve_fts
from app.rag.steps import retrieve_vector, rrf
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import ChunkCandidate, PipelineResult, RetrievalPath


@dataclass
class SharedArtifacts:
    query: str
    collections: list[str]
    quota: int
    candidate_pools: dict[str, dict[str, list[ChunkCandidate]]]
    cost_breakdown: dict[str, float]
    total_cost: float
    duration_s: float
    degradations: list[str]
    degradation_events: list[dict]
    # Per pipeline, the cost of the HyDE draw its pool was built from. Draws are
    # shared between arms with the same HyDE config, so these do not sum to
    # `total_cost`; they exist so a HyDE-model arm's cost can be compared with
    # production's. Empty for artifacts captured before per-draw accounting.
    hyde_costs: dict[str, dict[str, float]] = dataclasses.field(default_factory=dict)

    @property
    def quality_eligible(self) -> bool:
        return not self.degradations

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "collections": self.collections,
            "quota": self.quota,
            "candidate_pools": {
                pipeline: {
                    collection: [dataclasses.asdict(c) for c in candidates]
                    for collection, candidates in pool.items()
                }
                for pipeline, pool in self.candidate_pools.items()
            },
            "cost_breakdown": self.cost_breakdown,
            "total_cost": self.total_cost,
            "duration_s": self.duration_s,
            "degradations": self.degradations,
            "degradation_events": self.degradation_events,
            "hyde_costs": self.hyde_costs,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SharedArtifacts":
        return cls(
            query=value["query"],
            collections=value["collections"],
            quota=value["quota"],
            candidate_pools={
                pipeline: {
                    collection: [ChunkCandidate(**candidate) for candidate in candidates]
                    for collection, candidates in pool.items()
                }
                for pipeline, pool in value["candidate_pools"].items()
            },
            cost_breakdown=value["cost_breakdown"],
            total_cost=value["total_cost"],
            duration_s=value["duration_s"],
            degradations=value.get("degradations", []),
            degradation_events=value.get("degradation_events", []),
            hyde_costs=value.get("hyde_costs", {}),
        )


async def capture(
    query: str,
    collections: list[str],
    quota: int,
    configs: list[PipelineConfig],
) -> SharedArtifacts:
    """Capture one healthy shared retrieval and derive every pipeline candidate pool."""
    tracker = CostTracker()
    degradation.begin_degradation_accounting(degradation.DegradationPolicy.QUARANTINE)
    started = time.perf_counter()

    sizes = {config.name: _pool_sizes(config, quota) for config in configs}
    effective_k = {
        name: k if k is not None else quota * settings.candidate_multiplier
        for name, (k, _top_n) in sizes.items()
    }
    max_k = max(effective_k.values())

    query_vec = await embed.run(query, tracker)

    # One HyDE capture per distinct HyDE configuration, so arms that pin different
    # HyDE models (or ask for an independent draw via `hyde_sample`) each retrieve
    # from their own passages, while arms that agree still share one capture and
    # differ only downstream. With default configs this is a single call, made
    # exactly as before.
    HydeKey = tuple[str | None, str | None, int]

    def hyde_key(config: PipelineConfig) -> HydeKey:
        r = config.retrieval
        return (r.hyde_luna_model, r.hyde_genre_luna_model, r.hyde_sample)

    first_config: dict[HydeKey, PipelineConfig] = {}
    for config in configs:
        first_config.setdefault(hyde_key(config), config)
    # Each draw bills its own tracker, so the per-arm HyDE cost stays attributable.
    draw_trackers = {key: CostTracker() for key in first_config}

    async def draw(key: HydeKey) -> dict:
        hyde_vecs = await hyde_s25.run(
            query, collections, draw_trackers[key],
            **hyde_overrides(first_config[key].retrieval),
        )
        return await retrieve_vector.run(
            query_vec, hyde_vecs, collections, quota, k=max_k,
        )

    keys = list(first_config)
    # return_exceptions so a failing draw does not leave its siblings running
    # unobserved (and still spending) after the capture has already raised.
    draws = await asyncio.gather(*[draw(key) for key in keys], return_exceptions=True)
    for key in keys:
        tracker.merge(draw_trackers[key])
    for outcome in draws:
        if isinstance(outcome, BaseException):
            raise outcome
    vector_raw_by_hyde: dict[HydeKey, dict] = dict(zip(keys, draws))
    fts_raw = await retrieve_fts.run(query, collections, quota, k=max_k)

    # Keyed by every input that changes the merged pool. `rrf_k` belongs here for
    # the same reason `fts` does: two arms differing only in it produce differently
    # ordered merges, and reusing one pool for both would hand replay identical
    # candidates and silently compare an arm against itself. The HyDE key is here
    # for the same reason: a pool built from one arm's HyDE vectors must never be
    # replayed as another arm's.
    Shape = tuple[int, int | None, bool, int | None, HydeKey]
    pools_by_shape: dict[Shape, dict[str, list[ChunkCandidate]]] = {}
    candidate_pools: dict[str, dict[str, list[ChunkCandidate]]] = {}
    for config in configs:
        k = effective_k[config.name]
        _configured_k, top_n = sizes[config.name]
        shape = (
            k, top_n, config.retrieval.fts, config.retrieval.rrf_k, hyde_key(config),
        )
        if shape not in pools_by_shape:
            vector_raw = vector_raw_by_hyde[hyde_key(config)]
            vectors = {
                collection: [RetrievalPath(path.family, path.rows[:k]) for path in strategies]
                for collection, strategies in vector_raw.items()
            }
            lexical = (
                {collection: ranked[:k] for collection, ranked in fts_raw.items()}
                if config.retrieval.fts else {}
            )
            merged = rrf.run(vectors, lexical, quota, top_n=top_n, k=config.retrieval.rrf_k)
            pools_by_shape[shape] = await fetch_positions.run(merged)
        candidate_pools[config.name] = copy.deepcopy(pools_by_shape[shape])

    return SharedArtifacts(
        query=query,
        collections=list(collections),
        quota=quota,
        candidate_pools=candidate_pools,
        cost_breakdown=tracker.breakdown(),
        total_cost=tracker.total_cost(),
        duration_s=time.perf_counter() - started,
        degradations=degradation.degradations(),
        degradation_events=degradation.event_dicts(),
        hyde_costs={
            config.name: draw_trackers[hyde_key(config)].breakdown() for config in configs
        },
    )


async def replay(
    artifacts: SharedArtifacts,
    configs: list[PipelineConfig],
) -> list[PipelineResult]:
    """Run each configured reranker against its deterministic captured candidate pool."""
    results: list[PipelineResult] = []
    for config in configs:
        results.append(await run_from_candidates(
            config,
            artifacts.candidate_pools[config.name],
            artifacts.query,
            artifacts.collections,
            artifacts.quota,
            degradation_policy=degradation.DegradationPolicy.QUARANTINE,
        ))
    return results
