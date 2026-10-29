# Multi-Dimensional Rubric Scoring for RAG Pipeline Judge — Design Spec
**Date:** 2026-07-01

## Overview

Replace the single-score LLM judge in `services/api/app/rag/compare/judge.py` with a five-dimension rubric that scores each pipeline independently across specific retrieval quality criteria, then aggregates to a weighted total in Python. The rubric is designed for a Catholic theology RAG pipeline and reflects domain-specific failure modes that a generic relevance score cannot capture.

---

## Goals

1. Replace the current holistic 0.0–1.0 pipeline score with five independently scored dimensions
2. Embed chain-of-thought reasoning into the tool schema (reasoning field precedes score field for each dimension)
3. Compute the weighted aggregate in Python, not by the LLM
4. Add `temperature=0.1` for deterministic, comparable scores across runs
5. Make the system prompt fully cacheable (static rubric definitions, no per-query content)

---

## Rubric Dimensions & Weights

| Dimension | Weight | What it measures |
|---|---|---|
| Retrieval Relevance | 30% | How on-target each chunk is; sensitive to vocabulary collision failures |
| Best-Passage Selection | 20% | When a collection is relevant, did the pipeline find its canonical passages |
| Multi-angle Coverage | 20% | Does the result set span distinct source types (scriptural, systematic, pastoral, etc.) |
| Doctrinal Completeness | 15% | Does the result set represent both poles of a doctrine, not a one-sided slice |
| Redundancy Rate | 15% | Same source making the same argument in multiple chunks |

**Weighted total formula (Python):**
```python
WEIGHTS = {
    "retrieval_relevance":    0.30,
    "best_passage_selection": 0.20,
    "multi_angle_coverage":   0.20,
    "doctrinal_completeness": 0.15,
    "redundancy_rate":        0.15,
}

def compute_weighted_total(dimension_scores: dict[str, float]) -> float:
    return round(sum(dimension_scores[dim] * weight
                     for dim, weight in WEIGHTS.items()), 4)
```

---

## Scoring Anchors

Each dimension uses a 0.0–1.0 continuous scale. The anchors below define 1.0, 0.5, and 0.0 for each dimension. These are embedded in the system prompt as the few-shot calibration signal.

### Retrieval Relevance

| Score | Meaning | Example |
|---|---|---|
| 1.0 | Every chunk directly engages the specific concept asked about. No vocabulary collisions. | Query: "what is purgatory?" → all chunks are explicitly about purgatory as a doctrine of final purification |
| 0.5 | Most chunks are on-topic; one or two share vocabulary with the query but address something adjacent | Query: "what is purgatory?" → four good chunks, one is a psalm about suffering/refinement used metaphorically |
| 0.0 | One or more chunks are a different doctrine entirely — vocabulary collision. The rest may be fine. | Query: "what is the Immaculate Conception?" → a chunk about the Virgin Birth appears; a different doctrine sharing the word "conception" |

A single vocabulary collision must pull the score below 0.5 regardless of how good the other chunks are.

### Best-Passage Selection

Score per collection that appears in the results, average across them.

| Score | Meaning | Example |
|---|---|---|
| 1.0 | For each relevant collection, the pipeline found its canonical answer passage — the section where the collection most directly and substantively treats the topic | Query: "what does the Church teach about the Trinity?" → Catechism chunk is from CCC §253–267, the specific Trinitarian dogma section |
| 0.5 | Relevant collections are represented but passages are mid-tier — thematically related sections rather than the core treatment | Same query → Catechism chunk is from a baptismal formula section that mentions the Trinity in passing |
| 0.0 | A clearly relevant collection appears only via a peripheral mention — the corpus obviously has far better passages available that were not found | Same query → Catechism chunk is from the section on prayer: "we pray to the Father, through the Son, in the Holy Spirit" with no doctrinal explanation |

### Multi-angle Coverage

Applicable angles for this corpus: scriptural foundation, systematic/philosophical reasoning, conciliar/magisterial definition, pastoral application, historical precedent. First identify which angles apply to this query type, then assess coverage only against those.

| Score | Meaning | Example |
|---|---|---|
| 1.0 | Results span three or more meaningfully distinct applicable angles | Query: "why does suffering exist?" → one chunk is scriptural (Job/Romans), one is systematic (Aquinas on privation), one is pastoral (Salvifici Doloris on redemptive suffering) |
| 0.5 | Two distinct angles covered; noticeably thin in at least one clearly applicable area | Same query → scriptural and pastoral covered; no systematic/philosophical treatment of theodicy despite Summa availability |
| 0.0 | All results come from one angle — five scripturally-grounded chunks and nothing else | Same query → five Bible passages on suffering; no Aquinas, no magisterial document, no pastoral guidance |

### Doctrinal Completeness

If a topic has no meaningful doctrinal tension, score 1.0 by default — completeness is not a meaningful constraint on non-contested doctrines.

| Score | Meaning | Example |
|---|---|---|
| 1.0 | Result set captures both the affirmation and the nuance — both poles of the doctrine where tension exists | Query: "does the Church teach only Catholics are saved?" → results include both the traditional formulation AND Vatican II's development in Lumen Gentium §16 |
| 0.5 | Dominant side of the doctrine is well-represented; the balancing pole is thin or absent | Same query → results are all traditional formulations with nothing from Vatican II's development |
| 0.0 | Results represent only one pole, and the missing pole would substantially change how a user understands Church teaching | Query: "what does the Church teach about contraception?" → all passages are prohibitive; the positive theology of conjugal love in Humanae Vitae §§8–12 is entirely absent |

### Redundancy Rate

Two different sources making similar arguments is NOT redundant — that is convergence across the tradition and is a positive signal. Penalize only same-source chunks that make the same argument.

| Score | Meaning | Example |
|---|---|---|
| 1.0 | No two chunks from the same source make the same substantive argument | Five chunks from five documents, each adding distinct content |
| 0.5 | One pair of same-source chunks overlaps significantly; other results are distinct | Two sections from Evangelium Vitae both arguing from natural law on the same point; other results are varied |
| 0.0 | Multiple same-source chunks are essentially restating each other — wasted result slots | Three sections from Humanae Vitae all making the same contraception-as-intrinsically-disordered argument in slightly different phrasing |

---

## Prompt Architecture

### Model & Temperature

- Model: `claude-sonnet-4-6` (unchanged)
- Temperature: `0.1` (new — scoring should be deterministic and comparable across runs)

### System Prompt (static, cacheable)

Three sections passed as a single `cache_control: ephemeral` system block:

**Section 1 — Role and task:**
```
You are evaluating Catholic theology RAG pipeline results. For each pipeline,
score five dimensions of retrieval quality. For EACH dimension: reason through
what you observe in the result set first, then assign a score 0.0–1.0.
Your score must follow your reasoning — do not assign a number and then justify it.
```

**Section 2 — Rubric definitions with anchors:**
One block per dimension containing the definition and the three anchor examples (1.0 / 0.5 / 0.0) from the Scoring Anchors section above. The anchor examples serve as the few-shot calibration — they define the scale concretely rather than abstractly.

**Section 3 — Scoring rules:**
```
RULES:
- Score each dimension independently. Do not let your score on one dimension
  influence your score on another.
- For Doctrinal Completeness: if the topic has no meaningful doctrinal tension,
  score 1.0 by default.
- For Multi-angle Coverage: first identify which angles are applicable to this
  query type, then assess coverage only against those angles. Do not penalize
  absence of canon law in a devotional query.
- For Redundancy Rate: two different sources making similar arguments is NOT
  redundant. Penalize only same-source chunks making the same argument.
- For Retrieval Relevance: a single vocabulary collision (wrong doctrine
  retrieved) must pull the score below 0.5 regardless of how good the
  other chunks are.
- Do NOT compute a weighted total. Return only per-dimension scores.
```

### User Prompt

Unchanged from current structure — query, per-pipeline chunk lists with reference/collection/reranker score, and the overlap report summary.

### Chain-of-Thought Mechanism

CoT is embedded in the tool schema via property ordering: `reasoning` is defined before `score` for every dimension. Claude fills tool properties sequentially in definition order, so it articulates reasoning before it can emit the number. No separate thinking turn is needed. The reasoning is captured as structured output alongside the score, making it inspectable and loggable in the compare viewer.

---

## Tool Schema

```json
{
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

            "summary":                               {"type": "string"}
          },
          "required": [
            "pipeline",
            "retrieval_relevance_reasoning", "retrieval_relevance_score",
            "best_passage_selection_reasoning", "best_passage_selection_score",
            "multi_angle_coverage_reasoning", "multi_angle_coverage_score",
            "doctrinal_completeness_reasoning", "doctrinal_completeness_score",
            "redundancy_rate_reasoning", "redundancy_rate_score",
            "summary"
          ]
        }
      },
      "comparative_analysis": {"type": "string"}
    },
    "required": ["pipeline_scores", "comparative_analysis"]
  }
}
```

---

## Updated Data Model

```python
# services/api/app/rag/compare/judge.py

@dataclass
class DimensionScore:
    score: float
    reasoning: str

@dataclass
class JudgeScore:
    pipeline: str
    dimensions: dict[str, DimensionScore]   # keyed by dimension name
    weighted_total: float                    # computed by Python, not LLM
    summary: str

@dataclass
class JudgeReport:
    scores: list[JudgeScore]
    comparative_analysis: str
    tokens_used: int
    cost: float
    model: str
```

---

## Changes to `judge.py`

| Area | Current | New |
|---|---|---|
| `JudgeScore` dataclass | `pipeline`, `score: float`, `reasoning: str` | `pipeline`, `dimensions: dict[str, DimensionScore]`, `weighted_total: float`, `summary: str` |
| `JudgeReport` dataclass | `overall_reasoning` | `comparative_analysis` |
| Tool schema | Single `score` + `reasoning` per pipeline | Five `reasoning`/`score` pairs per pipeline + `summary` |
| System prompt | Inlined in `_build_prompt()` alongside query context | Extracted as a static string constant; passed as cacheable system block |
| Weighted total | IS the score field | Computed by `compute_weighted_total()` after parsing tool output |
| Temperature | Not set | `temperature=0.1` |
| `WEIGHTS` constant | Does not exist | Added as module-level dict |
| `compute_weighted_total()` | Does not exist | Added as module-level function |

---

## What Does Not Change

- `compare/runner.py` — unchanged
- `compare/overlap.py` — unchanged
- `routes/compare.py` — unchanged (the `judge` dict in `CompareResponse` will have a richer structure, but the field name and type are already `dict`)
- `tests/test_compare_judge.py` — all existing tests will need to be updated to match new dataclass structure, but the mock/patch pattern is identical
- The compare HTML viewer — the judge panel already renders from the `judge` dict; new dimension keys will appear automatically if the viewer is updated to display them

---

## Out of Scope

- Changes to the reranker prompt (`rerank_haiku.py`) — the rubric evaluates pipeline output, not the reranker's internal scoring
- Changes to `rerank_cohere.py` — same reason
- A golden query test set — the rubric is ready to receive one but none is defined here; building a curated query set is a separate future task
- Prompt caching for the user message — chunk content varies per query; only the system prompt is cached
