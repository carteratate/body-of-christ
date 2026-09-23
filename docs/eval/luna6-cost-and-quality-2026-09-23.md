# GPT-6 Luna: cost, explanation quality, and retrieval pilot (2026-09-23)

Evidence behind the explanation-model switch, the pricing fixes, and the Luna arms in the
registry. Every number was measured against live services: cost and retrieval numbers
through the production pipeline (`hyde_cohere_luna`), the explanation bake-off by calling
each model directly with the production explanation prompt. Raw per-call token logs were
kept out of the repo.

## Prices used (checked on the providers' pages this day)

| Model | Input $/M | Output $/M | Role |
|---|---|---|---|
| gpt-5.6-luna | 0.20 | 1.20 | HyDE, genre pick, listwise rerank (production) |
| gpt-6-luna | 0.10 | 0.50 | explanations (new); evaluation arms |
| gpt-5.4-mini | 0.75 | 4.50 | explanations (old). The cost tracker carried gpt-4o-mini's 0.15/0.60 |
| claude-opus-5-5 | 4.00 | 20.00 | evaluation judge |
| Cohere rerank-v4.0-pro | $2.50 / 1K search units | | per collection |

## Real production cost, 28 searches logged Sept 16–23

The logs understated explanations ~5.27x (the gpt-5.4-mini rate). Corrected:

| Search type | n | Logged | Actual | Explanation share |
|---|---|---|---|---|
| All | 28 | $0.0192 | $0.0312 | 47% |
| Focused (quota 10, 1 collection) | 12 | $0.0103 | $0.0176 | 52% |
| Guest default (6 collections, quota 3) | 7 | $0.0246 | $0.0384 | 44% |
| 9–10 collections | 7 | $0.0320 | $0.0526 | 48% |
| Standard, 1–2 collections | 2 | $0.0092 | $0.0130 | 36% |

With explanations on gpt-6-luna the average falls to about **$0.018** (explanations
≈ $0.0017 of it). Cohere (~$0.010) then dominates, and Luna retrieval is ~$0.0057.

## Luna cost per search by configuration (8 queries each)

| Configuration | 5.6: HyDE | genre | rerank (medium) | 6 at medium: total | 6 at low: total |
|---|---|---|---|---|---|
| Guest default, 6 col q3 | 0.00205 | 0.00017 | 0.00426 | 0.00321 | 0.00282 |
| 1 col Catechism q4 | 0.00023 | – | 0.00116 | 0.00070 | 0.00058 |
| Focused Bible q10 | 0.00158 | – | 0.00338 | 0.00240 | 0.00209 |
| 5 col q4 | 0.00177 | 0.00017 | 0.00455 | 0.00324 | 0.00288 |
| All 10 q4 | 0.00293 | 0.00017 | 0.00526 | 0.00405 | 0.00372 |

HyDE and genre-pick token counts are the same on both models (reasoning off). The
reranker at medium emits ~46% more output on 6 (1,013 vs 693 tokens, 734 of them
reasoning) and is still ~48% cheaper.

## Explanation bake-off (60 passages, 15 objection/reply/stitched; judge Opus 5.5, blind)

Same system prompt and user message as `steps/explain.py`, streamed.

| Model | Mean (1–5) | Unsupported claim | $ / 1K explanations | Median total |
|---|---|---|---|---|
| gpt-6-sol (ceiling) | 4.70 | 0.0% | 2.80 | 2.44s |
| **gpt-6-luna, reasoning none** | **4.67** | **1.7%** | **0.14** | 1.75s |
| gpt-5.6-luna, reasoning none | 4.32 | 13.3% | 0.29 | 1.79s |
| claude-sonnet-5 | 4.21 | 13.3% | 4.77 | 3.22s |
| gpt-5.4-mini (old production) | 4.19 | 16.7% | 1.20 | 1.86s |
| claude-haiku-4-5 | 4.00 | 20.0% | 1.73 | 1.96s |
| gpt-5.4-nano | 3.93 | 11.7% | 0.36 | 1.72s |
| gpt-5-nano (minimal) | 3.22 | 46.7% | 0.11 | 1.83s |
| gpt-4.1-nano | 3.12 | 46.7% | 0.13 | 1.36s |

## Retrieval pilot (20 of the round-3 queries, 5 collections, quota 4; judge Opus 5.5)

Full pipeline per arm, all Luna calls switched together, so HyDE and rerank effects are
not separable here — which is why the registry now has separate arms.

| Arm | Judge total | Δ vs production (95% CI) | Passages | Chunk overlap with production |
|---|---|---|---|---|
| 5.6 medium (production) | 0.791 | — | 17.2 | — |
| 5.6 medium, rerun | 0.793 | +0.002 [−0.020, +0.029] | 16.9 | 0.60 |
| 6 medium | 0.786 | −0.005 [−0.041, +0.032] | 15.4 | 0.51 |
| 6 low | 0.774 | −0.017 [−0.047, +0.013] | 15.3 | 0.51 |

No arm is distinguishable from production at n=20. Two identical production runs share
only 60% of their passages; judging by the n=20 intervals, expect differences of a few
hundredths in the 80-query eval to be within noise — `hyde_cohere_luna_hydesample`
measures that floor directly for HyDE.
The 6 arms consistently return ~2 fewer passages (lower completeness/coverage, less
redundancy) — the thing to watch in the full eval.

## Bible genre pick, 80 eval queries, each model twice

| | Identical 4-genre sets | Mean shared genres |
|---|---|---|
| 5.6 vs 5.6 | 58/80 | 3.71 |
| 6 vs 6 | 47/80 | 3.54 |
| 5.6 vs 6 | 28/80 | 3.16 |

6 picks `free` far more (55 vs 16 of 80) and `nt-teachings` less (52 vs 75). Latency was
equal (median ~1.25s). Hence `HYDE_GENRE_LUNA_MODEL` is its own setting.

## Arms for the 80-query evaluation

`hyde_cohere_luna` (production), `hyde_cohere_luna_hydesample` (production, independent
HyDE draw: the HyDE noise floor), `hyde6_cohere_luna` (HyDE passages on 6, genre pick and
reranker unchanged), `hyde6_cohere_luna6` / `hyde6_cohere_luna6_low` (all Luna calls on
6, reranker at medium / low).
