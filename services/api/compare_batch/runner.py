# services/api/compare_batch/runner.py
"""Async batch runner: calls /v1/search/compare for each query, writes JSONL."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import aiohttp

from compare_batch.queries import QuerySpec

logger = logging.getLogger(__name__)

ALL_COLLECTIONS = [
    "bible", "catechism", "summa", "encyclicals", "councils",
    "church-fathers", "medieval", "canon-law", "apostolic-exhortations",
    "papal-documents",
]

ALL_PIPELINES = ["hyde_haiku", "hyde_cohere", "hyde_cohere_haiku", "hyde_cohere_luna"]


def _load_completed_indices(output_path: Path) -> set[int]:
    """Return query_idx values already written to the JSONL file."""
    if not output_path.exists():
        return set()
    completed: set[int] = set()
    with output_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                completed.add(obj["query_idx"])
            except (json.JSONDecodeError, KeyError):
                pass
    return completed


async def _run_one(
    session: aiohttp.ClientSession,
    idx: int,
    total: int,
    spec: QuerySpec,
    pipelines: list[str],
    collections: list[str],
    quota: int,
    base_url: str,
    sem: asyncio.Semaphore,
    output_path: Path,
    lock: asyncio.Lock,
) -> None:
    payload = {
        "query": spec.query,
        "collections": collections,
        "quota": quota,
        "pipelines": pipelines,
    }
    async with sem:
        t0 = time.monotonic()
        logger.info("[%d/%d] starting: %s", idx + 1, total, spec.query[:60])
        try:
            async with session.post(
                f"{base_url}/v1/search/compare",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("[%d] HTTP %d: %s", idx, resp.status, body[:200])
                    return
                data = await resp.json()
        except Exception as exc:
            logger.error("[%d] request failed: %s", idx, exc)
            return

    duration = time.monotonic() - t0
    record = {
        "query_idx": idx,
        "query": spec.query,
        "category": spec.category,
        "expected_collections": spec.expected_collections,
        "duration_s": round(duration, 2),
        "pricing": data.get("pricing"),
        "judge": data.get("judge"),
        "pipeline_results": [
            {
                "pipeline": r["pipeline"],
                "total_duration_s": r["total_duration_s"],
                "total_cost": r["total_cost"],
                "chunk_count": len(r["chunks"]),
            }
            for r in data.get("pipeline_results", [])
        ],
    }

    async with lock:
        with output_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    logger.info("[%d/%d] done in %.1fs", idx + 1, total, duration)


async def run_batch(
    queries: list[QuerySpec],
    output_path: Path,
    pipelines: list[str] = ALL_PIPELINES,
    collections: list[str] = ALL_COLLECTIONS,
    quota: int = 4,
    concurrency: int = 3,
    base_url: str = "http://localhost:8000",
) -> None:
    """Run all queries against the compare endpoint, writing results to JSONL.

    Skips queries whose query_idx already appears in output_path (resumable).
    """
    completed = _load_completed_indices(output_path)
    remaining = [(i, q) for i, q in enumerate(queries) if i not in completed]

    if not remaining:
        logger.info("All %d queries already completed.", len(queries))
        return

    logger.info(
        "Running %d queries (%d already done). concurrency=%d  output=%s",
        len(remaining), len(completed), concurrency, output_path,
    )

    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=concurrency + 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _run_one(
                session, idx, len(queries), spec,
                pipelines, collections, quota, base_url,
                sem, output_path, lock,
            )
            for idx, spec in remaining
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                logger.error("_run_one[%d] raised unexpectedly: %s", i, r)

    total_done = len(_load_completed_indices(output_path))
    logger.info(
        "Batch complete: %d/%d queries written to %s",
        total_done, len(queries), output_path,
    )
