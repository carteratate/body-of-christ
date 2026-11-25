"""A passage's footnotes, shown with it: the Catechism's own notes (issue #279), and the
scripture references the Fathers' and medieval translators gave in their notes
(corpus-cleanup 1.10b).

The USCCB's rules for its English Catechism require footnoted material to be
identified. The datapipeline writes each passage's notes to `chunks.metadata.footnotes`
as `[{n, text, at}]`: the Catechism's own note number, the note text, and the character
offset in `content` where its marker sits. Notes are never part of `content`, so they
stay out of the embedding input and the keyword index.

`fetch_footnotes` is the one reader. Footnotes never fail a response: a missing or
malformed value, or a failed query, gives a passage no notes.
"""
from __future__ import annotations

import asyncio
import logging

from app.reader_access import CATECHISM_TITLE

logger = logging.getLogger(__name__)

_FOOTNOTES_SQL = """
    SELECT id::text AS id, metadata->'footnotes' AS footnotes
    FROM chunks WHERE id = ANY($1::uuid[])
"""

# Notes are optional, so a slow lookup must not hold up the response it decorates.
_TIMEOUT_SECONDS = 2.0


# Collections whose translators' notes give scripture references (1.10b).
_SCRIPTURE_NOTE_COLLECTIONS = frozenset({"church-fathers", "theologians"})


def has_footnotes(collection: str | None, document_title: str | None) -> bool:
    """Whether a passage's notes are looked up. In the catechism collection it is keyed
    on the document, like `reader_access.source_credit`: the Catechism, not every
    catechism-collection text. A Fathers or medieval passage may carry scripture
    references; one without them simply has none."""
    if collection in _SCRIPTURE_NOTE_COLLECTIONS:
        return True
    return collection == "catechism" and document_title == CATECHISM_TITLE


def _validated(value, content: str) -> list[dict] | None:
    """The notes in `value`, [] when absent, None when malformed."""
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    notes = []
    for item in value:
        if not isinstance(item, dict):
            return None
        n, text, at = item.get("n"), item.get("text"), item.get("at")
        if (
            not isinstance(n, int) or isinstance(n, bool) or n <= 0
            or not isinstance(text, str) or not text.strip()
            or not isinstance(at, int) or isinstance(at, bool)
            or not 0 <= at <= len(content)
        ):
            return None
        notes.append({"n": n, "text": text, "at": at})
    return notes


async def fetch_footnotes(pool, items: list[tuple[str, str]]) -> dict[str, list[dict]]:
    """The notes of each `(chunk_id, content)`, keyed by chunk id.

    Callers pass only passages for which `has_footnotes` holds, with the content they
    already hold (offsets are checked against it). `pool` may be a pool or a connection.
    """
    items = [(str(chunk_id), content or "") for chunk_id, content in items]
    if not items:
        return {}
    if pool is None:
        logger.warning("footnotes: no database pool; passages shown without notes")
        return {chunk_id: [] for chunk_id, _ in items}
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            rows = await pool.fetch(
                _FOOTNOTES_SQL, sorted({chunk_id for chunk_id, _ in items}),
            )
    except Exception as exc:
        logger.warning(
            "footnotes: query failed (%s); passages shown without notes",
            exc.__class__.__name__,
        )
        return {chunk_id: [] for chunk_id, _ in items}

    stored = {str(row["id"]): row["footnotes"] for row in rows}
    result: dict[str, list[dict]] = {}
    for chunk_id, content in items:
        notes = _validated(stored.get(chunk_id), content)
        if notes is None:
            logger.warning("footnotes: malformed footnotes on chunk %s; not shown", chunk_id)
            notes = []
        result[chunk_id] = notes
    return result
