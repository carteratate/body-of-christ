#!/usr/bin/env python
"""Run every registered pipeline once against live services and report the results.

Measures what the plan predicted: cost per mode, per-step timing, Cohere billed search
units per collection, and enough result detail to judge quality. Writes a JSON report.

Usage:
    python scripts/run_all_pipelines.py [--collections a b c] [--quota 4] [--query "..."]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
# Keep the per-collection Cohere unit lines and pool sizes visible — they are the
# measurements this run exists to collect.
for name in ("app.rag.steps.rerank_cohere", "app.rag.steps.rerank",
             "app.rag.steps.llm_rerank.listwise", "app.rag.steps.budget"):
    logging.getLogger(name).setLevel(logging.INFO)

DEFAULT_QUERY = "Why does God allow suffering? What is the Christian answer to evil and pain?"
DEFAULT_COLLECTIONS = ["bible", "catechism", "summa", "encyclicals", "church-fathers"]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--collections", nargs="+", default=DEFAULT_COLLECTIONS)
    ap.add_argument("--quota", type=int, default=4)
    ap.add_argument("--out", default="/tmp/pipeline_runs.json")
    ap.add_argument("--only", nargs="+", default=None, help="subset of pipeline names")
    args = ap.parse_args()

    from app.db import close_pool, init_pool
    from app.llm import close_llm, init_llm
    from app.rag.api_keys import close_api_keys, init_api_keys
    from app.rag.pipelines.registry import PIPELINES
    from app.rag.pipelines.runner import run as run_pipeline
    from app.rag.qdrant_client import close_qdrant, init_qdrant
    from app.rag.steps.embed import close_embed, init_embed
    from app.rag.steps.llm_rerank.openai_provider import close as close_luna
    from app.rag.steps.llm_rerank.openai_provider import init as init_luna
    from app.rag.steps.rerank_cohere import close_cohere, init_cohere
    from app.rag.steps.rerank_haiku import close_rerank, init_rerank

    # Same startup sequence as app.main.lifespan.
    await init_pool()
    init_llm(); init_embed(); init_qdrant(); init_api_keys()
    init_rerank(); init_cohere(); init_luna()

    names = args.only or list(PIPELINES)
    report = {
        "query": args.query,
        "collections": args.collections,
        "quota": args.quota,
        "runs": [],
    }

    try:
        for name in names:
            config = PIPELINES[name]
            print(f"\n{'='*78}\nRUN: {name}  (mode={config.rerank.mode}, "
                  f"hyde={config.retrieval.hyde}, fts={config.retrieval.fts})\n{'='*78}",
                  flush=True)
            t0 = time.perf_counter()
            try:
                result = await run_pipeline(
                    config, args.query, args.collections, args.quota,
                )
                wall = time.perf_counter() - t0
                run = {
                    "pipeline": name,
                    "mode": config.rerank.mode,
                    "hyde": config.retrieval.hyde,
                    "fts": config.retrieval.fts,
                    "provider": config.rerank.llm_provider,
                    "ok": True,
                    "wall_s": round(wall, 3),
                    "duration_s": round(result.total_duration_s, 3),
                    # Throttle/backoff seconds are INSIDE wall_s. Latency comparisons
                    # must use wall_s_ex_throttle, or a rate-limited key makes a
                    # pipeline look slow for a reason a production key removes.
                    "throttle_wait_s": round(result.throttle_wait_s, 3),
                    "wall_s_ex_throttle": round(wall - result.throttle_wait_s, 3),
                    "degraded": bool(result.degradations),
                    "degradations": result.degradations,
                    "total_cost": result.total_cost,
                    "cost_breakdown": result.cost_breakdown,
                    "steps": {s.step: round(s.duration_s, 3) for s in result.step_timings},
                    "n_results": len(result.chunks),
                    "collections_represented": sorted({c.collection for c in result.chunks}),
                    "scores": [round(c.reranker_score, 4) for c in result.chunks],
                    "results": [
                        {
                            "rank": i + 1,
                            "chunk_id": c.chunk_id,
                            "collection": c.collection,
                            "reference": c.reference,
                            "title": c.document_title,
                            "score": round(c.reranker_score, 4),
                            "has_annotation": c.annotation is not None,
                            "excerpt": (c.content or "")[:160].replace("\n", " "),
                        }
                        for i, c in enumerate(result.chunks)
                    ],
                }
                warn = f" [DEGRADED {result.degradations} - not comparable]" if run["degraded"] else ""
                thr = f" (throttle {result.throttle_wait_s:.1f}s)" if result.throttle_wait_s else ""
                print(f"  -> {len(result.chunks)} results, {wall:.2f}s{thr}, "
                      f"${result.total_cost:.5f}{warn}", flush=True)
            except Exception as exc:  # a failed pipeline must not stop the sweep
                run = {
                    "pipeline": name, "mode": config.rerank.mode, "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "wall_s": round(time.perf_counter() - t0, 3),
                }
                print(f"  -> FAILED: {type(exc).__name__}: {exc}", flush=True)
            report["runs"].append(run)
    finally:
        await close_luna(); await close_cohere(); await close_rerank()
        await close_api_keys(); await close_embed(); await close_qdrant()
        await close_pool(); await close_llm()

    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nreport -> {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
