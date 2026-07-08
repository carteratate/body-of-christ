"""Embed stage: content -> chunks.dense; each facet -> facets; each question -> questions."""
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
    prefix = f"{doc.author or ''} — {doc.title}, {passages[idx].chapter_label} "
    return build_embedding_input(passages, idx, k_prev, k_next, prefix)


@dataclass
class EmbedDeps:
    cache: Cache
    embed_client: object
    qdrant: object
    # Both hooks are async callables so embed_chunk can await them directly —
    # this mirrors EnrichDeps.annotation_writer's convention (stages/enrich.py)
    # and avoids mixing sync callbacks with async upserts in embed_collection.
    upsert_chunk_point: Callable[[PointStruct], Awaitable[None]]
    upsert_points_named: Callable[[str, list[PointStruct]], Awaitable[None]]


async def _cached_embed(deps: EmbedDeps, cid: str, ch: str, vtype: str, text: str) -> list[float]:
    cached = deps.cache.get_embedding(cid, ch, vtype)
    if cached is not None:
        return cached
    vec = (await deps.embed_client.embed([text]))[0]
    deps.cache.put_embedding(cid, ch, vtype, vec)
    return vec


async def embed_chunk(doc: Document, passages: list[Passage], idx: int,
                      merged_facets: list[dict], deps: EmbedDeps) -> None:
    p = passages[idx]
    cid = passage_id(doc.id, p.anchor)
    ch = Cache.content_hash(p.content)

    # content -> chunks.dense
    content_vec = await _cached_embed(deps, cid, ch, "content", content_embedding_input(passages, idx, doc))
    await deps.upsert_chunk_point(build_point(doc, p, content_vec))

    # facets -> facets ; questions -> questions
    facet_points: list[PointStruct] = []
    question_points: list[PointStruct] = []
    for i, f in enumerate(merged_facets):
        fvec = await _cached_embed(deps, cid, ch, f"facet:{i}", f["text"])
        facet_points.append(PointStruct(
            id=passage_id(cid, f"facet/{i}"),
            vector=fvec,
            payload={"chunk_id": cid, "document_id": doc.id, "collection": doc.collection,
                     "facet_index": i, "confidence": f["confidence"], "kind": f["kind"],
                     "facet_text": f["text"]}))
        qvec = await _cached_embed(deps, cid, ch, f"question:{i}", f["question"])
        question_points.append(PointStruct(
            id=passage_id(cid, f"question/{i}"),
            vector=qvec,
            payload={"chunk_id": cid, "document_id": doc.id, "collection": doc.collection,
                     "facet_index": i, "facet_confidence": f["confidence"], "facet_kind": f["kind"],
                     "facet_text": f["text"], "question": f["question"]}))
    await deps.upsert_points_named(FACETS, facet_points)
    await deps.upsert_points_named(QUESTIONS, question_points)


async def embed_collection(docs: list[Document], cache: Cache, embed_client, qdrant) -> None:
    """Embed every chunk of every doc whose merged enrichment is already cached.

    Chunk points are buffered and flushed in EMBEDDING_BATCH_SIZE batches (matching
    write_document's batching in writers/search_writer.py); facet/question points
    are upserted per-chunk since they're already small per-call batches.
    """
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

    deps = EmbedDeps(cache=cache, embed_client=embed_client, qdrant=qdrant,
                     upsert_chunk_point=_stash_chunk,
                     upsert_points_named=_upsert_named)

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
