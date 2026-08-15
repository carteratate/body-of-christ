# services/api/compare_batch/runner.py
"""Async batch runner: calls /v1/search/compare for each query, writes JSONL."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path

from compare_batch.queries import QuerySpec
from app.rag.compare.methodology import fingerprint as methodology_fingerprint
from app.rag.compare.methodology import snapshot as methodology_snapshot

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


def _batch_fingerprint(
    queries: list[QuerySpec], pipelines: list[str], collections: list[str], quota: int,
    concurrency: int = 3,
    base_url: str = "http://localhost:8000",
) -> str:
    """Fingerprint every input and methodology that makes a resume comparable."""
    methodology = methodology_snapshot(pipelines)
    deployment = methodology["deployment"]
    if not deployment["build_id"] or not deployment["corpus_id"]:
        raise ValueError(
            "Resumable comparisons require EVALUATION_BUILD_ID and "
            "EVALUATION_CORPUS_ID so deployments and corpus snapshots cannot mix."
        )
    payload = {
        "queries": [
            {
                "query": query.query,
                "category": query.category,
                "expected_collections": query.expected_collections,
            }
            for query in queries
        ],
        "pipelines": pipelines,
        "methodology": methodology,
        "collections": collections,
        "quota": quota,
        # Concurrency changes shared-throttle/latency behavior, while the endpoint
        # identifies which deployed corpus and implementation produced the run.
        "concurrency": concurrency,
        "base_url": base_url.rstrip("/"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return methodology_fingerprint({"batch": json.loads(canonical)})


def _validate_resume_file(output_path: Path, expected_fingerprint: str) -> None:
    """Reject historical or differently configured artifacts before appending."""
    if not output_path.exists():
        return
    lines = output_path.read_text().splitlines(keepends=True)
    repaired_truncated_tail = False
    seen_query_indices: set[int] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if line_number != len(lines):
                raise ValueError(
                    f"Cannot resume {output_path}: malformed record on line "
                    f"{line_number} is not the final truncated write."
                )
            # Remove only the incomplete final write before append, including a
            # non-newline tail that would otherwise concatenate with new JSON.
            output_path.write_text("".join(lines[:line_number - 1]))
            repaired_truncated_tail = True
            break
        if record.get("batch_fingerprint") != expected_fingerprint:
            raise ValueError(
                f"Cannot resume {output_path}: record on line {line_number} was "
                "created with a different or legacy batch methodology/config. "
                "Use a new output file."
            )
        query_idx = record.get("query_idx")
        if (
            isinstance(query_idx, bool)
            or not isinstance(query_idx, int)
            or query_idx < 0
        ):
            raise ValueError(
                f"Cannot resume {output_path}: line {line_number} has an invalid query_idx."
            )
        if query_idx in seen_query_indices:
            raise ValueError(
                f"Cannot resume {output_path}: duplicate query_idx {query_idx}."
            )
        seen_query_indices.add(query_idx)
    # A valid final JSON object without a newline is still unsafe to append to:
    # the next object would be concatenated onto it and corrupt both records.
    if (
        not repaired_truncated_tail
        and lines
        and lines[-1].strip()
        and not lines[-1].endswith("\n")
    ):
        with output_path.open("a") as output_file:
            output_file.write("\n")


@contextmanager
def _exclusive_batch_lock(output_path: Path):
    """Reject concurrent writers across processes for one batch artifact."""
    import fcntl

    lock_path = output_path.with_suffix(output_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"Another batch process is already writing {output_path}"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
    batch_fingerprint: str,
) -> None:
    import aiohttp

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
    expected_methodology = methodology_snapshot(pipelines)
    if data.get("methodology") != expected_methodology:
        logger.error(
            "[%d] server methodology differs from this batch runner; refusing record",
            idx,
        )
        return
    record = {
        "query_idx": idx,
        "batch_fingerprint": batch_fingerprint,
        "query": spec.query,
        "category": spec.category,
        "expected_collections": spec.expected_collections,
        "duration_s": round(duration, 2),
        "pricing": data.get("pricing"),
        "methodology": data.get("methodology"),
        "judge": data.get("judge"),
        "pipeline_results": [
            {
                "pipeline": r["pipeline"],
                "rerank_contract_version": r.get("rerank_contract_version"),
                "total_duration_s": r["total_duration_s"],
                "total_cost": r["total_cost"],
                "chunk_count": len(r["chunks"]),
                "quality_eligible": r.get("quality_eligible", False),
                "latency_eligible": r.get("latency_eligible", False),
                "cost_eligible": r.get("cost_eligible", False),
                "degradation_events": r.get("degradation_events", []),
                "recovery_events": r.get("recovery_events", []),
                "outcome": r.get("outcome"),
            }
            for r in data.get("pipeline_results", [])
        ],
    }

    async with lock:
        with output_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    logger.info("[%d/%d] done in %.1fs", idx + 1, total, duration)


async def _run_batch_locked(
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
    import aiohttp

    fingerprint = _batch_fingerprint(
        queries, pipelines, collections, quota, concurrency, base_url,
    )
    _validate_resume_file(output_path, fingerprint)
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
                fingerprint,
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


async def run_batch(
    queries: list[QuerySpec],
    output_path: Path,
    pipelines: list[str] = ALL_PIPELINES,
    collections: list[str] = ALL_COLLECTIONS,
    quota: int = 4,
    concurrency: int = 3,
    base_url: str = "http://localhost:8000",
) -> None:
    """Run or safely resume a batch under an inter-process artifact lock."""
    with _exclusive_batch_lock(output_path):
        await _run_batch_locked(
            queries, output_path, pipelines, collections, quota, concurrency, base_url,
        )
