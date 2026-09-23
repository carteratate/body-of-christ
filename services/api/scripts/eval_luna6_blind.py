#!/usr/bin/env python
"""Run the 80-query Luna 5.6-vs-6 evaluation with the arms blinded to the judge.

The judge prompt shows each pipeline's name, and names like `hyde6_cohere_luna6_low`
tell it which arm is the newer model. This registers the five arms under neutral
aliases (`arm_1`..`arm_5`, deterministic shuffle) with configs identical to the
registry entries except `name`, writes the alias -> arm mapping next to the results,
and hands off to `run_eval_suite.main()`. Resumable exactly like the suite: rerun the
same command and completed queries are skipped.

Usage (from services/api, with the project .venv):
    EVALUATION_BUILD_ID=$(git rev-parse --short HEAD) EVALUATION_CORPUS_ID=prod-YYYY-MM-DD \\
        .venv/bin/python scripts/eval_luna6_blind.py
    .venv/bin/python scripts/analyze_luna6_eval.py

Expect ~140 s and ~$0.20 of Opus 5.5 judging per query (~3 h, ~$16 for all 80),
plus ~$0.05 per query of retrieval spend. One process, one query at a time: safe
for the production database.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ARMS = [
    "hyde_cohere_luna",             # production: all Luna calls on 5.6, rerank medium
    "hyde_cohere_luna_hydesample",  # production with its own HyDE draw: noise floor
    "hyde6_cohere_luna",            # HyDE passages on 6; genre pick + rerank on 5.6
    "hyde6_cohere_luna6",           # all Luna calls on 6, rerank medium
    "hyde6_cohere_luna6_low",       # all Luna calls on 6, rerank low
]
_DEFAULT_OUT = Path(__file__).resolve().parents[3] / "docs/eval/eval80-luna6.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    ap.add_argument("--queries", nargs="+", type=int, default=None,
                    help="subset of query indices (default: all 80)")
    ap.add_argument("--seed", type=int, default=20260923,
                    help="alias shuffle seed; keep it fixed so a resumed run reuses the mapping")
    args = ap.parse_args()

    from app.rag.pipelines.registry import PIPELINES
    import scripts.run_eval_suite as suite

    shuffled = ARMS[:]
    random.Random(args.seed).shuffle(shuffled)
    mapping = {f"arm_{i + 1}": real for i, real in enumerate(shuffled)}
    for alias, real in mapping.items():
        PIPELINES[alias] = dataclasses.replace(PIPELINES[real], name=alias)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    map_path = out.with_suffix(".arm_map.json")
    if map_path.exists() and json.loads(map_path.read_text()) != mapping:
        raise SystemExit(
            f"{map_path} holds a different alias mapping; resuming would mix arms. "
            "Use the original --seed or a new --out."
        )
    map_path.write_text(json.dumps(mapping, indent=2) + "\n")
    print(f"arm map   : {map_path}", flush=True)

    sys.argv = [sys.argv[0], "--out", str(out), "--pipelines", *mapping]
    if args.queries is not None:
        sys.argv += ["--queries", *map(str, args.queries)]
    asyncio.run(suite.main())


if __name__ == "__main__":
    main()
