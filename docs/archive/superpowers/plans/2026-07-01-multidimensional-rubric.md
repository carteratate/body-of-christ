# Multi-Dimensional Rubric Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single holistic score in `compare/judge.py` with a five-dimension rubric that uses chain-of-thought tool-use, computes a weighted aggregate in Python, and updates the HTML viewer to render per-dimension breakdowns.

**Architecture:** The LLM fills reasoning fields before score fields for each dimension (CoT via tool property ordering). Python parses the tool output and computes `weighted_total = Σ(score × weight)` after the fact. The system prompt is extracted to a static module-level constant so it is passed as a cacheable system block rather than inlined in the user message.

**Tech Stack:** Python 3.12, `anthropic` SDK (AsyncAnthropic), `dataclasses`, `pytest-asyncio`, inline HTML/JS in `routes/compare.py`

## Global Constraints

- Model: `claude-sonnet-4-6` — do not change
- Temperature: `0.1` — new; must be added to every `messages.create` call in `judge.py`
- Weights: Retrieval Relevance 0.30 · Best-Passage Selection 0.20 · Multi-angle Coverage 0.20 · Doctrinal Completeness 0.15 · Redundancy Rate 0.15 — sum to 1.0
- `compute_weighted_total()` is Python-only — the LLM must not compute the aggregate
- Two different sources making similar arguments is NOT redundant — same-source only
- Doctrinal Completeness defaults to 1.0 for non-contested topics
- A single vocabulary collision must pull Retrieval Relevance below 0.5 regardless of other chunks
- `JudgeReport.overall_reasoning` → renamed to `comparative_analysis` everywhere

---

## File Map

| File | Change |
|---|---|
| `services/api/app/rag/compare/judge.py` | Full rewrite of dataclasses, constants, tool schema, system prompt, and `run()` |
| `services/api/app/routes/compare.py` | Update judge panel in `_HTML_VIEWER` to render per-dimension scores |
| `services/api/tests/test_compare_judge.py` | Replace all four existing tests; add new dimension-parsing test |

`compare/runner.py`, `compare/overlap.py`, and `routes/compare.py`'s route handlers are untouched — `dataclasses.asdict(judge_report)` already serializes the richer structure transparently.

---

## Task 1: New data model, weights constant, and weighted aggregation

**Files:**
- Modify: `services/api/app/rag/compare/judge.py` (dataclasses + WEIGHTS + compute_weighted_total only — do not touch the `run()` function or tool schema yet)
- Modify: `services/api/tests/test_compare_judge.py`

**Interfaces:**
- Produces:
  - `DimensionScore(score: float, reasoning: str)` dataclass
  - `JudgeScore(pipeline: str, dimensions: dict[str, DimensionScore], weighted_total: float, summary: str)` dataclass
  - `JudgeReport(scores: list[JudgeScore], comparative_analysis: str, tokens_used: int, cost: float, model: str)` dataclass
  - `WEIGHTS: dict[str, float]` module-level constant
  - `compute_weighted_total(dimension_scores: dict[str, float]) -> float` module-level function

- [ ] **Step 1: Write the failing tests**

Add these to `services/api/tests/test_compare_judge.py` (keep existing tests for now — they will be replaced in Task 3):

```python
from app.rag.compare.judge import (
    DimensionScore,
    JudgeScore,
    JudgeReport,
    WEIGHTS,
    compute_weighted_total,
)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_weights_contain_all_dimensions():
    expected = {
        "retrieval_relevance",
        "best_passage_selection",
        "multi_angle_coverage",
        "doctrinal_completeness",
        "redundancy_rate",
    }
    assert set(WEIGHTS.keys()) == expected


def test_compute_weighted_total_perfect_scores():
    scores = {dim: 1.0 for dim in WEIGHTS}
    assert compute_weighted_total(scores) == 1.0


def test_compute_weighted_total_zero_scores():
    scores = {dim: 0.0 for dim in WEIGHTS}
    assert compute_weighted_total(scores) == 0.0


def test_compute_weighted_total_mixed():
    scores = {
        "retrieval_relevance": 1.0,
        "best_passage_selection": 0.0,
        "multi_angle_coverage": 0.0,
        "doctrinal_completeness": 0.0,
        "redundancy_rate": 0.0,
    }
    # Only retrieval_relevance (weight 0.30) contributes
    assert abs(compute_weighted_total(scores) - 0.30) < 1e-9


def test_dimension_score_dataclass():
    ds = DimensionScore(score=0.8, reasoning="Good coverage.")
    assert ds.score == 0.8
    assert ds.reasoning == "Good coverage."


def test_judge_score_dataclass():
    dims = {
        "retrieval_relevance": DimensionScore(0.9, "On-target."),
        "best_passage_selection": DimensionScore(0.8, "Canonical sections."),
        "multi_angle_coverage": DimensionScore(0.7, "Three angles."),
        "doctrinal_completeness": DimensionScore(1.0, "Non-contested topic."),
        "redundancy_rate": DimensionScore(1.0, "No same-source repeats."),
    }
    total = compute_weighted_total({k: v.score for k, v in dims.items()})
    js = JudgeScore(
        pipeline="s2_5_haiku",
        dimensions=dims,
        weighted_total=total,
        summary="Strong retrieval.",
    )
    assert js.pipeline == "s2_5_haiku"
    assert abs(js.weighted_total - (0.9*0.30 + 0.8*0.20 + 0.7*0.20 + 1.0*0.15 + 1.0*0.15)) < 1e-9
    assert js.summary == "Strong retrieval."


def test_judge_report_dataclass():
    report = JudgeReport(
        scores=[],
        comparative_analysis="No pipelines compared.",
        tokens_used=0,
        cost=0.0,
        model="claude-sonnet-4-6",
    )
    assert report.comparative_analysis == "No pipelines compared."
    assert not hasattr(report, "overall_reasoning")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && pytest tests/test_compare_judge.py::test_weights_sum_to_one tests/test_compare_judge.py::test_compute_weighted_total_perfect_scores tests/test_compare_judge.py::test_dimension_score_dataclass -v
```

Expected: FAIL — `ImportError: cannot import name 'DimensionScore'`

- [ ] **Step 3: Add new dataclasses, WEIGHTS, and compute_weighted_total to judge.py**

Replace the three existing dataclasses and add the new ones. Edit the top of `services/api/app/rag/compare/judge.py` — replace everything from `@dataclass` through the end of the `JudgeReport` definition:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd services/api && pytest tests/test_compare_judge.py::test_weights_sum_to_one tests/test_compare_judge.py::test_weights_contain_all_dimensions tests/test_compare_judge.py::test_compute_weighted_total_perfect_scores tests/test_compare_judge.py::test_compute_weighted_total_zero_scores tests/test_compare_judge.py::test_compute_weighted_total_mixed tests/test_compare_judge.py::test_dimension_score_dataclass tests/test_compare_judge.py::test_judge_score_dataclass tests/test_compare_judge.py::test_judge_report_dataclass -v
```

Expected: all 8 PASS

- [ ] **Step 5: Commit**

```bash
cd services/api && git add app/rag/compare/judge.py tests/test_compare_judge.py
git commit -m "feat(judge): add DimensionScore dataclasses, WEIGHTS constant, and compute_weighted_total"
```

---

## Task 2: System prompt, tool schema, temperature, and run() rewrite

**Files:**
- Modify: `services/api/app/rag/compare/judge.py` (everything except the dataclasses from Task 1)
- Modify: `services/api/tests/test_compare_judge.py` (replace all four existing tests, add one new test)

**Interfaces:**
- Consumes: `DimensionScore`, `JudgeScore`, `JudgeReport`, `WEIGHTS`, `compute_weighted_total` from Task 1
- Produces: updated `run(query, results, overlap) -> JudgeReport` — same signature, richer return value

- [ ] **Step 1: Write the failing tests**

Replace the four existing tests in `services/api/tests/test_compare_judge.py` with these (the eight new tests from Task 1 remain untouched):

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.rag.compare.judge import run as judge_run, JudgeReport, WEIGHTS
from app.rag.compare.overlap import OverlapReport
from app.rag.steps.types import RankedChunk, PipelineResult, StepTiming


def _make_result(pipeline: str) -> PipelineResult:
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000001",
        content="For God so loved the world.",
        reference="John 3:16",
        collection="bible",
        document_id="d1",
        document_title="Bible",
        author=None,
        reranker_score=0.9,
    )
    return PipelineResult(
        pipeline=pipeline,
        chunks=[chunk],
        step_timings=[StepTiming("embed", 0.1)],
        total_duration_s=1.0,
        cost_breakdown={},
        total_cost=0.0,
    )


def _make_tool_input(pipelines: list[str]) -> dict:
    """Build a valid score_pipelines tool input for the given pipeline names."""
    return {
        "pipeline_scores": [
            {
                "pipeline": p,
                "retrieval_relevance_reasoning": "All chunks are on-topic.",
                "retrieval_relevance_score": 0.9,
                "best_passage_selection_reasoning": "Canonical sections found.",
                "best_passage_selection_score": 0.8,
                "multi_angle_coverage_reasoning": "Three angles covered.",
                "multi_angle_coverage_score": 0.85,
                "doctrinal_completeness_reasoning": "Non-contested topic; default 1.0.",
                "doctrinal_completeness_score": 1.0,
                "redundancy_rate_reasoning": "No same-source repeats.",
                "redundancy_rate_score": 1.0,
                "summary": f"{p} retrieval is strong.",
            }
            for p in pipelines
        ],
        "comparative_analysis": f"Comparing {len(pipelines)} pipeline(s).",
    }


def _mock_tool_response(tool_input: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    response.usage = MagicMock(input_tokens=500, output_tokens=200)
    return response


@pytest.mark.asyncio
async def test_judge_returns_multidimensional_report():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku"), _make_result("s4_haiku")]
    mock_response = _mock_tool_response(_make_tool_input(["s2_5_haiku", "s4_haiku"]))

    import app.rag.compare.judge as judge_module
    judge_module._client = AsyncMock()
    judge_module._client.messages.create = AsyncMock(return_value=mock_response)

    report = await judge_run("what is love?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 2
    assert report.model == "claude-sonnet-4-6"
    assert report.cost > 0
    assert report.tokens_used == 700
    assert report.comparative_analysis == "Comparing 2 pipeline(s)."


@pytest.mark.asyncio
async def test_judge_dimension_scores_parsed_correctly():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku")]
    mock_response = _mock_tool_response(_make_tool_input(["s2_5_haiku"]))

    import app.rag.compare.judge as judge_module
    judge_module._client = AsyncMock()
    judge_module._client.messages.create = AsyncMock(return_value=mock_response)

    report = await judge_run("what is grace?", results, overlap)

    score = report.scores[0]
    assert score.pipeline == "s2_5_haiku"
    assert set(score.dimensions.keys()) == set(WEIGHTS.keys())
    assert score.dimensions["retrieval_relevance"].score == 0.9
    assert score.dimensions["retrieval_relevance"].reasoning == "All chunks are on-topic."
    assert score.dimensions["doctrinal_completeness"].score == 1.0
    # weighted_total: 0.9*0.30 + 0.8*0.20 + 0.85*0.20 + 1.0*0.15 + 1.0*0.15
    expected_total = 0.9*0.30 + 0.8*0.20 + 0.85*0.20 + 1.0*0.15 + 1.0*0.15
    assert abs(score.weighted_total - expected_total) < 1e-4
    assert score.summary == "s2_5_haiku retrieval is strong."


@pytest.mark.asyncio
async def test_judge_falls_back_on_llm_error():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku"), _make_result("s4_haiku")]

    import app.rag.compare.judge as judge_module
    judge_module._client = AsyncMock()
    judge_module._client.messages.create = AsyncMock(side_effect=RuntimeError("network error"))

    report = await judge_run("what is love?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 2
    assert all(s.weighted_total == 0.0 for s in report.scores)
    assert all(
        all(ds.score == 0.0 for ds in s.dimensions.values())
        for s in report.scores
    )
    assert report.tokens_used == 0
    assert report.cost == 0.0
    assert "failed" in report.comparative_analysis.lower()


@pytest.mark.asyncio
async def test_judge_falls_back_on_missing_tool_block():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("s2_5_haiku")]

    # Response with no tool_use block (e.g., text-only response)
    text_block = MagicMock()
    text_block.type = "text"
    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=20)

    import app.rag.compare.judge as judge_module
    judge_module._client = AsyncMock()
    judge_module._client.messages.create = AsyncMock(return_value=mock_response)

    report = await judge_run("grace?", results, overlap)

    assert isinstance(report, JudgeReport)
    assert len(report.scores) == 1
    assert report.scores[0].weighted_total == 0.0


@pytest.mark.asyncio
async def test_judge_scores_include_pipeline_names():
    overlap = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})
    results = [_make_result("pipeline_a"), _make_result("pipeline_b")]
    mock_response = _mock_tool_response(_make_tool_input(["pipeline_a", "pipeline_b"]))

    import app.rag.compare.judge as judge_module
    judge_module._client = AsyncMock()
    judge_module._client.messages.create = AsyncMock(return_value=mock_response)

    report = await judge_run("what is faith?", results, overlap)

    pipeline_names = {s.pipeline for s in report.scores}
    assert "pipeline_a" in pipeline_names
    assert "pipeline_b" in pipeline_names
    assert report.comparative_analysis == "Comparing 2 pipeline(s)."
    assert report.tokens_used == 700
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && pytest tests/test_compare_judge.py::test_judge_returns_multidimensional_report tests/test_compare_judge.py::test_judge_dimension_scores_parsed_correctly -v
```

Expected: FAIL — `AttributeError: 'JudgeReport' object has no attribute 'comparative_analysis'` (old dataclasses still have `overall_reasoning`)

- [ ] **Step 3: Replace judge.py entirely**

Full replacement of `services/api/app/rag/compare/judge.py`:

```python
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
```

- [ ] **Step 4: Run all judge tests**

```bash
cd services/api && pytest tests/test_compare_judge.py -v
```

Expected: all 13 tests PASS (8 from Task 1 + 5 from this task)

- [ ] **Step 5: Run the full test suite to catch regressions**

```bash
cd services/api && pytest tests/ -v --tb=short
```

Expected: all tests pass. If `test_compare_route.py` or `test_compare_stats.py` fail, check whether they assert on `judge.overall_reasoning` or `judge.scores[n].score` — update those assertions to use `comparative_analysis` and `scores[n].weighted_total` respectively.

- [ ] **Step 6: Commit**

```bash
cd services/api && git add app/rag/compare/judge.py tests/test_compare_judge.py
git commit -m "feat(judge): five-dimension rubric with CoT tool schema, cached system prompt, temperature=0.1"
```

---

## Task 3: HTML viewer judge panel update

**Files:**
- Modify: `services/api/app/routes/compare.py` (the `_HTML_VIEWER` string only — no route handler changes)

**Interfaces:**
- Consumes: `data.judge` JSON structure from the updated `JudgeReport`:
  - `data.judge.scores[n].pipeline` — string
  - `data.judge.scores[n].weighted_total` — float (replaces `score`)
  - `data.judge.scores[n].summary` — string (replaces `reasoning`)
  - `data.judge.scores[n].dimensions` — dict keyed by dimension name, each with `score` and `reasoning`
  - `data.judge.comparative_analysis` — string (replaces `overall_reasoning`)
  - `data.judge.cost` — float (unchanged)
  - `data.judge.model` — string (unchanged)

There are no unit tests for the inline HTML. Verification is manual (step 4).

- [ ] **Step 1: Update the judge section in `_HTML_VIEWER`**

In `services/api/app/routes/compare.py`, find this block inside the `renderResults` function (around line 284–293):

```javascript
  // Judge section
  const judgeSec = document.createElement("div");
  judgeSec.className = "section";
  judgeSec.innerHTML = `<h3>Judge (${data.judge.model}) — $${(data.judge.cost||0).toFixed(5)}</h3>`;
  (data.judge.scores||[]).forEach(s => {
    judgeSec.innerHTML += `<div class="score-bar">
      <span class="judge-score">${s.pipeline}: ${s.score.toFixed(2)} </span>
      <span class="score-fill" style="width:${Math.round(s.score*200)}px"></span>
      <div class="judge-reasoning">${s.reasoning}</div>
    </div>`;
  });
  judgeSec.innerHTML += `<div style="margin-top:8px;color:#7A8099">${data.judge.overall_reasoning||""}</div>`;
  out.appendChild(judgeSec);
```

Replace it with:

```javascript
  // Judge section
  const DIMENSION_LABELS = {
    retrieval_relevance: "Retrieval Relevance (30%)",
    best_passage_selection: "Best-Passage Selection (20%)",
    multi_angle_coverage: "Multi-angle Coverage (20%)",
    doctrinal_completeness: "Doctrinal Completeness (15%)",
    redundancy_rate: "Redundancy Rate (15%)",
  };
  const judgeSec = document.createElement("div");
  judgeSec.className = "section";
  judgeSec.innerHTML = `<h3>Judge (${data.judge.model}) — $${(data.judge.cost||0).toFixed(5)}</h3>`;
  (data.judge.scores||[]).forEach(s => {
    const total = (s.weighted_total||0).toFixed(3);
    const barWidth = Math.round((s.weighted_total||0)*200);
    let dimRows = "";
    Object.entries(DIMENSION_LABELS).forEach(([key, label]) => {
      const dim = (s.dimensions||{})[key] || {};
      const dimScore = (dim.score||0).toFixed(2);
      const dimBar = Math.round((dim.score||0)*100);
      dimRows += `<tr>
        <td style="padding:3px 8px 3px 0;color:#7A8099;font-size:11px;white-space:nowrap">${label}</td>
        <td style="padding:3px 8px;font-size:11px;width:30px;text-align:right">${dimScore}</td>
        <td style="padding:3px 0;width:100px"><div style="background:#1a2030;height:6px;width:100px"><div style="background:#C4972A;height:6px;width:${dimBar}px"></div></div></td>
        <td style="padding:3px 0 3px 8px;color:#7A8099;font-size:11px">${dim.reasoning||""}</td>
      </tr>`;
    });
    judgeSec.innerHTML += `<div class="score-bar" style="margin-bottom:12px">
      <div style="margin-bottom:6px">
        <span class="judge-score" style="font-weight:bold">${s.pipeline}: ${total}</span>
        <span class="score-fill" style="width:${barWidth}px;margin-left:8px;vertical-align:middle"></span>
      </div>
      <details>
        <summary style="cursor:pointer;color:#7A8099;font-size:11px">Dimension breakdown</summary>
        <table style="width:100%;border-collapse:collapse;margin-top:6px">${dimRows}</table>
      </details>
      <div class="judge-reasoning" style="margin-top:4px">${s.summary||""}</div>
    </div>`;
  });
  judgeSec.innerHTML += `<div style="margin-top:8px;color:#7A8099;font-size:12px">${data.judge.comparative_analysis||""}</div>`;
  out.appendChild(judgeSec);
```

- [ ] **Step 2: Start the dev server**

```bash
cd services/api && uvicorn app.main:app --reload
```

- [ ] **Step 3: Open the compare viewer and run a real comparison**

Navigate to `http://localhost:8000/v1/search/compare/view`

Run a query with at least 2 pipelines selected (e.g., `s2_5_haiku` and `s4_haiku`), collections `bible catechism summa`, query text: `what does the Church teach about purgatory?`

Verify:
- Judge panel shows a weighted total score per pipeline (3 decimal places)
- "Dimension breakdown" `<details>` expands to show all 5 dimension rows with individual scores and reasoning text
- Gold bar fills proportionally to each dimension score
- `comparative_analysis` text appears below all pipeline scores
- No JS errors in browser console

- [ ] **Step 4: Commit**

```bash
git add services/api/app/routes/compare.py
git commit -m "feat(compare-viewer): render per-dimension rubric scores in judge panel"
```
