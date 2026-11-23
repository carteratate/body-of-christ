"""The headings inside a passage (issue #445), sent with it so the web can set them.

Adapters keep a heading in the text of the passage it introduces. The datapipeline marks
it in `chunks.metadata.headings` as `[{at, end, level, role, pairs_next?,
chapter_title?}]`: character offsets of one whole paragraph of `content`, `role`
"heading" (with `level` 1 to 3) or "epigraph", `pairs_next` on a level label printed
before its title, and `chapter_title` on a level-1 heading that repeats its chapter
label (`datapipeline/headings.py` is the contract). `content` never changes, so search
and embeddings do not see the marks.

`fetch_headings` reads them for search results, restored searches, bookmarks and the
reader, in a query of its own after the passages are read. Headings never fail
a response: a missing key gives none, and a malformed value, or a failed query, gives
the passage none and is logged.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_HEADINGS_SQL = """
    SELECT id::text AS id, metadata->'headings' AS headings
    FROM chunks WHERE id = ANY($1::uuid[])
"""

# Headings are optional, so a slow lookup must not hold up the response it decorates.
# The facts lookup's bound (`document_facts.TIMEOUT_SECONDS`): run beside it after a
# restore's deadline, headings add no wait of their own.
_TIMEOUT_SECONDS = 1.0

_ROLES = ("heading", "epigraph")
_LEVELS = (1, 2, 3)


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validated(value, content: str) -> list[dict] | None:
    """The marks in `value` in reading order, [] when absent, None when malformed: a
    mark outside `content`, overlapping another, with an unknown role, or a heading
    without a level 1 to 3."""
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    marks = []
    for item in value:
        if not isinstance(item, dict):
            return None
        at, end, role, level = item.get("at"), item.get("end"), item.get("role"), item.get("level")
        if (not _int(at) or not _int(end) or not 0 <= at < end <= len(content)
                or role not in _ROLES
                or (role == "heading" and (not _int(level) or level not in _LEVELS))):
            return None
        mark = {"at": at, "end": end, "role": role}
        if role == "heading":
            mark["level"] = level
            if item.get("pairs_next") is True:
                mark["pairs_next"] = True
            if item.get("chapter_title") is True:
                mark["chapter_title"] = True
        marks.append(mark)
    marks.sort(key=lambda m: m["at"])
    if any(a["end"] > b["at"] for a, b in zip(marks, marks[1:])):
        return None
    return marks


def checked(value, content: str, chunk_id: str) -> list[dict]:
    """`validated`, with a malformed value logged and shown as none."""
    marks = validated(value, content or "")
    if marks is None:
        logger.warning("headings: malformed headings on chunk %s; not shown", chunk_id)
        return []
    return marks


async def fetch_headings(pool, items: list[tuple[str, str]]) -> dict[str, list[dict]]:
    """The headings of each `(chunk_id, content)`, keyed by chunk id. Offsets are checked
    against the content the caller holds. `pool` may be a pool or a connection."""
    items = [(str(chunk_id), content or "") for chunk_id, content in items]
    if not items:
        return {}
    if pool is None:
        return {chunk_id: [] for chunk_id, _ in items}
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            rows = await pool.fetch(
                _HEADINGS_SQL, sorted({chunk_id for chunk_id, _ in items}),
            )
        stored = {str(row["id"]): row["headings"] for row in rows}
    except Exception as exc:
        logger.warning(
            "headings: query failed (%s); passages shown without headings",
            exc.__class__.__name__,
        )
        return {chunk_id: [] for chunk_id, _ in items}

    return {chunk_id: checked(stored.get(chunk_id), content, chunk_id)
            for chunk_id, content in items}
