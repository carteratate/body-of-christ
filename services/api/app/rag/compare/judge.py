"""LLM-as-judge scoring using Claude Sonnet."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic

from app.config import settings
from app.rag.compare.overlap import OverlapReport
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.types import PipelineResult

logger = logging.getLogger(__name__)

_JUDGE_MODEL = "claude-haiku-4-5"
_client: anthropic.AsyncAnthropic | None = None


def init_judge() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_judge() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


@dataclass
class JudgeScore:
    pipeline: str
    score: float
    reasoning: str


@dataclass
class JudgeReport:
    scores: list[JudgeScore]
    overall_reasoning: str
    tokens_used: int
    cost: float
    model: str


def _build_prompt(
    query: str,
    results: list[PipelineResult],
    overlap: OverlapReport,
) -> str:
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

    pipelines = [r.pipeline for r in results]
    lines.append(
        f"Score each pipeline 0.0-1.0 for retrieval quality relative to the query. "
        f"Consider: relevance of unique chunks, whether shared chunks confirm quality, "
        f"diversity of sources. "
        f'Return JSON only: {{"scores": [{{"pipeline": "<name>", "score": <float>, "reasoning": "<str>"}}], "overall_reasoning": "<str>"}}'
        f"\nPipelines to score: {pipelines}"
    )
    return "\n".join(lines)


async def run(
    query: str,
    results: list[PipelineResult],
    overlap: OverlapReport,
) -> JudgeReport:
    """Score pipeline results using Claude Sonnet. Called after overlap.run()."""
    if _client is None:
        init_judge()

    prompt = _build_prompt(query, results, overlap)
    tracker = CostTracker()

    response = None
    try:
        response = await _client.messages.create(  # type: ignore[union-attr]
            model=_JUDGE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        tracker.record(
            "judge",
            _JUDGE_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        parsed = json.loads(response.content[0].text)
        scores = [
            JudgeScore(
                pipeline=s["pipeline"],
                score=float(s["score"]),
                reasoning=s["reasoning"],
            )
            for s in parsed.get("scores", [])
        ]
        overall = parsed.get("overall_reasoning", "")
    except Exception as exc:
        logger.warning("judge: failed (%s); returning empty scores", exc)
        scores = [
            JudgeScore(pipeline=r.pipeline, score=0.0, reasoning="Judge failed")
            for r in results
        ]
        overall = f"Judge call failed: {exc}"

    tokens_used = 0
    if response is not None:
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return JudgeReport(
        scores=scores,
        overall_reasoning=overall,
        tokens_used=tokens_used,
        cost=tracker.total_cost(),
        model=_JUDGE_MODEL,
    )
