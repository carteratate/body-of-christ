"""Position+cosine dedup and per-source cap for post-scoring results.

apply_dedup(ranked) drops the lower-scorer in any pair from the same document
where abs(position_a - position_b) <= 2 AND cosine_similarity > 0.9, then
caps results at 2 per *source* (see `source_key`). Input must already be sorted
descending by reranker_score (the pipeline's global sort precedes this call).

The cap exists for source diversity: without it a single work can fill a
collection's entire quota. What counts as "a source" is not uniform across the
corpus, which is why `source_key` exists rather than a bare document_title —
see its docstring.
"""
from __future__ import annotations

import logging
import math

from app.rag.qdrant_client import QDRANT_COLLECTION, get_qdrant_client
from app.rag.steps.types import RankedChunk

logger = logging.getLogger(__name__)

_COSINE_THRESHOLD = 0.9
_POSITION_PROXIMITY = 2
_PER_SOURCE_CAP = 2

# Collections stored as ONE document whose title names the whole corpus rather
# than a distinct work. Keying the cap on document_title for these limits the
# ENTIRE collection to _PER_SOURCE_CAP results per search — measured against the
# 80-query eval suite, the Summa (49.5% of the corpus, one document titled
# "Summa Theologiae") hit that ceiling in 41 of 80 queries and never returned a
# third result. For these the cap keys on the reader chapter instead.
#
# What a chapter IS differs by collection, and only the mechanism is uniform:
# a Summa chapter is one article (3,120 of them, ~9 chunks each); a Canon Law
# chapter is a Book/Title/Chapter division (233, ~7 each); a Catechism chapter
# is a mechanical 100-paragraph pagination bucket ("CCC §§600–699" — 29 of them,
# ~28 each), NOT a topical section. Measured on real FTS results the Catechism
# still benefits (a top-12 spreads across 1–10 buckets, so the ceiling rises
# from 2 to ~4-8), just less cleanly than the Summa.
#
# COST: raising these ceilings grows the final result set. Simulated over 400
# Summa-dominant 40-candidate pools at quota=5, mean results/search went 21.8 ->
# 26.4 (+4.6, ~+21%). Each extra result costs one SEQUENTIAL explanation stream
# (pipeline.py step 9) plus a DB write, so this is real latency and spend — though
# chunks stream before explanations, so time-to-first-result is unchanged. quota is
# bounded 3-5 (models/search.py), capping the worst case at +9 per search.
_CHAPTER_KEYED_COLLECTIONS: frozenset[str] = frozenset({
    "summa", "catechism", "canon-law",
})


def chapter_grain_collections(chunks: list[RankedChunk]) -> frozenset[str]:
    """Which collections may use the chapter grain for THIS result set.

    Only collections actually present in `chunks` are returned, so the result
    describes what was decided rather than restating the configured set.

    The grain is decided per collection, once — never per chunk, because a result set
    can carry chapter_key on some chunks and not others. `retrieve_fts` selects it
    directly; Qdrant-sourced candidates depend on `fetch_positions` backfilling it
    from Postgres, and that backfill is skipped wholesale when the pool is
    unavailable or its query fails (see fetch_positions.run). Deciding per chunk
    would then open two disjoint buckets for one collection and admit
    `_PER_SOURCE_CAP` from each — making the degraded path LOOSER than the healthy
    one, and surfacing exactly the same-article redundancy the cap exists to prevent.
    Excluding the whole collection instead makes the degraded path fall back to
    precisely the pre-change behaviour.

    Note the Qdrant side of that mix is a property of the data, not of the schema:
    `build_point` has never written chapter_key, but
    `datapipeline/scripts/reconcile_qdrant_payloads.py --fields structural` backfills
    it into existing payloads without re-embedding. Once that has run for a
    collection, its candidates carry chapter_key regardless of `fetch_positions`, and
    this demotion stops being reachable for it — which is the point of running it.
    """
    present = {chunk.collection for chunk in chunks} & _CHAPTER_KEYED_COLLECTIONS
    incomplete = {
        chunk.collection
        for chunk in chunks
        if chunk.collection in present and not chunk.chapter_key
    }
    demoted = present & incomplete
    if demoted:
        logger.info(
            "dedup: chapter grain unavailable for %s (missing chapter_key on at "
            "least one candidate); falling back to the per-title grain, which "
            "caps each of those collections at %d results for this search",
            sorted(demoted), _PER_SOURCE_CAP,
        )
    return frozenset(present - incomplete)


def source_key(chunk: RankedChunk, chapter_grain: frozenset[str]) -> tuple[str, ...]:
    """The unit the per-source cap counts against.

    Returns a variable-length tuple, never a delimited string: the two kinds have
    different arities, so a title can never collide with a chapter key however
    either is punctuated.

    `collection` is part of both keys. Migration 0014 is
    UNIQUE(collection, title, translation, author) — `collection` is IN the
    constraint, so the same title may legitimately exist in two collections, and
    keying without it would merge two unrelated works into one bucket. No such
    pair exists in the corpus today (verified 2026-08-19), so this is structural
    protection rather than a live fix.

    Both branches then key on document_title rather than document_id, deliberately:
    `translation` is also in that constraint, so one work may hold several
    documents (one per translation). Keying on document_id would give each
    translation its own full allowance and return the same passage twice.

    Known, pre-existing consequence: church-fathers holds 128 documents under 127
    titles — Polycarp's and Ignatius' `Epistle to the Philippians` are distinct
    works sharing a title *within one collection*, so they share a bucket. Keying
    on document_id would fix that but would break the translation case above,
    which is the more common one.

    Callers must derive `chapter_grain` from the SAME list they then key, via
    `chapter_grain_collections`. Passing a grain computed from a different list can
    put a collection in the grain while some chunk of it has no chapter_key; the
    guard below keeps that safe (such a chunk falls back to the title key rather
    than joining a shared null-keyed bucket) but the resulting mix of grains within
    one collection is not a meaningful cap — compute the two together.
    """
    if chunk.collection in chapter_grain and chunk.chapter_key:
        return ("chapter", chunk.collection, chunk.document_title, chunk.chapter_key)
    return ("title", chunk.collection, chunk.document_title)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


async def apply_dedup(ranked: list[RankedChunk]) -> list[RankedChunk]:
    """Drop cosine-close adjacent duplicates and apply the per-source cap.

    Assumes `ranked` is already sorted descending by reranker_score.
    """
    # 1. Find pairs within _POSITION_PROXIMITY in the same document
    by_doc: dict[str, list[RankedChunk]] = {}
    for chunk in ranked:
        if chunk.include:
            by_doc.setdefault(chunk.document_id, []).append(chunk)

    close_pairs: list[tuple[str, str]] = []
    for chunks in by_doc.values():
        for i, a in enumerate(chunks):
            for b in chunks[i + 1:]:
                if (
                    a.position is not None
                    and b.position is not None
                    and abs(a.position - b.position) <= _POSITION_PROXIMITY
                ):
                    close_pairs.append((a.chunk_id, b.chunk_id))

    # 2. Fetch vectors for close pairs and compute cosine similarity
    to_drop: set[str] = set()
    if close_pairs:
        close_ids = {cid for pair in close_pairs for cid in pair}
        client = get_qdrant_client()
        if client is not None:
            try:
                points = await client.retrieve(
                    collection_name=QDRANT_COLLECTION,
                    ids=list(close_ids),
                    with_vectors=True,
                )
                vec_map: dict[str, list[float]] = {
                    str(p.id): p.vector
                    for p in points
                    if p.vector is not None
                }
                score_map = {r.chunk_id: r.reranker_score for r in ranked}
                for id_a, id_b in close_pairs:
                    if id_a in to_drop or id_b in to_drop:
                        continue
                    vec_a = vec_map.get(id_a)
                    vec_b = vec_map.get(id_b)
                    if vec_a is None or vec_b is None:
                        continue
                    if _cosine_sim(vec_a, vec_b) > _COSINE_THRESHOLD:
                        drop = (
                            id_a if score_map.get(id_a, 0.0) < score_map.get(id_b, 0.0) else id_b
                        )
                        to_drop.add(drop)
            except Exception as exc:
                logger.warning("apply_dedup: Qdrant vector fetch failed, skipping cosine check: %s", exc)

    # 3. Apply cosine dedup + per-source cap in one pass (input already score-sorted).
    # The grain is resolved against the surviving set, so a chunk that cosine dedup
    # already dropped cannot demote its whole collection to the title grain.
    survivors = [c for c in ranked if c.include and c.chunk_id not in to_drop]
    chapter_grain = chapter_grain_collections(survivors)
    source_counts: dict[tuple[str, ...], int] = {}
    final: list[RankedChunk] = []
    for chunk in survivors:
        key = source_key(chunk, chapter_grain)
        count = source_counts.get(key, 0)
        if count < _PER_SOURCE_CAP:
            source_counts[key] = count + 1
            final.append(chunk)
    return final
