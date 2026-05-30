"""Per-collection re-ranking of candidate chunks using Claude Haiku."""
import json
import logging
import re
import uuid as _uuid_mod
from dataclasses import dataclass

import anthropic

from app.config import settings
from app.rag.retrieve import ChunkCandidate

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

_RERANK_SYSTEM = (
    'You are a Catholic theology relevance ranker. Given a user query and a list of passages, '
    'score each passage for how directly and helpfully it addresses the query. '
    'Return ONLY a JSON array: [{"chunk_id": "<id>", "score": <0.0-1.0>}, ...]. '
    'Scores must be floats between 0.0 and 1.0. '
    'Include every chunk_id from the input. '
    'Prefer passages from different sections when scores are close.'
)


@dataclass
class RankedChunk:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    reranker_score: float  # 0.0–1.0


def init_rerank() -> None:
    global _client
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def close_rerank() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def _is_valid_uuid(val: str) -> bool:
    try:
        _uuid_mod.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False


def _format_passages(candidates: list[ChunkCandidate]) -> str:
    lines = []
    for c in candidates:
        ref = c.reference or "No reference"
        snippet = c.content[:300]
        lines.append(f"[{c.chunk_id}] {ref}: {snippet}")
    return "\n".join(lines)


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from the response text, stripping markdown fences."""
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in response")
    return json.loads(match.group(0))


async def rerank_collection(
    candidates: list[ChunkCandidate],
    query: str,
    quota: int,
) -> list[RankedChunk]:
    """Re-rank candidate chunks using Claude Haiku and return the top `quota` results.

    On failure: falls back to original RRF order with decreasing scores. Never raises.
    """
    if not candidates:
        return []

    # Build a lookup from chunk_id → ChunkCandidate for mapping results back
    candidate_map: dict[str, ChunkCandidate] = {c.chunk_id: c for c in candidates}

    if _client is None:
        logger.warning("rerank client not initialized; falling back to RRF order")
        return _fallback_ranked(candidates, quota)

    formatted_passages = _format_passages(candidates)
    user_message = f"Query: {query}\n\nPassages:\n{formatted_passages}"

    try:
        response = await _client.messages.create(
            model=settings.rerank_model,
            max_tokens=500,
            system=_RERANK_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text
        scored = _extract_json_array(raw_text)
    except Exception as exc:
        logger.warning("rerank_collection: Haiku scoring failed: %s", exc)
        return _fallback_ranked(candidates, quota)

    # Build RankedChunk objects from the scored list
    ranked: list[RankedChunk] = []
    for item in scored:
        chunk_id = str(item.get("chunk_id", ""))
        if not _is_valid_uuid(chunk_id):
            logger.warning("rerank_collection: invalid UUID '%s' in Haiku response", chunk_id)
            continue
        score = float(item.get("score", 0.0))
        candidate = candidate_map.get(chunk_id)
        if candidate is None:
            logger.warning("rerank_collection: unknown chunk_id '%s' in Haiku response", chunk_id)
            continue
        ranked.append(
            RankedChunk(
                chunk_id=candidate.chunk_id,
                content=candidate.content,
                reference=candidate.reference,
                collection=candidate.collection,
                document_id=candidate.document_id,
                document_title=candidate.document_title,
                author=candidate.author,
                reranker_score=max(0.0, min(1.0, score)),
            )
        )

    # Add any candidates that Haiku omitted (score 0.0)
    returned_ids = {r.chunk_id for r in ranked}
    for c in candidates:
        if c.chunk_id not in returned_ids:
            ranked.append(
                RankedChunk(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    reference=c.reference,
                    collection=c.collection,
                    document_id=c.document_id,
                    document_title=c.document_title,
                    author=c.author,
                    reranker_score=0.0,
                )
            )

    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return ranked[:quota]


def _fallback_ranked(candidates: list[ChunkCandidate], quota: int) -> list[RankedChunk]:
    """Return candidates in RRF order with decreasing scores as a fallback."""
    results = []
    for i, c in enumerate(candidates[:quota]):
        score = max(0.0, 1.0 - i * 0.01)
        results.append(
            RankedChunk(
                chunk_id=c.chunk_id,
                content=c.content,
                reference=c.reference,
                collection=c.collection,
                document_id=c.document_id,
                document_title=c.document_title,
                author=c.author,
                reranker_score=score,
            )
        )
    return results
