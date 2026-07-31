#!/usr/bin/env python
"""Analyse a run_eval_suite.py JSONL.

Deliberately NOT compare_batch/aggregate.py: that reads `pipeline_results` (a list)
while this harness writes `pipelines` (a dict) with different field names, so
pointing it here silently reports $0.00 cost and 0.0s latency for every pipeline
while the quality numbers look perfectly correct.

Reports per-dimension spread and per-query rankings alongside the composite, because
the composite alone is not trustworthy on this rubric: `multi_angle_coverage`
measured 0.916-0.971 across all six pipelines in round 1, `doctrinal_completeness`
is instructed to default to 1.0 when a topic has no doctrinal tension, and
`redundancy_rate` is floored by dedup's per-title cap. A chunk of the weight can act
as an additive constant that compresses every margin — and an additive constant
preserves rank order, which is why MEAN RANK is the statistic to read first.

Composites are re-scored from persisted per-dimension scores under the weights
currently in `judge.WEIGHTS`, so runs judged before and after a re-weighting stay
directly comparable. A run judged under different weights is flagged, not silently
mixed in.

Usage:  python scripts/analyze_eval.py /tmp/eval.jsonl
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.compare.judge import WEIGHTS  # noqa: E402

DIMS = list(WEIGHTS)


def total(score_row: dict) -> float:
    """Re-score from persisted per-dimension scores under the CURRENT weights.

    Deliberately not `score_row["weighted_total"]`: that field was frozen at the
    weights in force when the row was judged, so mixing runs from before and after a
    re-weighting would rank them on two different scales without any visible sign.
    Re-scoring is what makes the weights a decision that can be revisited after the
    fact — the judge's per-dimension scores are the durable artifact, the composite
    is just a view over them.
    """
    return sum(score_row["dimensions"][d]["score"] * w for d, w in WEIGHTS.items())


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/eval.jsonl")
    all_rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if not all_rows:
        raise SystemExit(f"{path} is empty")

    pipes = sorted({s["pipeline"] for r in all_rows for s in r["judge"]["scores"]})
    # Quality comparisons must stay paired. If any pipeline degraded, quarantine the
    # whole query from the default aggregate while retaining it in the artifact.
    rows = [
        r for r in all_rows
        if all(
            v.get("quality_eligible", not v.get("degraded", False))
            for v in r["pipelines"].values()
        )
    ]
    quarantined = sorted(
        r["query_idx"] for r in all_rows if r not in rows
    )
    if not rows:
        raise SystemExit(f"{path} has no quality-eligible query rows")
    n = len(rows)
    print(f"file    : {path}")
    print(f"queries : {n}")
    fp = rows[0].get("fingerprint")
    if fp:
        print(f"judge   : {fp['judge_model']}   quota={fp['quota']}")
        judged_under = fp.get("judge_weights")
        if judged_under and judged_under != WEIGHTS:
            changed = [f"{d} {judged_under.get(d)}->{WEIGHTS[d]}"
                       for d in WEIGHTS if judged_under.get(d) != WEIGHTS[d]]
            print(f"weights : re-scored under current weights ({', '.join(changed)})")
            print("          per-dimension scores are unchanged; only the composite moves.")
    print()

    # --- integrity first: nothing below is meaningful if these are non-zero -------
    print("=== INTEGRITY ===")
    degraded = [(r["query_idx"], p, r["pipelines"][p]["degradations"])
                for r in all_rows for p in r["pipelines"]
                if r["pipelines"][p].get("degraded")]
    print(f"  degraded pipeline-runs : {len(degraded)}"
          + (f"  {degraded[:4]}" if degraded else "  (none)"))
    print(f"  quarantined queries    : {len(quarantined)}"
          + (f"  {quarantined}" if quarantined else "  (none)"))
    print(f"  quality-eligible rows  : {len(rows)} / {len(all_rows)}")
    partial = [r["query_idx"] for r in rows
               if {s["pipeline"] for s in r["judge"]["scores"]} != set(pipes)]
    print(f"  partial judge rows     : {len(partial)}"
          + (f"  queries {partial}" if partial else "  (none)"))
    thr = [(r["query_idx"], p) for r in all_rows for p in r["pipelines"]
           if r["pipelines"][p]["throttle_wait_s"] > 1.0]
    print(f"  throttled runs         : {len(thr)} (latency inflated; use ex-throttle)")
    print()

    # --- the confound: result-set size varies structurally by mode ---------------
    print("=== RESULT-SET SIZE (a confound: 3 of 5 judge dimensions reward breadth) ===")
    print(f"  {'pipeline':28} {'mean n_results':>15} {'min':>5} {'max':>5}")
    for p in pipes:
        v = [r["pipelines"][p]["n_results"] for r in rows]
        print(f"  {p:28} {st.mean(v):>15.1f} {min(v):>5} {max(v):>5}")
    print()

    # --- composite --------------------------------------------------------------
    print("=== COMPOSITE (re-scored under CURRENT weights) ===")
    print("  " + "  ".join(f"{d.split('_')[0]}={w:g}" for d, w in WEIGHTS.items()))
    print(f"  {'pipeline':28} {'mean':>7} {'median':>7} {'stdev':>7} {'min':>6} {'max':>6} {'wins':>5}")
    comp = {}
    for p in pipes:
        v = [total(s) for r in rows for s in r["judge"]["scores"]
             if s["pipeline"] == p]
        comp[p] = v
        wins = sum(1 for r in rows
                   if max(r["judge"]["scores"], key=total)["pipeline"] == p)
        sd = st.stdev(v) if len(v) > 1 else 0.0
        print(f"  {p:28} {st.mean(v):>7.3f} {st.median(v):>7.3f} {sd:>7.3f} "
              f"{min(v):>6.3f} {max(v):>6.3f} {wins:>5}")
    spread = max(st.mean(v) for v in comp.values()) - min(st.mean(v) for v in comp.values())
    print(f"\n  mean spread across pipelines: {spread:.3f}")
    worst_sd = max(st.stdev(v) for v in comp.values() if len(v) > 1)
    if spread < worst_sd:
        print(f"  ⚠️  spread ({spread:.3f}) < per-pipeline stdev ({worst_sd:.3f}): "
              f"the ranking is NOT separable at n={n}. Add queries before deciding.")
    print()

    # --- per-dimension: which dimensions actually discriminate ------------------
    print("=== PER-DIMENSION MEANS (spread shows which dimensions carry signal) ===")
    print(f"  {'pipeline':28}" + "".join(d[:12].rjust(14) for d in DIMS))
    per_dim = {d: [] for d in DIMS}
    for p in pipes:
        vals = {d: [] for d in DIMS}
        for r in rows:
            for s in r["judge"]["scores"]:
                if s["pipeline"] == p:
                    for d in DIMS:
                        vals[d].append(s["dimensions"][d]["score"])
        for d in DIMS:
            per_dim[d].append(st.mean(vals[d]))
        print(f"  {p:28}" + "".join(f"{st.mean(vals[d]):.3f}".rjust(14) for d in DIMS))
    print(f"  {'SPREAD (max-min)':28}"
          + "".join(f"{max(per_dim[d]) - min(per_dim[d]):.3f}".rjust(14) for d in DIMS))
    print("  ^ a near-zero spread means that dimension's weight is an additive")
    print("    constant: it moves every pipeline equally and discriminates nothing.")
    print()

    # --- per-query rankings: more honest than a mean at small n ------------------
    print("=== PER-QUERY RANK (1 = best) ===")
    print(f"  {'query':26}" + "".join(p[:12].rjust(14) for p in pipes))
    ranks = {p: [] for p in pipes}
    for r in rows:
        order = sorted(r["judge"]["scores"], key=lambda s: -total(s))
        pos = {s["pipeline"]: i + 1 for i, s in enumerate(order)}
        for p in pipes:
            if p in pos:
                ranks[p].append(pos[p])
        print(f"  q{r['query_idx']} {r['category'][:21]:22}"
              + "".join(str(pos.get(p, "-")).rjust(14) for p in pipes))
    print(f"  {'MEAN RANK':26}"
          + "".join(f"{st.mean(ranks[p]):.2f}".rjust(14) for p in pipes))
    print()

    # --- cost / latency ---------------------------------------------------------
    print("=== COST & LATENCY ===")
    print(f"  {'pipeline':28} {'cost/query':>11} {'wall':>8} {'ex-throttle':>12} {'rerank':>8}")
    for p in pipes:
        c = [r["pipelines"][p]["total_cost"] for r in rows]
        w = [r["pipelines"][p]["wall_s"] for r in rows]
        e = [r["pipelines"][p]["wall_s_ex_throttle"] for r in rows]
        rr = [sum(v for k, v in r["pipelines"][p]["cost_breakdown"].items()
                  if k.startswith("rerank")) for r in rows]
        print(f"  {p:28} ${st.mean(c):>10.4f} {st.mean(w):>7.1f}s {st.mean(e):>11.1f}s "
              f"${st.mean(rr):>7.4f}")
    jc = [r["judge"]["cost"] for r in rows]
    tot = sum(r["pipelines"][p]["total_cost"] for r in rows for p in pipes)
    print(f"\n  search total ${tot:.2f} | judge total ${sum(jc):.2f} "
          f"(${st.mean(jc):.4f}/query)")


if __name__ == "__main__":
    main()
