"""Enrich stage: 3-pass Anthropic pipeline per chunk -> cache + JSONL backup +
Supabase annotation.

Pass 1 (generation, Opus) produces facets, each with a working `text` treatment
and a distilled `takeaway`, with hard validation (sentence/word-count bounds,
banned openers, concreteness, anti-copy) and a retry-once-then-mark-failed
policy. Downstream of Pass 1, "facet"/"text" always means the takeaway — Pass 2
(classification, Sonnet) and Pass 3 (annotation assembly, Sonnet) never see
Pass 1's raw working text, only the takeaway. Pass 2 assigns grounding/kind/
evidence per facet, with hard validation and the same retry-once policy. Pass 3
writes the retrieval annotation from Pass 2's authoritative labels, with the
same validation/retry policy.

Cache dependency graph: each stage is cached independently, but a cache hit is
only valid when BOTH that stage's own identity (prompt hash, model, temperature,
schema version) matches AND every upstream artifact it was computed from still
hashes identically (see Cache.canonical_hash). Concretely: classification's
cache row also records the generation_hash it was computed against; annotation's
also records generation_hash + classification_hash; the merged row records all
three. A change to an *upstream* prompt (e.g. generation) reruns generation,
which changes generation_hash, which — even though classification's own prompt
never changed — makes the previously-cached classification row's stored
generation_hash stale, forcing classification (and therefore annotation, and
the merged record) to rerun too. The merged cache is checked last, after all
three stages have already been resolved (from cache or freshly run), so it can
never bypass upstream invalidation the way a single (chunk_id, content_hash)
key would.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from cache import Cache, ENRICHMENT_SCHEMA_VERSION
from config import settings
from identity import passage_id
from model import Document, Passage
from enrichment.backup import Backup
from enrichment.client import SchemaValidationError, Usage
from enrichment.merge import merge
from enrichment.render import build_context, enrichment_content
from enrichment.prompts.annotation import ANNOTATION_SYSTEM
from enrichment.prompts.classification import classification_system
from enrichment.prompts.generation import generation_system
from enrichment.schema import (
    ClassificationOutput, GenerationOutput, IdentifiedFacet, MergedEnrichment, identify_facets,
)
from enrichment.telemetry import EnrichmentTelemetry
from enrichment.validation import (
    ValidationFailedError, annotation_target_tokens, annotation_token_count,
    reorder_labels_by_facet_id, validate_annotation, validate_classification,
    validate_evidence_style, validate_generation,
)

logger = logging.getLogger(__name__)


@dataclass
class EnrichDeps:
    cache: Cache
    gen_client: object                  # EnrichmentClient (Opus) — Pass 1
    classify_client: object             # EnrichmentClient (Sonnet) — Pass 2 & Pass 3
    backup: Backup
    annotation_writer: Callable[[str, str], Awaitable[None]]


@dataclass
class EnrichStats:
    processed: int
    from_cache: int
    usage: Usage
    failed: list[tuple[str, str]] = field(default_factory=list)


def _add_usage(a: Usage, b: Usage) -> Usage:
    return Usage(a.input_tokens + b.input_tokens, a.output_tokens + b.output_tokens)


async def _call_with_retry(call_fn, validate_fn, *, sample: bool, cache: Cache,
                           chunk_id: str, content_hash: str, status_name: str):
    """Runs call_fn(retry_errors) -> (output, usage) once; validates the output
    with validate_fn(output) -> list[str] warnings (raises ValidationFailedError
    on hard failure). On any failure (schema-level or business-rule), retries
    once with the error text appended. If the retry also fails, persists the
    raw response via cache.set_chunk_status(..., status_name) (unless sample)
    and re-raises ValidationFailedError. Never swallows a validation failure.
    """
    total_usage = Usage(0, 0)
    error_text: str | None = None
    for attempt in range(2):
        try:
            output, usage = await call_fn(error_text)
        except SchemaValidationError as exc:
            total_usage = _add_usage(total_usage, exc.usage)
            error_text = str(exc.original)
            if attempt == 1:
                if not sample:
                    cache.set_chunk_status(chunk_id, content_hash, status_name,
                                           raw_response=json.dumps(exc.raw),
                                           validation_errors=error_text)
                raise ValidationFailedError([error_text]) from exc
            continue

        total_usage = _add_usage(total_usage, usage)
        try:
            warnings = validate_fn(output)
        except ValidationFailedError as exc:
            error_text = str(exc)
            if attempt == 1:
                if not sample:
                    cache.set_chunk_status(chunk_id, content_hash, status_name,
                                           raw_response=json.dumps(output.model_dump()),
                                           validation_errors=error_text)
                raise
            continue

        return output, total_usage, warnings

    raise RuntimeError("unreachable")  # pragma: no cover


async def _run_generation(deps: EnrichDeps, chunk_id: str, content_hash: str,
                          gen_system: str, context: str, passage_content: str,
                          *, sample: bool) -> tuple[GenerationOutput, Usage]:
    async def call_fn(retry_errors):
        return await deps.gen_client.generate(
            gen_system, context, settings.PASS1_TEMPERATURE, retry_errors=retry_errors)

    def validate_fn(output) -> list[str]:
        validate_generation(output.facets, passage_content)
        return []

    generation, usage, _warnings = await _call_with_retry(
        call_fn, validate_fn, sample=sample, cache=deps.cache,
        chunk_id=chunk_id, content_hash=content_hash, status_name="generation_failed")
    return generation, usage


async def _run_classification(deps: EnrichDeps, chunk_id: str, content_hash: str,
                              cls_system: str, context: str,
                              facets: list[IdentifiedFacet], content: str,
                              *, sample: bool) -> tuple[ClassificationOutput, Usage]:
    # Downstream of Pass 1, "facet text" means the takeaway — Pass 2 never sees
    # Pass 1's raw working text.
    facets_for_call = [(f.id, f.takeaway, f.question) for f in facets]

    async def call_fn(retry_errors):
        return await deps.classify_client.classify(
            cls_system, context, facets_for_call, settings.PASS2_TEMPERATURE,
            retry_errors=retry_errors)

    def validate_fn(output) -> list[str]:
        validate_classification(facets, output.labels, content)
        return []

    classification, usage, _warnings = await _call_with_retry(
        call_fn, validate_fn, sample=sample, cache=deps.cache,
        chunk_id=chunk_id, content_hash=content_hash, status_name="classification_failed")

    # validate_classification (inside _call_with_retry's validate_fn) already
    # confirmed a 1:1 facet_id correspondence between `facets` and
    # `classification.labels` — realign labels into facet order here so every
    # downstream consumer (annotation assembly, merge) can safely zip by
    # position instead of re-deriving identity itself.
    ordered_labels = reorder_labels_by_facet_id(facets, classification.labels)
    classification = classification.model_copy(update={"labels": ordered_labels})

    for w in validate_evidence_style(classification.labels):
        logger.warning("enrich: chunk %s classification warning: %s", chunk_id, w)

    return classification, usage


async def _run_annotation(deps: EnrichDeps, chunk_id: str, content_hash: str,
                          context: str, facets_with_labels: list[dict[str, Any]],
                          *, sample: bool) -> tuple[str, Usage]:
    async def call_fn(retry_errors):
        return await deps.classify_client.assemble_annotation(
            ANNOTATION_SYSTEM, context, facets_with_labels, settings.PASS3_TEMPERATURE,
            retry_errors=retry_errors)

    def validate_fn(output) -> list[str]:
        return validate_annotation(facets_with_labels, output.annotation)

    annotation_out, usage, warnings = await _call_with_retry(
        call_fn, validate_fn, sample=sample, cache=deps.cache,
        chunk_id=chunk_id, content_hash=content_hash, status_name="annotation_failed")
    for w in warnings:
        logger.warning("enrich: chunk %s annotation warning: %s", chunk_id, w)
    return annotation_out.annotation, usage


async def enrich_one(doc: Document, passage: Passage, deps: EnrichDeps,
                     *, sample: bool,
                     telemetry: EnrichmentTelemetry | None = None,
                     ) -> tuple[MergedEnrichment, Usage]:
    cid = passage_id(doc.id, passage.anchor)
    ch = Cache.content_hash(passage.content)
    gen_system = generation_system(doc.collection)
    gen_prompt_hash = Cache.prompt_hash(gen_system)
    cls_system = classification_system(doc.collection)
    cls_prompt_hash = Cache.prompt_hash(cls_system)
    ann_prompt_hash = Cache.prompt_hash(ANNOTATION_SYSTEM)
    context = build_context(doc, passage)
    total = Usage(0, 0)

    # 1. generation (Pass 1). A cache hit requires the stage's OWN identity —
    # prompt, model, temperature, schema version — to match; it says nothing
    # about downstream stages, which check their own upstream dependency below.
    gen_cached = None if sample else deps.cache.get_generation(cid, ch)
    if (gen_cached is not None
            and gen_cached["prompt_hash"] == gen_prompt_hash
            and gen_cached["model"] == settings.ANTHROPIC_ENRICH_MODEL
            and gen_cached["temperature"] == settings.PASS1_TEMPERATURE
            and gen_cached["schema_version"] == ENRICHMENT_SCHEMA_VERSION):
        generation = GenerationOutput.model_validate({"facets": gen_cached["raw_facets"]})
        # identify_facets() always recomputes ids from position (f1, f2, ...),
        # so this transparently backfills legacy cache rows written before
        # facet ids existed — no separate migration path needed.
        identified = identify_facets(generation.facets)
    else:
        generation, gu = await _run_generation(
            deps, cid, ch, gen_system, context, enrichment_content(passage), sample=sample)
        total = _add_usage(total, gu)
        identified = identify_facets(generation.facets)
        raw_facets = [f.model_dump() for f in identified]
        if not sample:
            deps.backup.write(doc.collection, {
                "chunk_id": cid, "content_hash": ch, "stage": "generation",
                "collection": doc.collection, "reference": passage.reference,
                "raw_facets": raw_facets, "prompt_hash": gen_prompt_hash,
                "model": settings.ANTHROPIC_ENRICH_MODEL})
            deps.cache.put_generation(cid, ch, raw_facets, gen_prompt_hash,
                                      settings.ANTHROPIC_ENRICH_MODEL,
                                      temperature=settings.PASS1_TEMPERATURE,
                                      schema_version=ENRICHMENT_SCHEMA_VERSION)

    # Recomputed fresh every time (cheap — a small JSON list) rather than
    # trusted from a stored column, so it always reflects the facets actually
    # in hand regardless of which branch above produced them.
    generation_hash = Cache.canonical_hash([f.model_dump() for f in identified])

    # 2. classification (Pass 2). A cache hit additionally requires the stored
    # generation_hash to match the current one — if Pass 1 reran (prompt,
    # model, temperature, or schema changed) and produced different facets,
    # generation_hash changes and this cache is correctly treated as stale
    # even though classification's OWN prompt never changed.
    cls_cached = None if sample else deps.cache.get_classification(cid, ch)
    if (cls_cached is not None
            and cls_cached["prompt_hash"] == cls_prompt_hash
            and cls_cached["model"] == settings.ANTHROPIC_CLASSIFY_MODEL
            and cls_cached["temperature"] == settings.PASS2_TEMPERATURE
            and cls_cached["schema_version"] == ENRICHMENT_SCHEMA_VERSION
            and cls_cached["generation_hash"] == generation_hash):
        # Legacy classification cache rows (written before facet ids existed)
        # lack the `facet_id` key entirely. Those rows were written when label
        # order was positionally aligned with facet order (the only alignment
        # the old code used), so backfilling facet_id by position reproduces
        # exactly the alignment that run actually had — a narrow migration
        # path, not a weakening of validation for newly generated records.
        raw_labels = cls_cached["labels"]
        if len(raw_labels) == len(identified):
            raw_labels = [
                {**lab, "facet_id": lab.get("facet_id") or identified[i].id}
                for i, lab in enumerate(raw_labels)
            ]
        classification = ClassificationOutput.model_validate({"labels": raw_labels})
    else:
        classification, cu = await _run_classification(
            deps, cid, ch, cls_system, context, identified,
            enrichment_content(passage), sample=sample)
        total = _add_usage(total, cu)
        labels = [lab.model_dump() for lab in classification.labels]
        if not sample:
            deps.backup.write(doc.collection, {
                "chunk_id": cid, "content_hash": ch, "stage": "classification",
                "collection": doc.collection, "labels": labels, "prompt_hash": cls_prompt_hash,
                "model": settings.ANTHROPIC_CLASSIFY_MODEL})
            deps.cache.put_classification(cid, ch, labels, cls_prompt_hash,
                                          settings.ANTHROPIC_CLASSIFY_MODEL,
                                          temperature=settings.PASS2_TEMPERATURE,
                                          schema_version=ENRICHMENT_SCHEMA_VERSION,
                                          generation_hash=generation_hash)

    classification_hash = Cache.canonical_hash([lab.model_dump() for lab in classification.labels])

    # Batch telemetry (item 4/6): recorded for every chunk regardless of
    # whether classification came from cache or a fresh call, so per-collection
    # secondary-kind and evidence-warning rates reflect the batch's current
    # state rather than only chunks that happened to need reclassification.
    if telemetry is not None:
        telemetry.record_labels(classification.labels, validate_evidence_style(classification.labels))

    # 3. annotation assembly (Pass 3). A cache hit additionally requires the
    # stored generation_hash AND classification_hash to match current values.
    # "text" here is the takeaway — Pass 3 never sees Pass 1's raw working text.
    # `identified` and `classification.labels` are guaranteed aligned by
    # facet_id (validated + reordered in _run_classification, or already in
    # facet order for a cache hit), so zipping positionally here is safe.
    facets_with_labels = [
        {"id": f.id, "text": f.takeaway, "question": f.question, "grounding": lab.grounding,
         "evidence": lab.evidence, "kind": lab.kind, "kind_secondary": lab.kind_secondary}
        for f, lab in zip(identified, classification.labels)
    ]
    ann_cached = None if sample else deps.cache.get_annotation(cid, ch)
    if (ann_cached is not None
            and ann_cached["prompt_hash"] == ann_prompt_hash
            and ann_cached["model"] == settings.ANTHROPIC_CLASSIFY_MODEL
            and ann_cached["temperature"] == settings.PASS3_TEMPERATURE
            and ann_cached["schema_version"] == ENRICHMENT_SCHEMA_VERSION
            and ann_cached["generation_hash"] == generation_hash
            and ann_cached["classification_hash"] == classification_hash):
        annotation_text = ann_cached["annotation"]
    else:
        annotation_text, au = await _run_annotation(
            deps, cid, ch, context, facets_with_labels, sample=sample)
        total = _add_usage(total, au)
        if not sample:
            deps.backup.write(doc.collection, {
                "chunk_id": cid, "content_hash": ch, "stage": "annotation",
                "collection": doc.collection, "annotation": annotation_text,
                "prompt_hash": ann_prompt_hash, "model": settings.ANTHROPIC_CLASSIFY_MODEL})
            deps.cache.put_annotation(cid, ch, annotation_text, ann_prompt_hash,
                                      settings.ANTHROPIC_CLASSIFY_MODEL,
                                      temperature=settings.PASS3_TEMPERATURE,
                                      schema_version=ENRICHMENT_SCHEMA_VERSION,
                                      generation_hash=generation_hash,
                                      classification_hash=classification_hash)

    annotation_hash = Cache.canonical_hash(annotation_text)

    if telemetry is not None:
        telemetry.record_annotation(
            annotation_token_count(annotation_text), annotation_target_tokens(len(identified)))

    # 4. merged-cache lookup — checked LAST, only after all three upstream
    # stages have been resolved (from cache or freshly run), and only reused
    # when every one of its stored dependency hashes matches what we just
    # computed above. This is what stops the merged cache from bypassing
    # stage-level invalidation: it can never be consulted (or trusted) before
    # the three stages it depends on have already proven themselves current.
    if not sample:
        merged_cached = deps.cache.get_enrichment(cid, ch)
        if (merged_cached is not None
                and merged_cached["schema_version"] == ENRICHMENT_SCHEMA_VERSION
                and merged_cached["generation_hash"] == generation_hash
                and merged_cached["classification_hash"] == classification_hash
                and merged_cached["annotation_hash"] == annotation_hash):
            return MergedEnrichment.model_validate(merged_cached), total

    # 5. merge + persist
    merged = merge(identified, classification, annotation_text)
    # merge() always populates working_text (Pass 1's raw treatment) — drop it
    # here unless PILOT_MODE is on, so it's never persisted or embedded downstream
    # by default.
    if not settings.PILOT_MODE:
        for f in merged.facets:
            f.working_text = None
    if not sample:
        deps.cache.put_enrichment(cid, ch, [f.model_dump() for f in merged.facets], merged.annotation,
                                  generation_hash=generation_hash,
                                  classification_hash=classification_hash,
                                  annotation_hash=annotation_hash,
                                  schema_version=ENRICHMENT_SCHEMA_VERSION)
        await deps.annotation_writer(cid, merged.annotation)
    return merged, total


async def enrich_collection(docs: list[Document], collection: str, deps: EnrichDeps,
                            *, sample: bool = False) -> EnrichStats:
    passages = [(d, p) for d in docs for p in d.passages]
    total = Usage(0, 0)
    from_cache = 0
    failed: list[tuple[str, str]] = []
    sem = asyncio.Semaphore(settings.OPUS_CONCURRENCY)
    telemetry = EnrichmentTelemetry(collection=collection)

    async def _run(d, p):
        nonlocal total, from_cache
        async with sem:
            try:
                _, usage = await enrich_one(d, p, deps, sample=sample, telemetry=telemetry)
            except Exception as exc:
                cid = passage_id(d.id, p.anchor)
                logger.warning(
                    "enrich: chunk %s (%s) failed and was skipped: %s",
                    cid, p.reference, exc)
                failed.append((cid, p.reference))
                return
        total = Usage(total.input_tokens + usage.input_tokens,
                      total.output_tokens + usage.output_tokens)
        if usage.input_tokens == 0:
            from_cache += 1

    await asyncio.gather(*[_run(d, p) for d, p in passages])
    telemetry.log_summary()
    if not sample:
        deps.cache.set_collection_status(
            collection, total_chunks=len(passages),
            enriched=len(passages) - len(failed), complete=(len(failed) == 0))
    return EnrichStats(processed=len(passages), from_cache=from_cache, usage=total, failed=failed)
