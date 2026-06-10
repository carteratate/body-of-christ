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
    "You are evaluating Catholic theological passages for a user's question. "
    "For EACH passage, assign a relevance score and decide whether to include it.\n\n"
    "Score bands:\n"
    "  0.9-1.0: Directly addresses the specific topic with substance.\n"
    "  0.6-0.89: Clearly relevant, provides useful context.\n"
    "  0.3-0.59: Tangentially related.\n"
    "  0.0-0.29: Off-topic or shares only vocabulary with the question.\n\n"
    "Include rules:\n"
    "  Set include=false if score < 0.25.\n"
    "  Set include=false if this passage makes the same argument as a higher-scoring passage "
    "(set overlap_with to that passage's chunk_id, overlap_verdict='redundant').\n"
    "  Keep include=true for passages on the same theme from genuinely different angles "
    "(e.g., scripture vs. catechism vs. theology) — set overlap_verdict='complementary'.\n\n"
    "Return ONLY a JSON array containing ALL input chunk_ids:\n"
    '[{"chunk_id":"<id>","score":<float>,"include":<bool>,'
    '"overlap_with":<"id" or null>,"overlap_verdict":<"redundant"|"complementary"|null>}]'
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
    include: bool = True   # False = hard-excluded by reranker (low score or redundant)


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
        snippet = c.content
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
    """Score and filter candidate chunks using Claude Haiku.

    Returns all scored chunks with include/exclude decisions; the pipeline
    applies the hard cutoff. Falls back to RRF order (capped at quota) on
    failure. Never raises.
    """
    if not candidates:
        return []

    candidate_map: dict[str, ChunkCandidate] = {c.chunk_id: c for c in candidates}

    if _client is None:
        logger.warning("rerank client not initialized; falling back to RRF order")
        return _fallback_ranked(candidates, quota)

    formatted_passages = _format_passages(candidates)
    user_message = f"Query: {query}\n\nPassages:\n{formatted_passages}"

    try:
        response = await _client.messages.create(
            model=settings.rerank_model,
            max_tokens=1500,
            system=_RERANK_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text
        scored = _extract_json_array(raw_text)
    except Exception as exc:
        logger.warning("rerank_collection: Haiku scoring failed: %s", exc)
        return _fallback_ranked(candidates, quota)

    ranked: list[RankedChunk] = []
    for item in scored:
        chunk_id = str(item.get("chunk_id", ""))
        if not _is_valid_uuid(chunk_id):
            logger.warning("rerank_collection: invalid UUID '%s' in Haiku response", chunk_id)
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            logger.warning(
                "rerank_collection: non-numeric score %r for chunk_id '%s'; defaulting to 0.0",
                item.get("score"),
                chunk_id,
            )
            score = 0.0
        candidate = candidate_map.get(chunk_id)
        if candidate is None:
            logger.warning("rerank_collection: unknown chunk_id '%s' in Haiku response", chunk_id)
            continue

        include = bool(item.get("include", True))
        overlap_verdict = item.get("overlap_verdict") or None
        # Safety nets: hard-exclude low-scoring chunks and explicit redundancy
        if score < 0.25:
            include = False
        if overlap_verdict == "redundant":
            include = False

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
                include=include,
            )
        )

    # Chunks omitted by Haiku get score 0.0, include=False
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
                    include=False,
                )
            )

    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return ranked  # All chunks returned; pipeline applies the hard cutoff


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
