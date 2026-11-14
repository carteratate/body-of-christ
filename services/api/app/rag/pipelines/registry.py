# services/api/app/rag/pipelines/registry.py
"""Named pipeline configurations.

Naming:
`<hyde|nohyde|hyde6>[_nolex]_<rerank>[_rrf<k>][_seats<min>[t<total>]][_ftsminmatch]`.
The axes configured here — which retrieval paths run and how keyword search matches,
which rerankers (and, for Luna, which model and reasoning effort), how the paths are
fused, and how many candidates reach the terminal listwise call — let the eval harness (`scripts/run_eval_suite.py`) A/B
any two by name.

Enrichment is deliberately NOT an axis: whether a candidate has an annotation is a
property of the data, checked per candidate, so a single query spanning enriched and
unenriched collections works without a separate pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.rag.steps.budget import TerminalSeats
from app.rag.steps.retrieve_fts import FTS_MODES, FtsMode
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
    # Evaluation-arm overrides for the Luna HyDE calls. None means the production
    # default (`settings.hyde_luna_model` / `settings.hyde_genre_luna_model`). They
    # apply only when the corresponding provider setting is "luna".
    hyde_luna_model: str | None = None
    hyde_genre_luna_model: str | None = None
    # Which independent HyDE draw an arm uses in shared evaluation. HyDE is
    # sampled, so two arms that differ only here measure HyDE's own run-to-run
    # noise: the floor a HyDE-model change has to clear. No effect on live search,
    # where every run samples fresh.
    hyde_sample: int = 0
    # How the question is matched against `search_vector` (issue #233; modes in
    # `retrieve_fts`). "and" is today's plainto_tsquery, which finds nothing for
    # most questions; "min_match" keeps passages holding at least half the terms.
    fts_mode: FtsMode = "and"

    def __post_init__(self) -> None:
        # `settings.rrf_k` is validated by pydantic and no request field reaches
        # rrf_k, so a hand-edited literal here is the only way a bad value gets in
        # — and it fails silently: `_rrf_merge` takes a per-family `max` against
        # 0.0, so a negative k clamps every score to zero and leaves the ordering
        # arbitrary rather than raising. Guarded because the person pinning k is
        # running an ablation, and would read that as a result.
        if self.rrf_k is not None and self.rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {self.rrf_k}")
        if self.fts_mode not in FTS_MODES:
            raise ValueError(f"unknown fts_mode {self.fts_mode!r}")


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    retrieval: RetrievalConfig
    rerank: RerankConfig


def _p(name: str, *, hyde: bool = True, fts: bool = True,
       cohere: bool = False, llm: str | None = None,
       k: int | None = None, rrf_k: int | None = None,
       hyde_model: str | None = None, genre_model: str | None = None,
       hyde_sample: int = 0, fts_mode: FtsMode = "and",
       llm_model: str | None = None, effort: str | None = None,
       seats: TerminalSeats | None = None) -> PipelineConfig:
    return PipelineConfig(
        name=name,
        retrieval=RetrievalConfig(
            hyde=hyde, fts=fts, retrieval_k_override=k, rrf_k=rrf_k,
            hyde_luna_model=hyde_model, hyde_genre_luna_model=genre_model,
            hyde_sample=hyde_sample, fts_mode=fts_mode,
        ),
        rerank=RerankConfig(
            use_cohere=cohere, llm_provider=llm,
            llm_model=llm_model, llm_reasoning_effort=effort,
            terminal_seats=seats,
        ),
    )


# Every pipeline runs Cohere, alone or followed by one listwise LLM call. The
# single-stage LLM arms (`hyde_haiku`, `nohyde_haiku`, `hyde_luna`, and the RRF-k
# ablation `hyde_luna_rrf60` built on them) were removed in October 2026 with the
# pointwise reranker; `rrf_k` stays an axis any Cohere arm can pin.
PIPELINES: dict[str, PipelineConfig] = {
    # Cohere alone, terminal.
    "hyde_cohere":         _p("hyde_cohere", cohere=True),
    "nohyde_cohere":       _p("nohyde_cohere", hyde=False, cohere=True),
    # Cohere per collection -> one global listwise LLM call.
    "hyde_cohere_haiku":   _p("hyde_cohere_haiku", cohere=True, llm="haiku"),
    "hyde_cohere_luna":    _p("hyde_cohere_luna", cohere=True, llm="luna"),
    "nohyde_cohere_haiku": _p("nohyde_cohere_haiku", hyde=False, cohere=True, llm="haiku"),
    # Lexical ablation: dense-only retrieval, to measure what FTS contributes.
    # k pinned to what hyde_cohere_haiku (its control) derives, so the only
    # difference between the two is the presence of the FTS path.
    "hyde_nolex_cohere_haiku": _p(
        "hyde_nolex_cohere_haiku", fts=False, cohere=True, llm="haiku", k=50,
    ),
    # Luna-model arms, each against `hyde_cohere_luna`. Production and its HyDE-
    # sample twin deliberately read the deployment's settings — they ARE production.
    # Every other arm pins each Luna model and effort it runs, so its meaning does
    # not move if a deployment default changes.
    # HyDE noise floor: production, but its own HyDE draw.
    "hyde_cohere_luna_hydesample": _p(
        "hyde_cohere_luna_hydesample", cohere=True, llm="luna", hyde_sample=1,
    ),
    # HyDE passages on 6; genre pick and reranker held at today's production values.
    "hyde6_cohere_luna": _p(
        "hyde6_cohere_luna", cohere=True, llm="luna", hyde_model="gpt-6-luna",
        genre_model="gpt-5.6-luna", llm_model="gpt-5.6-luna", effort="medium",
    ),
    # Everything on 6: passages, genre pick, and the reranker at medium / at low.
    "hyde6_cohere_luna6": _p(
        "hyde6_cohere_luna6", cohere=True, llm="luna", hyde_model="gpt-6-luna",
        genre_model="gpt-6-luna", llm_model="gpt-6-luna", effort="medium",
    ),
    "hyde6_cohere_luna6_low": _p(
        "hyde6_cohere_luna6_low", cohere=True, llm="luna", hyde_model="gpt-6-luna",
        genre_model="gpt-6-luna", llm_model="gpt-6-luna", effort="low",
    ),
    # Issue #235: production's quota+3 keep and 40-seat cap leave about 4-6 Cohere
    # candidates per collection for the listwise ranker on a 6-10 collection search.
    # seats10t80 is the chosen candidate: 80 seats split across the collections,
    # 10 to 25 each (1-3 collections: 25, 6: 13, 8-10: 10). seats10 is the fixed
    # comparison. In the depth study seats10t80 seated 89% of the deep run's final
    # picks and seats10 87%, against production's 65%. The study seated at most 16
    # per collection, so the 17-25 seats given to 1-3 collection searches are
    # unmeasured (and cheap: such pools stayed near 25 under the 0.30 keep floor).
    "hyde_cohere_luna_seats10": _p(
        "hyde_cohere_luna_seats10", cohere=True, llm="luna",
        seats=TerminalSeats(minimum=10),
    ),
    "hyde_cohere_luna_seats10t80": _p(
        "hyde_cohere_luna_seats10t80", cohere=True, llm="luna",
        seats=TerminalSeats(minimum=10, total=80, maximum=25),
    ),
    # Production (seats10t80) with its own HyDE draw: the noise floor any change to
    # production must clear. hyde_cohere_luna_hydesample is the pre-#235 equivalent.
    "hyde_cohere_luna_seats10t80_hydesample": _p(
        "hyde_cohere_luna_seats10t80_hydesample", cohere=True, llm="luna",
        seats=TerminalSeats(minimum=10, total=80, maximum=25), hyde_sample=1,
    ),
    # Issue #233: production with keyword search matching at least half a question's
    # terms instead of all of them, against production and its noise floor above.
    "hyde_cohere_luna_seats10t80_ftsminmatch": _p(
        "hyde_cohere_luna_seats10t80_ftsminmatch", cohere=True, llm="luna",
        seats=TerminalSeats(minimum=10, total=80, maximum=25), fts_mode="min_match",
    ),
}
