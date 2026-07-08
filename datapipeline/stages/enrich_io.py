"""Supabase side effects for the enrich stage (kept out of the pure stage logic)."""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable

_SEGMENT_LABEL_RE = re.compile(r"\[[^\]]*\]:\s*")


def annotation_prose(annotation: str) -> str:
    """Strip `[KIND | confidence]:` segment labels to plain prose for tsvector indexing."""
    cleaned = _SEGMENT_LABEL_RE.sub("", annotation)
    cleaned = cleaned.replace("SUMMARY:", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def make_annotation_writer(pool) -> Callable[[str, str], Awaitable[None]]:
    async def writer(chunk_id: str, annotation: str) -> None:
        prose = annotation_prose(annotation)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE chunks SET annotation = $1 WHERE id = $2::uuid",
                    json.dumps(annotation), chunk_id)
                await conn.execute(
                    "UPDATE chunks SET annotation_vector = to_tsvector('english', $1) "
                    "WHERE id = $2::uuid", prose, chunk_id)
    return writer
