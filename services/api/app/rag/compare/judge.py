"""LLM-as-judge scoring using Claude Opus 5 with a five-dimension rubric."""
from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass, field

import anthropic

from app.config import settings
from app.rag.compare.overlap import OverlapReport
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import PipelineResult

logger = logging.getLogger(__name__)

# Opus 5 as judge: this is the model that decides which retrieval strategy ships,
# so it gets the strongest available judgment. Note switching the judge model makes
# scores non-comparable with anything judged by a previous model — the model is
# recorded on every report and persisted row for exactly that reason.
_JUDGE_MODEL = "claude-opus-5"
_client: anthropic.AsyncAnthropic | None = None

# Must sum to 1.0 (asserted in tests). Weights are deliberately NOT fitted to
# observed spread — that would tune the ruler to the object being measured. They
# encode what the comparison is *for*:
#
#   best_passage_selection is raised because this is a RERANK comparison. Every
#     pipeline draws from a similar RRF pool; what differs is the ordering, and this
#     is the only dimension that measures ordering directly. It also has by far the
#     best signal-to-noise ratio measured across round 1 (between-pipeline sd 0.054
#     vs between-query sd 0.029 = 1.86x; retrieval_relevance is 0.78x, i.e. query
#     difficulty moves it more than pipeline choice does).
#   multi_angle_coverage is cut because it rewards breadth while result-set size
#     varies structurally by mode (12.6 vs ~15.6 results in round 1), so part of its
#     variance is a confound rather than quality. It is kept non-zero because it
#     still guards a real failure mode: every result making the same point.
#
# Changing these does NOT invalidate past runs: per-dimension scores are persisted,
# so any stored run can be re-scored under current weights (scripts/analyze_eval.py
# does exactly that). Round 1 was scored under 0.30/0.20/0.20/0.15/0.15; re-scoring
# it under these weights left the pipeline ordering unchanged.
WEIGHTS: dict[str, float] = {
    "retrieval_relevance":    0.35,
    "best_passage_selection": 0.25,
    "multi_angle_coverage":   0.10,
    "doctrinal_completeness": 0.15,
    "redundancy_rate":        0.15,
}


def compute_weighted_total(dimension_scores: dict[str, float]) -> float:
    return round(sum(dimension_scores[dim] * weight for dim, weight in WEIGHTS.items()), 4)


@dataclass
class DimensionScore:
    score: float
    reasoning: str


@dataclass
class JudgeScore:
    pipeline: str
    dimensions: dict[str, DimensionScore]
    weighted_total: float
    summary: str


@dataclass
class JudgeReport:
    scores: list[JudgeScore]
    comparative_analysis: str
    tokens_used: int
    cost: float
    model: str
    # Order the pipelines were presented to the judge, first to last. Randomised per
    # call; recorded so a narrow score margin can be weighed against position bias.
    presentation_order: list[str] = field(default_factory=list)
    valid: bool = True
    error: str | None = None


_JUDGE_SYSTEM = (
    "You are evaluating Catholic theology RAG pipeline results. For each pipeline, "
    "score five dimensions of retrieval quality. For EACH dimension: reason through "
    "what you observe in the result set first, then assign a score 0.0–1.0. "
    "Your score must follow your reasoning — do not assign a number and then justify it.\n\n"
    "---\n\n"
    "DIMENSION 1: RETRIEVAL RELEVANCE\n"
    "How directly each chunk addresses the specific concept asked about, not just whether "
    "it shares vocabulary or a broad theme. Catholic theological vocabulary overlaps heavily "
    "between unrelated doctrines — the most common failure is a 'vocabulary collision': a "
    "passage about a different doctrine that happens to use the same keywords.\n\n"
    "Anchors:\n"
    "1.0 — Every chunk directly engages the specific concept asked about. No vocabulary collisions.\n"
    "  Example: Query 'what is purgatory?' → all chunks explicitly address purgatory as a "
    "doctrine of final purification.\n"
    "0.5 — Most chunks are on-topic; one or two share vocabulary with the query but address "
    "something adjacent.\n"
    "  Example: Query 'what is purgatory?' → four good chunks, one is a psalm about "
    "suffering/refinement used metaphorically.\n"
    "0.0 — One or more chunks are a different doctrine entirely — a vocabulary collision. "
    "The rest may be fine.\n"
    "  Example: Query 'what is the Immaculate Conception?' → a chunk about the Virgin Birth "
    "appears; a different doctrine that shares the word 'conception.'\n\n"
    "---\n\n"
    "DIMENSION 2: BEST-PASSAGE SELECTION\n"
    "When a collection is relevant to the query, did the pipeline find its canonical answer "
    "passages — the section where the collection treats the topic most directly and "
    "substantively — or only peripheral mentions? Score per collection that appears in "
    "results; average across them.\n\n"
    "Anchors:\n"
    "1.0 — For each relevant collection, the pipeline found its canonical answer passage.\n"
    "  Example: Query 'what does the Church teach about the Trinity?' → Catechism chunk is "
    "CCC §253–267, the specific Trinitarian dogma section.\n"
    "0.5 — Relevant collections are represented but passages are mid-tier — thematically "
    "related sections rather than the core treatment.\n"
    "  Example: Same query → Catechism chunk is from a baptismal formula section that "
    "mentions the Trinity in passing.\n"
    "0.0 — A clearly relevant collection appears only via a peripheral mention; the corpus "
    "obviously has far better passages that were not found.\n"
    "  Example: Same query → Catechism chunk is 'we pray to the Father, through the Son, "
    "in the Holy Spirit' with no doctrinal explanation.\n\n"
    "---\n\n"
    "DIMENSION 3: MULTI-ANGLE COVERAGE\n"
    "Does the result set approach the question from genuinely distinct kinds of sources? "
    "The applicable angles for this corpus are: scriptural foundation, "
    "systematic/philosophical reasoning, conciliar/magisterial definition, pastoral "
    "application, historical precedent. First identify which angles are applicable to this "
    "query type, then assess coverage only against those.\n\n"
    "Anchors:\n"
    "1.0 — Results span three or more meaningfully distinct applicable angles.\n"
    "  Example: Query 'why does suffering exist?' → scriptural (Job/Romans) + systematic "
    "(Aquinas on privation) + pastoral (Salvifici Doloris on redemptive suffering).\n"
    "0.5 — Two distinct angles covered; noticeably thin in at least one clearly applicable area.\n"
    "  Example: Same query → scriptural and pastoral covered; no systematic/philosophical "
    "treatment of theodicy despite Summa availability.\n"
    "0.0 — All results come from one angle.\n"
    "  Example: Same query → five Bible passages on suffering only; no Aquinas, no "
    "magisterial document, no pastoral guidance.\n\n"
    "---\n\n"
    "DIMENSION 4: DOCTRINAL COMPLETENESS\n"
    "Does the result set represent the full picture of Church teaching — both poles of a "
    "doctrine where tension exists — or only a one-sided slice? If a topic has no "
    "meaningful doctrinal tension, score 1.0 by default.\n\n"
    "Anchors:\n"
    "1.0 — Result set captures both the affirmation and the nuance; both poles of the "
    "doctrine where tension exists.\n"
    "  Example: Query 'does the Church teach only Catholics are saved?' → results include "
    "both the traditional formulation AND Vatican II's development in Lumen Gentium §16.\n"
    "0.5 — Dominant side of the doctrine is well-represented; the balancing pole is thin "
    "or absent.\n"
    "  Example: Same query → all traditional formulations with nothing from Vatican II.\n"
    "0.0 — Results represent only one pole, and the missing pole would substantially change "
    "how a user understands Church teaching.\n"
    "  Example: Query 'what does the Church teach about contraception?' → all passages are "
    "prohibitive; the positive theology of conjugal love in Humanae Vitae §§8–12 is "
    "entirely absent.\n\n"
    "---\n\n"
    "DIMENSION 5: REDUNDANCY RATE\n"
    "Are same-source chunks making the same substantive argument? Two different sources "
    "making similar arguments is NOT redundant — that is convergence across the tradition "
    "and is a positive signal. Penalize only same-source chunks that restate the same point.\n\n"
    "Anchors:\n"
    "1.0 — No two chunks from the same source make the same substantive argument.\n"
    "  Example: Five chunks from five documents, each adding distinct content even when "
    "covering related themes.\n"
    "0.5 — One pair of same-source chunks overlaps significantly in argument; other results "
    "are distinct.\n"
    "  Example: Two sections from Evangelium Vitae both arguing from natural law on the "
    "same point; other results are varied.\n"
    "0.0 — Multiple same-source chunks are essentially restating each other — wasted "
    "result slots.\n"
    "  Example: Three sections from Humanae Vitae all making the same "
    "contraception-as-intrinsically-disordered argument in slightly different phrasing.\n\n"
    "---\n\n"
    "RULES:\n"
    "- Score each dimension independently. Do not let your score on one dimension "
    "influence your score on another.\n"
    "- For Doctrinal Completeness: if the topic has no meaningful doctrinal tension, "
    "score 1.0 by default.\n"
    "- For Multi-angle Coverage: first identify which angles are applicable to this query "
    "type, then assess coverage only against those angles. Do not penalize absence of "
    "canon law in a devotional query.\n"
    "- For Redundancy Rate: two different sources making similar arguments is NOT redundant. "
    "Penalize only same-source chunks making the same argument.\n"
    "- For Retrieval Relevance: a single vocabulary collision (wrong doctrine retrieved) "
    "must pull the score below 0.5 regardless of how good the other chunks are.\n"
    "- Do NOT compute a weighted total. Return only per-dimension scores."
)

_TOOL = {
    "name": "score_pipelines",
    "description": "Return multi-dimensional retrieval quality scores for each pipeline.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pipeline_scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pipeline":                              {"type": "string"},
                        "retrieval_relevance_reasoning":         {"type": "string"},
                        "retrieval_relevance_score":             {"type": "number"},
                        "best_passage_selection_reasoning":      {"type": "string"},
                        "best_passage_selection_score":          {"type": "number"},
                        "multi_angle_coverage_reasoning":        {"type": "string"},
                        "multi_angle_coverage_score":            {"type": "number"},
                        "doctrinal_completeness_reasoning":      {"type": "string"},
                        "doctrinal_completeness_score":          {"type": "number"},
                        "redundancy_rate_reasoning":             {"type": "string"},
                        "redundancy_rate_score":                 {"type": "number"},
                        "summary":                              {"type": "string"},
                    },
                    "required": [
                        "pipeline",
                        "retrieval_relevance_reasoning", "retrieval_relevance_score",
                        "best_passage_selection_reasoning", "best_passage_selection_score",
                        "multi_angle_coverage_reasoning", "multi_angle_coverage_score",
                        "doctrinal_completeness_reasoning", "doctrinal_completeness_score",
                        "redundancy_rate_reasoning", "redundancy_rate_score",
                        "summary",
                    ],
                },
            },
            "comparative_analysis": {"type": "string"},
        },
        "required": ["pipeline_scores", "comparative_analysis"],
    },
}


def init_judge() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_judge() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def _build_prompt(
    query: str,
    results: list[PipelineResult],
    overlap: OverlapReport,
) -> str:
    """Render the judge prompt. `results` must already be in presentation order —
    `run()` shuffles it so the order can be recorded alongside the scores."""
    lines = [f"Query: {query}\n"]
    lines.append(f"Shared chunks (in ALL pipelines): {overlap.shared}")
    lines.append(f"Unique chunks per pipeline: {json.dumps(overlap.unique, indent=2)}\n")
    for result in results:
        lines.append(f"=== Pipeline: {result.pipeline} ===")
        for i, chunk in enumerate(result.chunks):
            attribution = "SHARED" if chunk.chunk_id in overlap.shared else "UNIQUE"
            lines.append(
                f"  [{i+1}] ({attribution}) score={chunk.reranker_score:.3f} "
                f"ref={chunk.reference or chunk.collection}\n"
                f"      {chunk.content[:300]}"
            )
        lines.append("")
    return "\n".join(lines)


def _fallback_scores(results: list[PipelineResult]) -> list[JudgeScore]:
    return [
        JudgeScore(
            pipeline=r.pipeline,
            dimensions={
                dim: DimensionScore(score=0.0, reasoning="Judge failed")
                for dim in WEIGHTS
            },
            weighted_total=0.0,
            summary="Judge failed",
        )
        for r in results
    ]


async def run(
    query: str,
    results: list[PipelineResult],
    overlap: OverlapReport,
) -> JudgeReport:
    """Score pipeline results using a five-dimension rubric. Called after overlap.run()."""
    if _client is None:
        init_judge()

    # Randomise presentation order per call. An LLM comparing candidates in one
    # prompt weights earlier items more, so a fixed order would hand whichever
    # pipeline sorts first a permanent advantage across every query — the same
    # position bias the listwise reranker randomises against. The order used is
    # returned on the report so a narrow margin can be read with that in mind.
    presented = list(results)
    random.shuffle(presented)
    presentation_order = [r.pipeline for r in presented]
    logger.info("judge: presentation order=%s", presentation_order)

    prompt = _build_prompt(query, presented, overlap)
    tracker = CostTracker()
    response = None
    valid = True
    error = None

    try:
        # STREAMED, with an explicit deadline. A non-streaming call here hung for
        # 35 minutes in a batch run: Opus 5 with adaptive thinking and a large
        # multi-pipeline prompt exceeded the SDK's 10-minute default timeout, which
        # then retried twice (3 x 10 min). Anthropic's guidance is to stream any
        # request with long output or high max_tokens — streaming keeps the
        # connection active so the timeout does not fire mid-generation. The
        # explicit timeout + max_retries=0 bounds the worst case so a stuck judge
        # fails fast into _fallback_scores instead of stalling an entire suite.
        client = _client.with_options(  # type: ignore[union-attr]
            timeout=settings.judge_timeout_s,
            # A stalled streamed response must not be retried inside the SDK. The
            # artifact-aware suite can retry the query later without recapturing
            # retrieval, while an SDK retry invisibly doubles the deadline.
            max_retries=0,
        )
        async with client.messages.stream(
            model=_JUDGE_MODEL,
            # Thinking is ON by default on Opus 5 and must stay on: with
            # `thinking: disabled` the model occasionally emits a tool call as plain
            # text instead of a tool_use block, which this judge would read as a
            # missing tool block and silently fall back to all-zero scores. Budget is
            # raised because thinking bills as output and shares max_tokens with the
            # tool result.
            max_tokens=16000,
            # No `temperature` — Opus 5 removed the parameter and returns
            # 400 "`temperature` is deprecated for this model" if it is sent.
            system=[{
                "type": "text",
                "text": _JUDGE_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "score_pipelines"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = await stream.get_final_message()
        tracker.record(
            "judge",
            _JUDGE_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                f"judge output truncated at {response.usage.output_tokens} tokens"
            )
        tool_block = next(b for b in response.content if b.type == "tool_use")
        parsed = tool_block.input

        scores: list[JudgeScore] = []
        for s in parsed.get("pipeline_scores", []):
            dims: dict[str, DimensionScore] = {}
            for dim in WEIGHTS:
                raw_score = float(s.get(f"{dim}_score", 0.0))
                if not math.isfinite(raw_score):
                    raise ValueError(
                        f"judge returned non-finite {dim} score for {s.get('pipeline')}"
                    )
                dims[dim] = DimensionScore(
                    score=max(0.0, min(1.0, raw_score)),
                    reasoning=s.get(f"{dim}_reasoning", ""),
                )
            scores.append(JudgeScore(
                pipeline=s["pipeline"],
                dimensions=dims,
                weighted_total=compute_weighted_total({k: v.score for k, v in dims.items()}),
                summary=s.get("summary", ""),
            ))
        comparative = parsed.get("comparative_analysis", "")

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        logger.warning("judge: failed (%s); returning empty scores", error)
        scores = _fallback_scores(results)
        comparative = f"Judge call failed: {error}"
        valid = False

    tokens_used = 0
    if response is not None:
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

    # The judge is a model: it can skip a pipeline on a long comparison prompt, or
    # label one with a name that was never sent. Either is silent — a missing row is
    # not a zero, so the all-zeros guard in the batch harness does not catch it, and
    # the aggregate then averages that pipeline over a self-selected subset of
    # queries while its win rate is divided by the full count.
    expected = {r.pipeline for r in results}
    got = {s.pipeline for s in scores}
    duplicate_names = sorted(
        name for name in got if sum(s.pipeline == name for s in scores) > 1
    )
    if got != expected or duplicate_names:
        valid = False
        error = (
            f"incomplete judge output: missing={sorted(expected - got)} "
            f"unknown={sorted(got - expected)} duplicates={duplicate_names}"
        )
        missing, unknown = sorted(expected - got), sorted(got - expected)
        logger.warning(
            "judge: scored %d of %d pipelines (missing=%s unknown=%s duplicates=%s) — the caller "
            "should discard this query rather than aggregate a partial result",
            len(got & expected), len(expected), missing, unknown, duplicate_names,
        )
        # Unknown names can be dropped without damaging complete expected scores.
        if unknown:
            scores = [s for s in scores if s.pipeline in expected]
        # Duplicate expected names are ambiguous and must reject the response.
        if duplicate_names:
            scores = []

    return JudgeReport(
        scores=scores,
        comparative_analysis=comparative,
        tokens_used=tokens_used,
        cost=tracker.total_cost(),
        model=_JUDGE_MODEL,
        presentation_order=presentation_order,
        valid=valid,
        error=error,
    )
