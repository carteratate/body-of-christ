"""LLM-as-judge scoring using Claude Sonnet with a five-dimension rubric."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic

from app.config import settings
from app.rag.compare.overlap import OverlapReport
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import PipelineResult

logger = logging.getLogger(__name__)

_JUDGE_MODEL = "claude-sonnet-4-6"
_client: anthropic.AsyncAnthropic | None = None

WEIGHTS: dict[str, float] = {
    "retrieval_relevance":    0.30,
    "best_passage_selection": 0.20,
    "multi_angle_coverage":   0.20,
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
    import json
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


def _fallback_scores(results: list[PipelineResult], reason: str) -> list[JudgeScore]:
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

    prompt = _build_prompt(query, results, overlap)
    tracker = CostTracker()
    response = None

    try:
        response = await _client.messages.create(  # type: ignore[union-attr]
            model=_JUDGE_MODEL,
            max_tokens=4096,
            temperature=0.1,
            system=[{
                "type": "text",
                "text": _JUDGE_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "score_pipelines"},
            messages=[{"role": "user", "content": prompt}],
        )
        tracker.record(
            "judge",
            _JUDGE_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        tool_block = next(b for b in response.content if b.type == "tool_use")
        parsed = tool_block.input

        scores: list[JudgeScore] = []
        for s in parsed.get("pipeline_scores", []):
            dims: dict[str, DimensionScore] = {}
            for dim in WEIGHTS:
                dims[dim] = DimensionScore(
                    score=max(0.0, min(1.0, float(s.get(f"{dim}_score", 0.0)))),
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
        logger.warning("judge: failed (%s); returning empty scores", exc)
        scores = _fallback_scores(results, str(exc))
        comparative = f"Judge call failed: {exc}"

    tokens_used = 0
    if response is not None:
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return JudgeReport(
        scores=scores,
        comparative_analysis=comparative,
        tokens_used=tokens_used,
        cost=tracker.total_cost(),
        model=_JUDGE_MODEL,
    )
