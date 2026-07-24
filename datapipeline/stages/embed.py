"""Embed stage: content -> chunks.dense; each facet -> facets; each question -> questions.

Embedding cache identity (see cache.py): keyed on a hash of the EXACT text sent
to the embedding model, plus model + dimensions — never on chunk_id/content_hash
+ array position. If Pass 1 regenerates facet or question text while the raw
passage content and facet count/position are unchanged (e.g. a generation
prompt tweak), the new text hashes differently and is embedded fresh; it can
never silently reuse a stale vector computed for old text that happened to
sit at the same position.

Qdrant point identity for facets/questions is still positional
(`facet/{i}`, `question/{i}`) for point ids, but every re-embed of a chunk
first deletes all existing facet/question points for that chunk_id before
upserting the fresh set. This is what prevents orphaned stale points: if
re-enrichment produces fewer facets than before, the old higher-index points
are removed rather than left behind to keep appearing in retrieval.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from qdrant_client.models import PointStruct

from cache import Cache
from config import settings
from identity import passage_id
from model import Document, Passage
from qdrant_schema import FACETS, QUESTIONS
from writers.search_writer import build_embedding_input, build_point

logger = logging.getLogger(__name__)


def content_embedding_input(passages: list[Passage], idx: int, doc: Document) -> str:
    k_prev, k_next = settings.overlap_for(doc.collection)
    author_part = f"{doc.author} — " if doc.author else ""
    prefix = f"{author_part}{doc.title}, {passages[idx].chapter_label}"
    return build_embedding_input(passages, idx, k_prev, k_next, prefix)


@dataclass
class EmbedDeps:
    cache: Cache
    embed_client: object
    qdrant: object
    # All hooks are async callables so embed_chunk can await them directly —
    # this mirrors EnrichDeps.annotation_writer's convention (stages/enrich.py)
    # and avoids mixing sync callbacks with async upserts in embed_collection.
    upsert_chunk_point: Callable[[PointStruct], Awaitable[None]]
    upsert_points_named: Callable[[str, list[PointStruct]], Awaitable[None]]
    # (collection_name, chunk_id) -> delete every existing point for that
    # chunk in that collection. Called before every facet/question upsert so
    # a shrinking facet set can't leave orphaned points behind.
    delete_points_by_chunk: Callable[[str, str], Awaitable[None]]


async def _cached_embed(deps: EmbedDeps, text: str) -> list[float]:
    input_hash = Cache.embedding_input_hash(text)
    cached = deps.cache.get_embedding(input_hash, settings.EMBEDDING_MODEL, settings.EMBEDDING_DIMS)
    if cached is not None:
        return cached
    vec = (await deps.embed_client.embed([text]))[0]
    deps.cache.put_embedding(input_hash, settings.EMBEDDING_MODEL, settings.EMBEDDING_DIMS, vec)
    return vec


async def embed_chunk(doc: Document, passages: list[Passage], idx: int,
                      merged_facets: list[dict], deps: EmbedDeps) -> None:
    p = passages[idx]
    cid = passage_id(doc.id, p.anchor)

    # content -> chunks.dense
    content_vec = await _cached_embed(deps, content_embedding_input(passages, idx, doc))
    await deps.upsert_chunk_point(build_point(doc, p, content_vec))

    # Delete this chunk's existing facet/question points BEFORE upserting the
    # fresh set. Point ids are positional (facet/{i}), so without this, a
    # re-enrichment that produces fewer facets than before would leave the old
    # higher-index points in Qdrant forever — silently corrupting retrieval
    # with stale facets that no longer exist in the current enrichment.
    await deps.delete_points_by_chunk(FACETS, cid)
    await deps.delete_points_by_chunk(QUESTIONS, cid)

    # facets -> facets ; questions -> questions
    facet_points: list[PointStruct] = []
    question_points: list[PointStruct] = []
    for i, f in enumerate(merged_facets):
        fvec = await _cached_embed(deps, f["text"])
        facet_points.append(PointStruct(
            id=passage_id(cid, f"facet/{i}"),
            vector=fvec,
            payload={"chunk_id": cid, "document_id": doc.id, "collection": doc.collection,
                     "facet_index": i, "facet_id": f.get("id"), "grounding": f["grounding"],
                     "kind": f["kind"], "kind_secondary": f.get("kind_secondary"),
                     "evidence": f["evidence"], "facet_text": f["text"],
                     # Pilot-only debug field (Pass 1's raw working treatment,
                     # before takeaway compression); None outside PILOT_MODE.
                     "working_text": f.get("working_text")}))
        qvec = await _cached_embed(deps, f["question"])
        question_points.append(PointStruct(
            id=passage_id(cid, f"question/{i}"),
            vector=qvec,
            payload={"chunk_id": cid, "document_id": doc.id, "collection": doc.collection,
                     "facet_index": i, "facet_id": f.get("id"), "facet_grounding": f["grounding"],
                     "facet_kind": f["kind"], "facet_kind_secondary": f.get("kind_secondary"),
                     "facet_text": f["text"], "question": f["question"]}))
    await deps.upsert_points_named(FACETS, facet_points)
    await deps.upsert_points_named(QUESTIONS, question_points)


async def embed_collection(docs: list[Document], cache: Cache, embed_client, qdrant) -> None:
    """Embed every chunk of every doc whose merged enrichment is already cached.

    Chunk points are buffered and flushed in EMBEDDING_BATCH_SIZE batches (matching
    write_document's batching in writers/search_writer.py); facet/question points
    are upserted per-chunk since they're already small per-call batches.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from writers.qdrant import upsert_points

    chunk_batch: list[PointStruct] = []

    async def _stash_chunk(pt: PointStruct) -> None:
        chunk_batch.append(pt)
        if len(chunk_batch) >= settings.EMBEDDING_BATCH_SIZE:
            await upsert_points(qdrant, chunk_batch)
            chunk_batch.clear()

    async def _upsert_named(collection: str, points: list[PointStruct]) -> None:
        if points:
            await qdrant.upsert(collection_name=collection, points=points, wait=True)

    async def _delete_by_chunk(collection: str, chunk_id: str) -> None:
        await qdrant.delete(
            collection_name=collection,
            points_selector=Filter(must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]),
            wait=True)

    deps = EmbedDeps(cache=cache, embed_client=embed_client, qdrant=qdrant,
                     upsert_chunk_point=_stash_chunk,
                     upsert_points_named=_upsert_named,
                     delete_points_by_chunk=_delete_by_chunk)

    for doc in docs:
        for idx, p in enumerate(doc.passages):
            cid = passage_id(doc.id, p.anchor)
            ch = Cache.content_hash(p.content)
            enr = cache.get_enrichment(cid, ch)
            if enr is None:
                logger.warning("embed: no enrichment for %s (%s) — run enrich first", cid, p.reference)
                continue
            await embed_chunk(doc, doc.passages, idx, enr["facets"], deps)

    if chunk_batch:
        await upsert_points(qdrant, chunk_batch)
