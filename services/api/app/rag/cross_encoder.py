"""BGE cross-encoder — zero-cost replacement for Sonnet reranking.

Loaded once at startup via init_cross_encoder(). score_candidates() is
synchronous (CPU-bound); callers must run it in a thread executor to avoid
blocking the event loop:

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, score_candidates, candidates, query)
"""
from __future__ import annotations

import logging
import math

from sentence_transformers import CrossEncoder

from app.rag.steps.types import ChunkCandidate
from app.rag.rerank import RankedChunk

logger = logging.getLogger(__name__)

_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
_model: CrossEncoder | None = None


def init_cross_encoder() -> None:
    global _model
    _model = CrossEncoder(_MODEL_NAME)
    logger.info("Cross-encoder loaded: %s", _MODEL_NAME)


def close_cross_encoder() -> None:
    global _model
    _model = None


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def score_candidates(
    candidates: list[ChunkCandidate],
    query: str,
) -> list[RankedChunk]:
    """Score candidates with BGE cross-encoder. SYNCHRONOUS — run in executor.

    Input text for scoring = annotation text + '\\n\\n' + content when annotation
    is populated; falls back to content alone until enrichment runs.
    Scores are sigmoid-normalized to [0, 1]. Falls back to RRF order on failure.
    Returns all candidates sorted descending by reranker_score.
    """
    if not candidates:
        return []
    if _model is None:
        logger.warning("cross_encoder not initialized; returning RRF order fallback")
        return _fallback_ranked(candidates)

    pairs = []
    for c in candidates:
        annotation_text = ""
        if c.annotation and isinstance(c.annotation, dict):
            annotation_text = c.annotation.get("annotation", "")
            if annotation_text:
                annotation_text += "\n\n"
        pairs.append((query, annotation_text + c.content))

    try:
        raw_scores = _model.predict(pairs)
    except Exception as exc:
        logger.warning("cross_encoder.predict failed: %s", exc)
        return _fallback_ranked(candidates)

    ranked = [
        RankedChunk(
            chunk_id=c.chunk_id,
            content=c.content,
            reference=c.reference,
            collection=c.collection,
            document_id=c.document_id,
            document_title=c.document_title,
            author=c.author,
            reranker_score=_sigmoid(float(score)),
            include=True,
            anchor=c.anchor,
            position=c.position,
        )
        for c, score in zip(candidates, raw_scores)
    ]
    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return ranked


def _fallback_ranked(candidates: list[ChunkCandidate]) -> list[RankedChunk]:
    return [
        RankedChunk(
            chunk_id=c.chunk_id,
            content=c.content,
            reference=c.reference,
            collection=c.collection,
            document_id=c.document_id,
            document_title=c.document_title,
            author=c.author,
            reranker_score=max(0.0, 1.0 - i * 0.01),
            include=True,
            anchor=c.anchor,
            position=c.position,
        )
        for i, c in enumerate(candidates)
    ]
