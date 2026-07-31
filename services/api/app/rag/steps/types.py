from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChunkCandidate:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    rrf_score: float
    anchor: str | None = None
    position: int | None = None
    # jsonb in Postgres, but the stored value is a JSON-encoded *string* (see
    # datapipeline enrich_io.py) and app/db.py registers a jsonb codec, so this
    # decodes to the annotation prose itself — not a dict.
    annotation: str | None = None


@dataclass
class RankedChunk:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    reranker_score: float
    include: bool = True
    anchor: str | None = None
    position: int | None = None
    # Carried through reranking so a second-stage reranker still sees it (the
    # listwise card needs it). Same decoded-string shape as ChunkCandidate's.
    annotation: str | None = None
    # Provenance for interpreting reranker_score. ``rrf_fallback`` is an ordering
    # surrogate, not a measured relevance score, and must not be shown as confidence.
    score_source: str = "unknown"


@dataclass
class StepTiming:
    step: str
    duration_s: float


@dataclass
class PipelineResult:
    pipeline: str
    chunks: list[RankedChunk]
    step_timings: list[StepTiming]
    total_duration_s: float
    cost_breakdown: dict[str, float]
    total_cost: float
    # Wall-clock seconds during which at least one Cohere call was throttled or
    # backing off (overlapping concurrent waits are merged, not summed).
    # This time is INSIDE total_duration_s and inside the `rerank` step timing, so
    # any latency comparison taken while rate-limited must subtract it — otherwise a
    # throttled key makes a pipeline look slow for reasons that vanish on a
    # production key. See rerank_cohere.begin_throttle_accounting.
    throttle_wait_s: float = 0.0
    # Rerank stages that silently fell back (e.g. "cohere:summa",
    # "rerank_listwise_luna:parse_failed"). Non-empty means at least part of the
    # rerank never ran, so this query's quality and timing are not comparable with a
    # healthy one — the cost breakdown cannot reveal this on its own.
    degradations: list[str] = field(default_factory=list)
    # Structured form used by telemetry and evaluation eligibility decisions.
    degradation_events: list[dict] = field(default_factory=list)
    # Transient malformed output, throttling, or other defects repaired before a
    # fallback was needed. These remain quality-eligible but are important for
    # production reliability and tail-latency monitoring.
    recovery_events: list[dict] = field(default_factory=list)
    # A degraded result remains usable in production but must not enter a quality
    # aggregate as if every configured stage ran successfully.
    quality_eligible: bool = True
    latency_eligible: bool = True
    # User-facing terminal classification. The frontend must never infer this
    # merely from chunks == [] because infrastructure failures can also be empty.
    outcome: str = "success"
    # Per requested collection: results | results_degraded | no_candidates |
    # below_threshold | retrieval_failed | corpus_sync_failed | ranking_failed.
    collection_outcomes: dict[str, str] = field(default_factory=dict)
