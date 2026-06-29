# services/api/app/rag/compare/runner.py
"""Runs multiple pipeline variants sequentially against the same query."""
from __future__ import annotations

import logging

from app.rag.pipelines.registry import PIPELINES
from app.rag.pipelines.runner import run as run_pipeline
from app.rag.steps.types import PipelineResult

logger = logging.getLogger(__name__)


async def run(
    query: str,
    collections: list[str],
    quota: int,
    pipeline_names: list[str],
    user_id: str | None = None,
) -> list[PipelineResult]:
    """Run each named pipeline sequentially. Returns results in order.

    Raises ValueError for unknown pipeline names.
    """
    results: list[PipelineResult] = []
    for name in pipeline_names:
        config = PIPELINES.get(name)
        if config is None:
            raise ValueError(f"Unknown pipeline: {name!r}. Valid: {sorted(PIPELINES)}")
        logger.info("compare/runner: starting pipeline=%s", name)
        result = await run_pipeline(config, query, collections, quota, user_id)
        results.append(result)
        logger.info(
            "compare/runner: finished pipeline=%s duration=%.2fs cost=$%.6f",
            name, result.total_duration_s, result.total_cost,
        )
    return results
