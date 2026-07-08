"""Enrich stage: two-call Opus per chunk -> cache + JSONL backup + Supabase annotation."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from cache import Cache
from config import settings
from identity import passage_id
from model import Document, Passage
from enrichment.backup import Backup
from enrichment.client import Usage
from enrichment.merge import merge
from enrichment.render import build_context
from enrichment.prompts.generation import generation_system
from enrichment.prompts.classification import CLASSIFICATION_SYSTEM
from enrichment.schema import GenerationOutput, MergedEnrichment


@dataclass
class EnrichDeps:
    cache: Cache
    client: object                      # EnrichmentClient (duck-typed for tests)
    backup: Backup
    annotation_writer: Callable[[str, str], Awaitable[None]]


@dataclass
class EnrichStats:
    processed: int
    from_cache: int
    usage: Usage


async def enrich_one(doc: Document, passage: Passage, deps: EnrichDeps,
                     *, sample: bool) -> tuple[MergedEnrichment, Usage]:
    cid = passage_id(doc.id, passage.anchor)
    ch = Cache.content_hash(passage.content)
    gen_system = generation_system(doc.collection)
    gen_prompt_hash = Cache.prompt_hash(gen_system)
    cls_prompt_hash = Cache.prompt_hash(CLASSIFICATION_SYSTEM)
    context = build_context(doc, passage)
    total = Usage(0, 0)

    # 0. fully-merged cache hit -> skip everything (production only)
    if not sample:
        cached = deps.cache.get_enrichment(cid, ch)
        if cached is not None:
            return MergedEnrichment.model_validate(cached), total

    # 1. generation (cache unless prompt changed)
    gen_cached = None if sample else deps.cache.get_generation(cid, ch)
    if gen_cached is not None and gen_cached["prompt_hash"] == gen_prompt_hash:
        generation = GenerationOutput.model_validate(
            {"facets": gen_cached["raw_facets"], "annotation": gen_cached["annotation"]})
    else:
        generation, gu = await deps.client.generate(gen_system, context)
        total = Usage(total.input_tokens + gu.input_tokens, total.output_tokens + gu.output_tokens)
        raw_facets = [f.model_dump() for f in generation.facets]
        if not sample:
            deps.backup.write(doc.collection, {
                "chunk_id": cid, "content_hash": ch, "stage": "generation",
                "collection": doc.collection, "reference": passage.reference,
                "raw_facets": raw_facets, "annotation": generation.annotation,
                "prompt_hash": gen_prompt_hash})
            deps.cache.put_generation(cid, ch, raw_facets, generation.annotation, gen_prompt_hash)

    # 2. classification (cache unless prompt changed)
    cls_cached = None if sample else deps.cache.get_classification(cid, ch)
    if cls_cached is not None and cls_cached["prompt_hash"] == cls_prompt_hash:
        from enrichment.schema import ClassificationOutput
        classification = ClassificationOutput.model_validate({"labels": cls_cached["labels"]})
    else:
        classification, cu = await deps.client.classify(
            CLASSIFICATION_SYSTEM, context, [f.text for f in generation.facets])
        total = Usage(total.input_tokens + cu.input_tokens, total.output_tokens + cu.output_tokens)
        labels = [lab.model_dump() for lab in classification.labels]
        if not sample:
            deps.backup.write(doc.collection, {
                "chunk_id": cid, "content_hash": ch, "stage": "classification",
                "collection": doc.collection, "labels": labels, "prompt_hash": cls_prompt_hash})
            deps.cache.put_classification(cid, ch, labels, cls_prompt_hash)

    # 3. merge + persist
    merged = merge(generation, classification)
    if not sample:
        deps.cache.put_enrichment(cid, ch, [f.model_dump() for f in merged.facets], merged.annotation)
        await deps.annotation_writer(cid, merged.annotation)
    return merged, total


async def enrich_collection(docs: list[Document], collection: str, deps: EnrichDeps,
                            *, sample: bool = False) -> EnrichStats:
    passages = [(d, p) for d in docs for p in d.passages]
    total = Usage(0, 0)
    from_cache = 0
    sem = asyncio.Semaphore(settings.OPUS_CONCURRENCY)

    async def _run(d, p):
        nonlocal total, from_cache
        async with sem:
            _, usage = await enrich_one(d, p, deps, sample=sample)
        total = Usage(total.input_tokens + usage.input_tokens,
                      total.output_tokens + usage.output_tokens)
        if usage.input_tokens == 0:
            from_cache += 1

    await asyncio.gather(*[_run(d, p) for d, p in passages])
    if not sample:
        deps.cache.set_collection_status(
            collection, total_chunks=len(passages),
            enriched=len(passages), complete=True)
    return EnrichStats(processed=len(passages), from_cache=from_cache, usage=total)
