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
    chapter_key: str | None = None
    position: int | None = None
    # jsonb in Postgres, but the stored value is a JSON-encoded *string* (see
    # datapipeline enrich_io.py) and app/db.py registers a jsonb codec, so this
    # decodes to the annotation prose itself — not a dict.
    annotation: str | None = None
    # The passage's role within its document — "Objection 1", "Reply to Objection 2",
    # "I answer that", "Can. 1055 §1". Carried because a fragment's role can invert
    # its meaning: 39.3% of the Summa is objections Aquinas states in order to REFUTE,
    # and without this the reranker sees only "It would seem that..." with nothing
    # marking it. Sourced from the Qdrant payload or backfilled by fetch_positions.
    unit_label: str | None = None


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
    chapter_key: str | None = None
    position: int | None = None
    # Carried through reranking so a second-stage reranker still sees it (the
    # listwise card needs it). Same decoded-string shape as ChunkCandidate's.
    annotation: str | None = None
    # Carried through reranking for the same reason as `annotation`: the listwise
    # card and the result UI both need the passage's role. See ChunkCandidate.
    unit_label: str | None = None
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
    # Appended to preserve positional compatibility for external dataclass callers.
    # None means the row predates contract versioning (before 2026-08-20). It does
    # NOT mean Cohere-only: since COHERE_RERANK_CONTRACT_VERSION was added, a
    # cohere_only pipeline reports that instead, and rerank.contract_version()'s
    # remaining None branch is unreachable (RerankConfig rejects no-reranker configs).
    rerank_contract_version: str | None = None
    # Appended to preserve positional compatibility. False means total_cost is
    # incomplete and must not enter persisted or aggregate cost comparisons.
    cost_eligible: bool = True
    # Appended for the same reason. Presentation attached to `chunks`, keyed by
    # chunk_id. NOT results in their own right — fetched after quota_cap so they never
    # consume a result slot — and kept separate so `chunks` stays exactly what was
    # scored, persisted, bookmarked and given feedback on.
    context: dict[str, "AttachedContext"] = field(default_factory=dict)


@dataclass
class AttachedContext:
    """The passage that makes a matched Summa result intelligible.

    `relation` says what the attached passage IS relative to the match, so a renderer
    never infers placement from a label:

      answered_by  the match is an objection; these parts are Aquinas's answer  -> below
      answers      the match is a reply; this part is the objection it answers  -> above

    See `app.rag.steps.stitch` for why the two roles need different passages.
    """

    relation: str
    parts: list[RankedChunk]
