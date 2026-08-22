"""Fetch the passages that complete a Summa result.

One batched query after the result set is final: a single round trip per search, and
nothing at all for the majority of searches, which return no Summa objection or reply.

WHY WHOLE ARTICLES RATHER THAN JUST THE PIECE WANTED
`chapter_key` is not an article boundary. 3 of 3,120 keys hold two complete disputations
— `.../article-10-whether-the-brave-man-makes-use-of-anger...` carries both Article 10
and the article after it, which also inherits Article 10's `reference` string. Selecting
"the determination for this chapter_key" would return TWO unrelated determinations and
glue them into one answer, and 10 keys carry a duplicate `Objection N` label, so
selecting an objection by (key, number) would be a coin flip between two articles.

So the query returns every passage of each key and `stitch` finds what a result needs by
scanning its neighbours. That also needs the roles this feature does not attach: a scan
stops at a sed contra's or a reply's position, which is how it knows not to walk into a
neighbouring article. A query filtered to one label could serve none of it.

Deliberately runs AFTER `quota_cap`: an attached passage is presentation, not a result,
so it must not consume a slot the user's quota would otherwise give to a real passage.
"""
from __future__ import annotations

import logging

from app.db import get_pool
from app.rag.steps import degradation
from app.rag.steps.types import RankedChunk

logger = logging.getLogger(__name__)

# Every passage of each article, in document order. `position` ordering is load-bearing
# twice over: it is the order the neighbour scans walk, and it is what keeps a split
# determination (109 of 3,120 keys) in reading order rather than presenting its halves
# backwards.
_SQL = """
    SELECT c.id::text AS chunk_id, c.content, c.reference, c.anchor, c.chapter_key,
           c.position, c.unit_label, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.chapter_key = ANY($1::text[])
      AND d.collection = 'summa'
    ORDER BY c.document_id, c.chapter_key, c.position
"""


def _to_chunk(row) -> RankedChunk:
    return RankedChunk(
        chunk_id=row["chunk_id"], content=row["content"], reference=row["reference"],
        collection=row["collection"], document_id=row["document_id"],
        document_title=row["document_title"], author=row["author"],
        # Not a scored result — fetched because another passage needed it.
        # `score_source` says so, so nothing downstream can mistake this for a measured
        # relevance judgement.
        reranker_score=0.0, include=True, anchor=row["anchor"],
        chapter_key=row["chapter_key"], position=row["position"],
        unit_label=row["unit_label"], score_source="stitched",
    )


async def articles(chapter_keys: set[str]) -> dict[tuple[str, str], list[RankedChunk]]:
    """(document_id, chapter_key) -> every passage under that key, in position order.

    Keyed by document as well: `chapter_key` is unique only within a document, and
    migrations 0008/0014 exist so a second translation of the Summa can be loaded. Keyed
    by chapter_key alone, that day two documents' passages would merge into one bucket
    with overlapping positions, and a neighbour scan could cross between translations.

    Best-effort by design, and recorded via `record_recovery`, NOT `record`. A
    degradation would mark the run quality- and latency-ineligible and get the whole
    eval row discarded (`compare/persist.py`), and under `DegradationPolicy.RAISE` the
    record call itself raises — turning a missing presentation flourish into a failed
    search, which is exactly what "best-effort" is supposed to preclude. Nothing about
    retrieval or ranking changed here, so the result stays comparable.

    A failure means Summa passages are shown unattached: the behaviour before stitching
    existed, and still honest, because `unit_label` marks the passage's role and the
    explanation model is told what that role means.
    """
    if not chapter_keys:
        return {}

    pool = get_pool()
    if pool is None:
        logger.warning("fetch_context: no DB pool; results stay unstitched")
        degradation.record_recovery(
            "fetch_context", "pool_unavailable", "results_unstitched",
            scope="summa", details={"article_count": len(chapter_keys)},
        )
        return {}

    try:
        rows = await pool.fetch(_SQL, sorted(chapter_keys))
    except Exception as exc:
        logger.warning("fetch_context: lookup failed: %s", exc)
        degradation.record_recovery(
            "fetch_context", type(exc).__name__, "results_unstitched",
            scope="summa",
            details={"message": str(exc)[:300], "article_count": len(chapter_keys)},
        )
        return {}

    out: dict[tuple[str, str], list[RankedChunk]] = {}
    for row in rows:
        out.setdefault((row["document_id"], row["chapter_key"]), []).append(_to_chunk(row))

    missing = len(chapter_keys) - len({key for _, key in out})
    if missing:
        logger.info("fetch_context: %d of %d key(s) returned no passages",
                    missing, len(chapter_keys))
    return out
