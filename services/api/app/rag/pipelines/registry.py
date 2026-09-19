# services/api/app/rag/pipelines/registry.py
"""Named pipeline configurations.

Naming: `<hyde|nohyde>[_nolex]_<rerank>[_rrf<k>]`. Three axes are configured here —
which retrieval paths run, which rerankers, and how the paths are fused — so
`compare/` can A/B any two by name.

Enrichment is deliberately NOT an axis: whether a candidate has an annotation is a
property of the data, checked per candidate, so a single query spanning enriched and
unenriched collections works without a separate pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.rag.steps.rerank import RerankConfig


@dataclass(frozen=True)
class RetrievalConfig:
    """Which retrieval paths contribute candidate lists to RRF.

    `fts` exists to answer one question — how much does the lexical path contribute?
    — which is what should decide whether the Qdrant sparse-BM25 migration (a named-
    vector schema change plus a full corpus re-embed) is worth doing. It is an
    ablation control, not a production option.
    """

    hyde: bool = True
    fts: bool = True
    # Pin the per-strategy retrieval limit instead of deriving it from the active
    # path count. Only for controlled ablations: `retrieval_k` scales k up when a
    # path is removed (3 paths -> k=50, 2 paths -> k=60), so a no-FTS pipeline would
    # also search each remaining dense path 20% deeper — changing two variables and
    # measuring neither. Pinning k to the control's value isolates the FTS effect.
    retrieval_k_override: int | None = None
    # Rank-bias constant for the RRF merge. None uses `settings.rrf_k`. Per-pipeline
    # so two arms can differ in k alone: k decides the rank at which agreement
    # between paths stops beating one path's precision, and that trade-off was
    # picked by reasoning, never measured. Carried on the config (rather than read
    # from settings inside the step) so `dataclasses.asdict` puts it in the
    # methodology fingerprint automatically and the two arms stay segmentable.
    rrf_k: int | None = None


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    retrieval: RetrievalConfig
    rerank: RerankConfig


def _p(name: str, *, hyde: bool = True, fts: bool = True,
       cohere: bool = False, llm: str | None = None,
       k: int | None = None, rrf_k: int | None = None) -> PipelineConfig:
    return PipelineConfig(
        name=name,
        retrieval=RetrievalConfig(
            hyde=hyde, fts=fts, retrieval_k_override=k, rrf_k=rrf_k,
        ),
        rerank=RerankConfig(use_cohere=cohere, llm_provider=llm),
    )


PIPELINES: dict[str, PipelineConfig] = {
    # Structured pointwise control. Name retained for API compatibility; comparisons
    # must segment across the structured-output contract rollout.
    "hyde_haiku":          _p("hyde_haiku", llm="haiku"),
    "nohyde_haiku":        _p("nohyde_haiku", hyde=False, llm="haiku"),
    # Same shape, Luna instead of Haiku.
    "hyde_luna":           _p("hyde_luna", llm="luna"),
    # Cohere alone, terminal.
    "hyde_cohere":         _p("hyde_cohere", cohere=True),
    "nohyde_cohere":       _p("nohyde_cohere", hyde=False, cohere=True),
    # Cohere per collection -> one global listwise LLM call.
    "hyde_cohere_haiku":   _p("hyde_cohere_haiku", cohere=True, llm="haiku"),
    "hyde_cohere_luna":    _p("hyde_cohere_luna", cohere=True, llm="luna"),
    "nohyde_cohere_haiku": _p("nohyde_cohere_haiku", hyde=False, cohere=True, llm="haiku"),
    # Fusion ablation: `hyde_luna` at the pre-#101 k of 60, to settle 60 -> 20 on
    # evidence. Paired with `hyde_luna` because `llm_only` is where k bites hardest
    # — `_pool_sizes` returns (None, None) there, so top_n drops to
    # `quota * candidate_multiplier` and RRF actually truncates. In the Cohere arms
    # the reranker rescores every survivor, which washes most of the difference out.
    "hyde_luna_rrf60":     _p("hyde_luna_rrf60", llm="luna", rrf_k=60),
    # Lexical ablation: dense-only retrieval, to measure what FTS contributes.
    # k pinned to what hyde_cohere_haiku (its control) derives, so the only
    # difference between the two is the presence of the FTS path.
    "hyde_nolex_cohere_haiku": _p(
        "hyde_nolex_cohere_haiku", fts=False, cohere=True, llm="haiku", k=50,
    ),
}
