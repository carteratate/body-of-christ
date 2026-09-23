#!/usr/bin/env python
"""Analyse the blinded Luna 5.6-vs-6 evaluation written by `eval_luna6_blind.py`.

Reads the suite JSONL, its `.arm_map.json` (alias -> real arm) and the per-query
artifacts (for each arm's own HyDE-draw cost), and reports:

1. Coverage — queries judged validly, and per-arm eligibility.
2. Per arm — mean rank (read first; see analyze_eval.py for why the composite is
   compressed), composite re-scored under current `judge.WEIGHTS`, each dimension,
   passages returned, rerank latency, and cost (rerank + Cohere + the arm's HyDE draw).
3. Paired comparisons against production with bootstrap 95% CIs, win/tie/loss and an
   exact two-sided sign test. The HyDE noise floor is `hydesample - production`: two
   independent 5.6 HyDE draws, identical downstream.
4. Isolated effects the arm design makes clean:
   - HyDE model: hybrid vs the mean of the two 5.6 draws (halves draw noise).
   - Rerank effort on 6: luna6 medium vs low (same HyDE key => same candidate pool).
   - Rerank model 5.6 vs 6 at medium: hybrid vs luna6 (confounded only by the Bible
     genre pick, which also moves to 6 in luna6).
5. Per-category deltas and a presentation-position bias check.
6. A decision summary under a non-inferiority margin (default 0.02 composite).

Usage (from services/api):
    .venv/bin/python scripts/analyze_luna6_eval.py
    .venv/bin/python scripts/analyze_luna6_eval.py --results ../../docs/eval/eval80-luna6.jsonl \\
        --margin 0.02 --md ../../docs/eval/eval80-luna6-analysis.md
Standard library only, apart from importing judge.WEIGHTS from the app.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROD = "hyde_cohere_luna"
NOISE = "hyde_cohere_luna_hydesample"
HYBRID = "hyde6_cohere_luna"
L6MED = "hyde6_cohere_luna6"
L6LOW = "hyde6_cohere_luna6_low"
ORDER = [PROD, NOISE, HYBRID, L6MED, L6LOW]
LABEL = {
    PROD: "production (5.6 all, rerank medium)",
    NOISE: "production, 2nd HyDE draw (noise floor)",
    HYBRID: "HyDE passages on 6 (genre + rerank 5.6)",
    L6MED: "all 6, rerank medium",
    L6LOW: "all 6, rerank low",
}
_DEFAULT = Path(__file__).resolve().parents[3] / "docs/eval/eval80-luna6.jsonl"


# --- stats ------------------------------------------------------------------

def bootstrap_ci(diffs: list[float], n: int = 10_000, seed: int = 7) -> tuple[float, float]:
    if not diffs:
        return (math.nan, math.nan)
    rng = random.Random(seed)
    k = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def sign_test_p(wins: int, losses: int) -> float:
    """Exact two-sided binomial sign test, ties dropped."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] if s else math.nan


# --- loading ----------------------------------------------------------------

def load(results: Path, arm_map: Path, artifacts: Path):
    from app.rag.compare.judge import WEIGHTS, compute_weighted_total

    alias = json.loads(arm_map.read_text())            # alias -> real
    rows, skipped = [], defaultdict(int)
    for line in results.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        judge = rec.get("judge") or {}
        if not judge.get("valid", False):
            skipped["judge invalid"] += 1
            continue
        weights = rec.get("fingerprint", {}).get("judge_weights")
        if weights and weights != dict(WEIGHTS):
            skipped["judged under different weights (re-scored)"] += 1
        scores = {}
        for s in judge["scores"]:
            real = alias.get(s["pipeline"], s["pipeline"])
            dims = {d: v["score"] for d, v in s["dimensions"].items()}
            scores[real] = {"total": compute_weighted_total(dims), **dims}
        if set(scores) != set(ORDER):
            skipped["missing arm scores"] += 1
            continue
        pipes = {alias.get(k, k): v for k, v in rec["pipelines"].items()}
        art_path = artifacts / f"q{rec['query_idx']:03d}.json"
        hyde_costs = {}
        if art_path.exists():
            shared = json.loads(art_path.read_text())["shared"]
            hyde_costs = {alias.get(k, k): v for k, v in shared.get("hyde_costs", {}).items()}
        order = [alias.get(p, p) for p in judge.get("presentation_order", [])]
        ranks = {
            arm: 1 + sum(scores[o]["total"] > scores[arm]["total"] for o in ORDER)
            + 0.5 * sum(scores[o]["total"] == scores[arm]["total"] for o in ORDER if o != arm)
            for arm in ORDER
        }
        rows.append({
            "qi": rec["query_idx"], "category": rec.get("category", "?"),
            "scores": scores, "ranks": ranks, "pipes": pipes,
            "hyde_costs": hyde_costs, "order": order,
            "judge_cost": judge.get("cost", 0.0),
        })
    return rows, dict(skipped), list(WEIGHTS)


# --- report -----------------------------------------------------------------

def paired(rows, a: str, b: str, key: str = "total") -> dict:
    diffs = [r["scores"][a][key] - r["scores"][b][key] for r in rows]
    wins = sum(d > 1e-9 for d in diffs)
    losses = sum(d < -1e-9 for d in diffs)
    lo, hi = bootstrap_ci(diffs)
    return {"mean": st.mean(diffs) if diffs else math.nan, "lo": lo, "hi": hi,
            "wins": wins, "ties": len(diffs) - wins - losses, "losses": losses,
            "p": sign_test_p(wins, losses), "n": len(diffs)}


def fmt_p(d: dict) -> str:
    return (f"{d['mean']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]  "
            f"W/T/L {d['wins']}/{d['ties']}/{d['losses']}  sign p={d['p']:.3f}")


def arm_cost(r, arm: str) -> float:
    p = r["pipes"][arm]
    return p.get("total_cost", 0.0) + sum(r["hyde_costs"].get(arm, {}).values())


def report(rows, skipped, dims, margin: float) -> list[str]:
    out: list[str] = []
    w = out.append
    n = len(rows)
    w(f"# Luna 5.6 vs 6 — blinded 80-query evaluation\n")
    w(f"Valid judged queries: **{n}**" + (f"  (skipped: {skipped})" if skipped else ""))
    if not n:
        return out
    judge_total = sum(r["judge_cost"] for r in rows)
    w(f"Judge spend: ${judge_total:.2f}\n")

    w("## Per arm\n")
    w("| Arm | Mean rank (1 best) | Composite | " + " | ".join(d.replace('_', ' ') for d in dims)
      + " | Passages | Rerank p50 / p90 s | Cost / query | Degraded |")
    w("|---|---|---|" + "---|" * len(dims) + "---|---|---|---|")
    for arm in ORDER:
        rank = st.mean(r["ranks"][arm] for r in rows)
        comp = st.mean(r["scores"][arm]["total"] for r in rows)
        dm = " | ".join(f"{st.mean(r['scores'][arm][d] for r in rows):.3f}" for d in dims)
        passages = st.mean(r["pipes"][arm].get("n_results", 0) for r in rows)
        lat = [r["pipes"][arm].get("wall_s_ex_throttle", r["pipes"][arm].get("wall_s", 0)) for r in rows]
        cost = st.mean(arm_cost(r, arm) for r in rows)
        degraded = sum(bool(r["pipes"][arm].get("degraded")) for r in rows)
        w(f"| {LABEL[arm]} | {rank:.2f} | {comp:.3f} | {dm} | {passages:.1f} | "
          f"{pct(lat, .5):.1f} / {pct(lat, .9):.1f} | ${cost:.4f} | {degraded} |")
    w("\nCost/query = the arm's rerank (Cohere + Luna) plus its own HyDE draw (HyDE, genre "
      "pick, HyDE embeddings); excludes the shared query embedding, FTS, and explanations "
      "(identical across arms). Latency is the per-arm replay (rerank and shaping), not HyDE.\n")

    w("## Paired against production (composite; positive = better than production)\n")
    noise = paired(rows, NOISE, PROD)
    for arm in [NOISE, HYBRID, L6MED, L6LOW]:
        w(f"- **{LABEL[arm]}**: {fmt_p(paired(rows, arm, PROD))}")
    w(f"\nHyDE noise floor (two 5.6 draws, identical downstream): {noise['mean']:+.3f} "
      f"[{noise['lo']:+.3f}, {noise['hi']:+.3f}]. An arm whose interval sits inside a "
      "band this wide around zero has not shown an effect beyond HyDE sampling.\n")

    w("## Isolated effects\n")
    two_draw = [
        r["scores"][HYBRID]["total"] - (r["scores"][PROD]["total"] + r["scores"][NOISE]["total"]) / 2
        for r in rows
    ]
    lo, hi = bootstrap_ci(two_draw)
    w(f"- **HyDE model 6 vs 5.6** (hybrid − mean of the two 5.6 draws): "
      f"{st.mean(two_draw):+.3f} [{lo:+.3f}, {hi:+.3f}]")
    w(f"- **Rerank effort on 6, medium vs low** (same candidate pool): "
      f"{fmt_p(paired(rows, L6MED, L6LOW))}")
    w(f"- **Rerank model 6 vs 5.6 at medium** (all-6 vs hybrid; also moves the Bible genre "
      f"pick): {fmt_p(paired(rows, L6MED, HYBRID))}")
    w("")

    w("## Per dimension against production (mean difference)\n")
    w("| Arm | " + " | ".join(d.replace('_', ' ') for d in dims) + " |")
    w("|---|" + "---|" * len(dims))
    for arm in [NOISE, HYBRID, L6MED, L6LOW]:
        cells = " | ".join(f"{paired(rows, arm, PROD, d)['mean']:+.3f}" for d in dims)
        w(f"| {LABEL[arm]} | {cells} |")
    w("")

    w("## By query category (composite difference vs production)\n")
    cats = sorted({r["category"] for r in rows})
    w("| Category | n | " + " | ".join(LABEL[a] for a in [NOISE, HYBRID, L6MED, L6LOW]) + " |")
    w("|---|---|" + "---|" * 4)
    for cat in cats:
        sub = [r for r in rows if r["category"] == cat]
        cells = " | ".join(f"{paired(sub, a, PROD)['mean']:+.3f}" for a in [NOISE, HYBRID, L6MED, L6LOW])
        w(f"| {cat} | {len(sub)} | {cells} |")
    w("")

    w("## Presentation-position bias check\n")
    by_pos = defaultdict(list)
    for r in rows:
        for i, arm in enumerate(r["order"]):
            by_pos[i + 1].append(r["scores"][arm]["total"] - st.mean(
                r["scores"][a]["total"] for a in ORDER))
    for pos in sorted(by_pos):
        w(f"- position {pos}: mean score vs query mean {st.mean(by_pos[pos]):+.3f} (n={len(by_pos[pos])})")
    w("")

    w(f"## Decision summary (non-inferiority margin {margin:.3f} composite)\n")
    prod_cost = st.mean(arm_cost(r, PROD) for r in rows)
    prod_lat = pct([r["pipes"][PROD].get("wall_s_ex_throttle", 0) for r in rows], .5)
    for arm in [HYBRID, L6MED, L6LOW]:
        d = paired(rows, arm, PROD)
        if d["lo"] > 0:
            verdict = "BETTER than production"
        elif d["lo"] >= -margin:
            verdict = "non-inferior (within margin)"
        elif d["hi"] < -margin:
            verdict = "WORSE than production"
        else:
            verdict = "inconclusive (interval crosses the margin)"
        cost = st.mean(arm_cost(r, arm) for r in rows)
        lat = pct([r["pipes"][arm].get("wall_s_ex_throttle", 0) for r in rows], .5)
        passages = st.mean(r["pipes"][arm].get("n_results", 0) for r in rows) - st.mean(
            r["pipes"][PROD].get("n_results", 0) for r in rows)
        w(f"- **{LABEL[arm]}** — {verdict}; composite {d['mean']:+.3f} "
          f"[{d['lo']:+.3f}, {d['hi']:+.3f}]; cost {100 * (cost / prod_cost - 1):+.0f}% "
          f"per query (arm spend); rerank p50 {lat - prod_lat:+.1f}s; passages {passages:+.1f}")
    w("\nRead mean rank alongside the composite; a change worth shipping should also clear "
      "the HyDE noise floor above and not trade away passages the dimension table shows "
      "users rely on (doctrinal completeness, coverage).")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", default=str(_DEFAULT))
    ap.add_argument("--arm-map", default=None, help="default: <results>.arm_map.json")
    ap.add_argument("--artifacts", default=None, help="default: <results stem>-artifacts/")
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--md", default=None, help="also write the report to this Markdown file")
    args = ap.parse_args()

    results = Path(args.results)
    arm_map = Path(args.arm_map) if args.arm_map else results.with_suffix(".arm_map.json")
    artifacts = (Path(args.artifacts) if args.artifacts
                 else results.with_suffix("").with_name(results.stem + "-artifacts"))
    for path in (results, arm_map):
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts/eval_luna6_blind.py first")

    rows, skipped, dims = load(results, arm_map, artifacts)
    text = "\n".join(report(rows, skipped, dims, args.margin))
    print(text)
    if args.md:
        Path(args.md).write_text(text + "\n")
        print(f"\nwritten: {args.md}")


if __name__ == "__main__":
    main()
