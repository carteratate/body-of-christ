# TheoCorpus V5 — Boosted Mode: Complete Hyperparameter Specification

> **Status: design spec — NOT implemented.** This describes the intended
> retrieval architecture, not live behavior. As of 2026-07-16 no retrieval code
> implements Stage 3's kind/grounding weighting (`services/api/app/rag/steps/rrf.py`
> has no kind, grounding, or weight references at all), and Stages 4-7 as
> specified here do not exist. The enrichment side that feeds this — facet
> kinds, grounding tiers, the `juridical` kind — IS built, in `datapipeline/`.
> Previously kept as `services/api/app/rag/BOOSTED_PLAN.md`; moved here so it
> is not mistaken for a description of the code it sat next to.

Architecture: per-source through Cohere → global merge → single global Haiku rerank → composition.
Modes: **Direct** / **Reflective**. All values are starting points pending gold-set tuning.

---

## Stage 0 — Query Prep (all paths fire in parallel)

| Component | Setting |
|---|---|
| Dense embed query | 1 call |
| Sparse encode query | per-collection BM25 (content model) + per-collection BM25 (annotation model) |
| Query classification (Haiku) | returns `intent_primary`, `intent_secondary` (optional), `confidence` |
| Classification gate | confidence below **high** → intent modifiers no-op; mode defaults carry the query |
| HyDE (Haiku) | collection-specific hypothetical passage; **Bible: one call returning all 3 style variants**, each embedded separately |

Intent labels: `doctrinal_lookup`, `passage_meaning`, `moral_practical`, `devotional_exploratory`, `typological_connection`, `historical_factual`, `juridical_lookup`.

`juridical_lookup` covers queries about validity/liceity, canonical obligations,
permissions and prohibitions, jurisdiction or competence, ecclesiastical office,
penalties or procedures, and what an operative decree establishes or suppresses
— e.g. "Who can validly witness a Catholic marriage?", "What penalty applies to
this canonical delict?". It is a distinct intent from `doctrinal_lookup`
("Why does the Church teach marriage is indissoluble?" stays doctrinal even
though canon law also addresses marriage) and from `moral_practical` ("What
virtues should spouses practice?" is moral, not juridical). A query about what
a decree changed historically stays `historical_factual` unless the requested
answer is specifically the operative legal effect.

---

## Stage 1 — Candidate Generation (per collection, 6 paths)

| Path | Target | Top-K |
|---|---|---|
| Dense query → facets | facets collection | 60 |
| Dense query → questions | questions collection | 30 |
| Dense query → chunks | chunks.dense | 50 |
| Sparse query → content BM25 | chunks.sparse_content | 40 |
| Sparse query → annotation BM25 | chunks.sparse_annotation | 40 |
| HyDE embed(s) → chunks | chunks.dense | 30 total (variants merged + deduped) |

Rule preserved from spec: sparse annotation path active only for fully enriched collections.

---

## Stage 2 — Precision Fast Lane (2 buckets per collection, pre-RRF)

| Parameter | Direct | Reflective |
|---|---|---|
| Facet bucket K | 5 | 5 |
| Question bucket K | 5 | 5 |
| Facet cosine threshold | 0.68 | 0.64 |
| Question cosine threshold | 0.72 | 0.68 |

- Dedup by `chunk_id`.
- Grounding used **only as tiebreaker** within a bucket (explicit > traditional > inferential). No guaranteed inclusion by grounding class; inferential competes like everything else.
- Fast-lane chunks are **pinned** into that collection's Cohere pool (bypass RRF).
- ⚠️ **Calibrate the two thresholds against your embedding model's actual similarity distribution before trusting these numbers.** Run ~100 sample queries, plot similarities, set thresholds at the elbow. These are the two most model-dependent numbers in the system.

---

## Stage 3 — Weighted RRF (per collection)

**RRF constant:** k = 60.

**Per-strategy weights:**

| Expansion path | Direct | Reflective |
|---|---|---|
| Enrichment facets (dense) | 1.00 | 1.00 |
| Enrichment questions (dense) | 0.90 | 0.85 |
| Dense chunks | 0.85 | 0.75 |
| Sparse content (BM25) | 0.80 | 0.60 |
| Sparse annotation (BM25) | 0.70 | 0.80 |
| HyDE | 0.70 | 0.75 |

**Grounding multiplier (per facet/question match):**

| Grounding | Direct | Reflective |
|---|---|---|
| explicit | 1.25 | 1.00 |
| traditional | 1.10 | 1.00 |
| inferential | 1.00 | 1.00 |

**Kind weighting — mode base table:**

| kind | Direct | Reflective |
|---|---|---|
| doctrinal | 1.00 | 0.90 |
| scriptural | 1.00 | 0.95 |
| moral | 1.00 | 0.90 |
| juridical | 1.00 | 0.90 |
| philosophical | 0.90 | 1.00 |
| historical | 0.90 | 0.95 |
| typological | 0.85 | 1.00 |
| devotional | 0.85 | 1.00 |

`juridical` (legal/ecclesial norms — validity, obligation, permission,
competence, penalty; see `enrichment/schema.py` KIND_VALUES) is new as of the
enrichment taxonomy update; it did not exist when this table was first
written, so it's placed alongside `moral`/`doctrinal` under the same
reasoning — a norm-stating, answer-seeking kind best served at full weight in
Direct mode. A separate, older planning doc used the name `legal_effect` for
this kind; `juridical` is the one canonical name going forward — do not
reintroduce `legal_effect` as a second runtime value.

**Intent × kind modifier table** (unlisted cells = 1.0; keep sparse):

| intent ↓ / kind → | doctrinal | scriptural | typological | devotional | moral | historical | juridical |
|---|---|---|---|---|---|---|---|
| doctrinal_lookup | 1.10 | 1.05 | 0.90 | 0.90 | — | — | 1.05 |
| passage_meaning | — | 1.10 | 1.05 | — | — | — | — |
| moral_practical | 1.05 | — | 0.85 | 0.90 | 1.20 | — | — |
| devotional_exploratory | 0.90 | — | 1.10 | 1.20 | 0.90 | — | 0.85 |
| typological_connection | 0.90 | 1.10 | 1.20 | — | 0.85 | — | 0.85 |
| historical_factual | — | — | 0.85 | 0.85 | — | 1.20 | 1.05 |
| juridical_lookup | 0.90 | 0.85 | 0.80 | 0.80 | 0.95 | 1.05 | 1.20 |

`juridical_lookup` is a new row (see Stage 0's intent labels): it strongly
boosts the `juridical` kind itself, mildly boosts `historical` (juridical
facts are often historically framed — a canon's promulgation date, a
suppressed office), and deprioritizes `typological`/`devotional` (least
relevant when the user wants a validity/competence/penalty answer). The other
intent rows each get a `juridical` cell for the same reason every other kind
has one — `moral_practical` deliberately gets no boost, since a query about
virtue is moral, not juridical, even when canon law also touches the same
topic (e.g. "What virtues should spouses practice?" vs. "What makes a
marriage canonically valid?").

**Combination formulas (order of operations):**

```
1. Intent blend (query side):
   intent_mod(kind) = 0.7 × table(primary, kind) + 0.3 × table(secondary, kind)
   (no secondary → primary alone; low confidence → intent_mod = 1.0)

2. Per-kind weight:
   kw(kind) = clamp( mode_base(kind) × intent_mod(kind), 0.80, 1.25 )

3. Secondary-kind gated, capped bonus (facet side) — REVISED. The original
   rule here was `w = max(kw(primary), (kw(primary)+kw(secondary))/2)`, which
   made a secondary kind pure, unconditional upside: it could never score a
   facet worse than a single-kind one, so as secondary-kind assignment became
   common (a 26-chunk enrichment trial saw secondary kinds on the large
   majority of facets in several collections — e.g. 50/52 Bible, 11/11
   papal-documents) the max() rule stopped discriminating between facets that
   genuinely serve a second query intent and facets that merely tolerate a
   second label. Replaced with:

   secondary_bonus_cap    = 0.10   (tunable; starting point, pending gold-set)
   secondary_match_factor = 0.5    (tunable; starting point, pending gold-set)

   secondary_matches_intent = intent_mod(secondary_kind) > 1.0
       (this query's classified intent must itself favor the secondary kind
        per the intent × kind modifier table above — not merely "the facet
        happens to carry a second label")

   w = kw(primary_kind) + (
         0                                                    if not secondary_matches_intent
         else min(secondary_bonus_cap,
                  secondary_match_factor × max(0, kw(secondary_kind) − kw(primary_kind)))
       )

   Primary kind is the sole determinant of eligibility and always the
   dominant weight; a secondary kind can nudge the score up by at most
   secondary_bonus_cap, and only for queries whose classified intent actually
   matches it — worth nothing on an intent that doesn't, instead of always
   worth something under the old rule.

   ⚠️ STATUS: no retrieval code implements Stage 3's kind/grounding weighting
   yet (checked `services/api/app/rag/steps/rrf.py` — no kind/grounding/weight
   references at all as of this note). This formula is the intended design
   for when that weighting is built, not a description of live behavior.
   When it is implemented, build it with three ablation modes selectable by
   config: (a) primary-kind weight only, no secondary bonus at all; (b) this
   gated capped-bonus formula; (c) [do NOT resurrect] the old unconditional
   max() rule, kept only as a documented cautionary baseline to compare
   against in offline evaluation, not as a production option.

4. Facet RRF contribution = strategy_weight × grounding_mult × w × RRF(rank)
```

- **Question matches inherit their parent facet's kind and grounding** and receive the same multipliers (× the questions strategy weight). **No kind gating anywhere** — kinds are weights, never eligibility.
- Output: **top m = 50 per collection** forwarded to Cohere.

---

## Stage 4 — Cohere Rerank (per source)

| Parameter | Direct | Reflective |
|---|---|---|
| Input per collection | fast-lane pins + RRF top-50, deduped (~50–55 docs) | same |
| Document text | annotation + content concatenated | same |
| Keep per collection (k_c) | **quota+4** | **same** |
| Score floor | drop anything < 0.30 | same |

Billing note: ~55 docs at ~2× long-doc counting ≈ 110 billed docs ≈ 1–2 search units per collection call. Verify current Cohere pricing/limits before locking in.

---

## Stage 5 — Global Merge (Cohere keeps → Haiku pool)

```
pool = union of per-collection keeps
if |pool| > 40:
    sort by Cohere score, trim to 40
    subject to floor: ≥2 candidates per active collection
        (only if that collection produced ≥2 above the 0.30 floor)
```

- **Randomize or interleave collection order** in the Haiku prompt every query (listwise position bias otherwise becomes a permanent thumb on the scale for whichever collection is listed first).

---

## Stage 6 — Global Haiku Listwise Rerank (boosted only)

| Parameter | Value |
|---|---|
| Pool cap | 40 candidates |
| Candidate representation | compressed card ≈ 300 tokens: chunk_id, collection, title/reference, annotation SUMMARY line, matched facet text + kind/grounding labels (if facet retreived), first ~150 tokens of content |
| Expected input | ~12–15K tokens (≈ 1–2¢/call) |
| Intent injection | one sentence: "The user appears to be asking a {intent}-type question." |
| Direct objective | rank by directness and authority of answer |
| Reflective objective | select a set illuminating the question from genuinely different angles; penalize redundancy (MMR-in-prompt) |
| Reflective floor | pool ≥ 25 before forced diversity; below that, diversify what exists without forcing |
| Return | ranked **IDs only**, one per line, top **(quota + 6)** — slack for post-processing losses |

---

## Stage 7 — Post-Processing / Composition

| Rule | Setting |
|---|---|
| Adjacent dedup | same document + within 2 chunks locationally + chunk-embedding cosine > 0.90 → drop lower-scored |
| Per-source cap | 2 (per work; per reader chapter for the single-document collections — see `app.rag.dedup.source_key`) |
| Per-collection cap | user quota setting |
| Coverage guarantee | ≥1 result per active collection if score allows |
| Direct guardrail | top-3 must not be all-inferential if traditional/explicit alternatives scored within ε (ε ≈ 0.05 Cohere score, or adjacent Haiku rank) |
| Reflective diversity | top 8 span ≥3 kinds and ≥2 collections where available |
| Final return | 8–10 results (quota) |

---

## Stage 8 — Explanations

Stream per-result "why this matters" LLM explanation sequentially, after all sources are combined. (Free tier substitute: display the matched facet text / question / annotation SUMMARY — precomputed, zero cost.)

---

## Tuning Discipline

This spec contains ~45 tunable numbers. A ~100-query gold set cannot tune 45 parameters — freeze everything at these defaults except the four that dominate:

1. **Facet fast-lane cosine threshold** (per mode)
2. **Question fast-lane cosine threshold** (per mode)
3. **Facets : dense-chunks RRF weight ratio**
4. **Direct-mode explicit grounding boost** (1.25)

Touch anything else only when the gold set shows a specific, repeated failure pattern attributable to it. If recall failures show the right chunk reaching RRF top-50 but dying before Cohere keeps, raise **k_c** before raising **m**.

Log per query: tier, mode, intent classification, full candidate pool with stage-by-stage scores, final results, and (when boosted) the free-tier result set for the same query — the divergence is your continuous measurement of what the LLM calls buy.