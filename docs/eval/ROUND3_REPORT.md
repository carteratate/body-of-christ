# TheoCorpus Retrieval Evaluation — Round 3

## Scope

Round 3 evaluated 80 distinct Catholic theology questions across five collections
using three retrieval/reranking pipelines:

1. `hyde_haiku` — the previous production pipeline
2. `hyde_cohere_haiku` — Cohere per collection, then global Haiku listwise reranking
3. `hyde_cohere_luna` — Cohere per collection, then global Luna listwise reranking

All final rows are clean, quality-eligible runs. Failed attempts were quarantined and
retried from durable shared-retrieval artifacts rather than scored as valid results.

## Quality

| Metric | Previous production | Cohere + Haiku | Cohere + Luna |
|---|---:|---:|---:|
| Mean score | 0.707 | 0.745 | **0.764** |
| Median score | 0.716 | 0.746 | **0.766** |
| Question wins | 22 | 25 | **33** |
| Average rank | 2.28 | 1.96 | **1.76** |
| Scores >= 0.80 | 20 | 20 | **28** |
| Scores < 0.65 | 25 | 12 | **4** |

Pairwise mean differences:

- Cohere + Haiku over previous production: +0.038 (50–30)
- Cohere + Luna over previous production: +0.057 (52–28)
- Cohere + Luna over Cohere + Haiku: +0.019 (47–33)

Both Cohere pipelines credibly outperformed the previous production pipeline. Luna's
advantage over Cohere + Haiku was directionally positive but smaller and not
conclusive by itself. Luna's strongest result was its lower bad-result rate: only four
questions scored below 0.65, compared with 25 under the previous production pipeline.

## Quality dimensions

| Dimension | Previous production | Cohere + Haiku | Cohere + Luna |
|---|---:|---:|---:|
| Retrieval relevance | 0.579 | 0.651 | **0.663** |
| Best-passage selection | 0.740 | 0.794 | **0.811** |
| Multi-angle coverage | 0.943 | 0.941 | **0.955** |
| Doctrinal completeness | 0.797 | 0.822 | **0.835** |
| Redundancy quality | 0.705 | 0.677 | **0.720** |

The average three-way result overlap was 5.8 passages. The variants therefore made
materially different selections rather than merely reordering the same result set.

## Production-path cost and latency

The evaluation judge is excluded from production estimates.

| Per-search metric | Previous production | Cohere + Haiku | Cohere + Luna |
|---|---:|---:|---:|
| Estimated cost | $0.0667 | $0.0442 | $0.0478 |
| Mean latency | 18.8s | 32.1s | 23.7s |
| Median latency | 17.8s | 30.0s | 22.0s |
| P95 latency | 21.3s | 47.6s | 31.2s |

Cohere + Luna improved mean quality by approximately 8% while costing approximately
28% less than the previous production pipeline. It added roughly four seconds at the
median and ten seconds at P95.

## Reliability

The experiment required 93 recorded attempts to produce 80 valid rows:

- 69 questions succeeded on the first attempt
- 9 required a second attempt
- 2 required a third attempt
- 13 attempts were quarantined

Failure breakdown:

- 9 evaluation-judge failures: eight read timeouts and one malformed response
- 3 pipeline-reranking failures: two Haiku failures and one incomplete Luna response
- 1 transient FTS DNS failure

The judge was the dominant evaluation reliability problem but is not part of live
search. Production-relevant risks were provider timeouts, malformed structured model
output, partial candidate coverage, and transient FTS connectivity.

The production implementation now:

- records structured degradation and successful-recovery events;
- uses targeted repairs for Haiku output defects;
- makes only one Luna attempt, falling back immediately to the complete Cohere order;
- retains conservative RRF fallbacks when a Cohere collection fails;
- never exposes fallback ordering scores as measured relevance; and
- keeps evaluation quarantine behavior separate from production availability.

## Decision

`hyde_cohere_luna` is the selected production pipeline. It had the strongest aggregate
quality, best low-quality tail, lower cost than the previous production pipeline, and
lower latency than Cohere + Haiku.

The previous production path remains represented in the registry for controlled
comparison. Live degradation telemetry should be monitored during rollout, especially
Luna fallback frequency, Cohere collection failures, total rerank latency, and FTS path
omissions.

## Reproducibility

The committed `eval80-round3-final.jsonl` contains exactly 80 unique, valid result
rows with no duplicate question IDs and no invalid judge outputs. Large shared
retrieval artifacts, attempts ledgers, smoke runs, aborted runs, and execution logs
are deliberately excluded from version control.
