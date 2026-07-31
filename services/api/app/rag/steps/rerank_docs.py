"""Builds the text each reranker sees for a candidate.

Two shapes, one per reranker, and each has an enriched and a plain branch selected
per candidate by whether `candidate.annotation` is populated. Enrichment is rolled
out one collection at a time, so a single query routinely spans enriched and
unenriched collections — there is deliberately no global "is enrichment on" flag.

The annotation is used RAW, labels and all. `datapipeline`'s `annotation_prose()`
strips the `[KIND | grounding]:` segment labels and the `SUMMARY:` marker, which is
right for tsvector indexing and wrong here: those labels tell the reranker that a
passage is, say, an `inferential`/`typological` reading rather than an explicit
statement, which is exactly the signal a cross-encoder cannot infer from raw
narrative. Do not reach for `annotation_prose()` in this module.
"""
from __future__ import annotations

from app.rag.steps.types import ChunkCandidate


def cohere_document(candidate: ChunkCandidate) -> str:
    """Document text for one Cohere rerank candidate.

    Ordering is deliberate: reference, then annotation, then content. Cohere
    truncates at `max_tokens_per_doc` from the end, so a long passage loses the tail
    of its content rather than the annotation that was added to carry the
    theological payload.
    """
    ref = candidate.reference or candidate.collection
    if candidate.annotation:
        return f"[{ref}] {candidate.annotation}\n{candidate.content}"
    return f"[{ref}] {candidate.content}"


def llm_card(candidate: ChunkCandidate, max_content_chars: int | None = None) -> str:
    """Compact card for one listwise-rerank candidate.

    Includes the annotation (its SUMMARY line and labeled segments) when present.
    Note this is NOT "the matched facet" — identifying which facet matched a query
    requires retrieving through the facets collection, which does not exist yet, so
    all facets arrive together via the annotation's segments.

    Content is truncated because the listwise call carries every candidate in one
    prompt; the annotation and reference are never truncated.
    """
    ref = candidate.reference or "no reference"
    content = candidate.content
    if max_content_chars is not None and len(content) > max_content_chars:
        content = content[:max_content_chars].rstrip() + "..."

    lines = [f"[{candidate.chunk_id}] ({candidate.collection}) {ref}"]
    if candidate.annotation:
        lines.append(candidate.annotation)
    lines.append(content)
    return "\n".join(lines)
