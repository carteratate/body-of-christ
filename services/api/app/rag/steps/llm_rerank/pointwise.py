"""Pointwise reranking: one call per collection, a score per passage.

This is the historical rerank shape, preserved exactly so it remains a valid A/B
baseline: same prompt, same parsing, same include-decision safety nets. The only
change is that the model call goes through a provider, so Haiku and Luna are
interchangeable here.

Cost note: this shape re-sends the ~723-token system prompt once per collection and
carries full passage content for every candidate, which makes it the most expensive
rerank mode in practice — see steps/llm_rerank/listwise.py for the single-call
alternative.
"""
from __future__ import annotations

import json
import logging
import math
import uuid as _uuid_mod

from app.config import settings
from app.rag.steps import degradation
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank.base import RerankProvider
from app.rag.steps.types import ChunkCandidate, RankedChunk

logger = logging.getLogger(__name__)

_RERANK_SYSTEM = (
    "You are evaluating Catholic theological passages for relevance to a user's "
    "question. For EACH passage, assign a score and an include decision.\n\n"
    "SCORING — use the FULL 0.0-1.0 range. Scores should spread meaningfully:\n"
    "  0.9-1.0: Directly answers the specific question with substance. Reserve "
    "this for passages that explicitly address the exact topic asked.\n"
    "  0.7-0.89: Clearly relevant — addresses the topic from a useful angle even "
    "if not the exact question. Should be shown.\n"
    "  0.4-0.69: Tangentially related — shares theme but doesn't directly help. "
    "Include only if better passages are scarce.\n"
    "  0.0-0.39: Off-topic. Shares vocabulary or broad theme but does not address "
    "the question.\n\n"
    "SOURCE DIVERSITY: The reference label shows which book or document each passage "
    "is from. When multiple passages from the same source (same biblical book, same "
    "encyclical, same author and work) are present, nudge lower-scoring duplicates "
    "down by 0.15-0.25 to prefer sourcing from different books. Do not apply this "
    "nudge to a passage that earns 0.9+ on its own merits — a genuinely excellent "
    "passage should not be penalized for its source. Within the same book or "
    "category, reward passages that approach the topic from a genuinely different "
    "angle, make a distinct argument, or offer a different kind of answer (lament vs. "
    "resolution, question vs. declaration, narrative vs. doctrine) — these earn a "
    "reduced or no penalty even when they share a source.\n\n"
    "INTENT: Consider why the user is asking. A devotional or personal question "
    "(\"How do I...\") should rank passages that are pastoral and practical higher. "
    "A doctrinal question (\"What does the Church teach about...\") should rank "
    "passages that define or explain Church teaching higher. A historical question "
    "should rank primary sources and council documents higher.\n\n"
    "INCLUDE RULES:\n"
    "  Set include=false if score < 0.35.\n"
    "  Set include=false if this passage makes the same argument as a higher-scoring "
    "passage already in the list (set overlap_verdict=\"redundant\"). Two passages "
    "from the same book repeating the same point are redundant.\n"
    "  Set include=true for passages that address the same theme from different "
    "sources, genres, or traditions — a lament, a theological epistle, and a "
    "catechism paragraph on the same topic are three perspectives on one question, "
    "not redundancy (overlap_verdict=\"complementary\"). Reward this kind of "
    "cross-source coverage.\n\n"
    "Respond with ONLY a JSON array containing ALL input chunk_ids. No text before "
    "or after the array:\n"
    '[{"chunk_id":"<id>","score":<float>,"include":<bool>,'
    '"overlap_verdict":<"redundant"|"complementary"|null>}]'
)


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
        lines.append(f"[{c.chunk_id}] {ref}: {c.content}")
    return "\n".join(lines)


def _extract_json_array(text: str) -> list[dict]:
    """Decode the first complete JSON array without greedily consuming later text."""
    start = text.find("[")
    if start < 0:
        raise ValueError("No JSON array found in response")
    value, end = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(value, list):
        raise ValueError("First JSON value is not an array")
    trailing = text[end:].strip()
    if trailing not in ("", "```"):
        raise ValueError("Unexpected trailing output after JSON array")
    return value


def fallback_ranked(candidates: list[ChunkCandidate], quota: int) -> list[RankedChunk]:
    """RRF order with synthetic scores, for a collection the LLM failed to score.

    These are NOT relevance measurements — nothing scored these candidates. They sit
    in a modest band starting at `llm_fallback_score_base` (0.40): above the include
    floors so the collection is still represented, but below what a genuinely strong
    LLM match earns, so an UNSCORED collection cannot outrank scored ones.

    This previously started at 1.00 and descended by 0.01, with `include` left at its
    default of True. Because `rerank.run` merges all collections and sorts globally,
    one failed collection's unscored RRF candidates sorted ABOVE every genuinely
    scored chunk in every other collection — and those 1.00 scores reached the UI as
    "100% relevance" and were persisted to `retrievals.reranker_score`. The Cohere
    path had the identical bug fixed earlier; this is its twin on the production
    (`llm_only`) path.
    """
    results = []
    base = settings.llm_fallback_score_base
    for i, c in enumerate(candidates[:quota]):
        score = max(0.0, base - i * 0.01)
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
                include=score >= settings.pointwise_score_cutoff,
                anchor=c.anchor,
                chapter_key=c.chapter_key,
                position=c.position,
                annotation=c.annotation,
                score_source="rrf_fallback",
            )
        )
    return results


async def rerank_collection(
    candidates: list[ChunkCandidate],
    query: str,
    quota: int,
    cost_tracker: CostTracker,
    provider: RerankProvider,
    step: str = "rerank_llm",
    *,
    _repair_attempt: int = 0,
    _repair_note: str | None = None,
    _expected_ids: set[str] | None = None,
    _base_ranked: list[RankedChunk] | None = None,
) -> list[RankedChunk]:
    """Score and filter one collection's candidates with the given provider.

    Returns all scored chunks with include/exclude decisions; the pipeline applies
    the hard cutoff. Falls back to RRF order (capped at quota) on failure. Never
    raises.
    """
    if not candidates or not provider.is_ready():
        logger.warning(
            "%s: provider not ready or no candidates; falling back to RRF order", step,
        )
        degradation.record(step, "provider_not_ready", "rrf_fallback_used")
        return fallback_ranked(candidates, quota)

    candidate_map: dict[str, ChunkCandidate] = {c.chunk_id: c for c in candidates}
    response_expected = set(_expected_ids or candidate_map)
    user_message = f"Query: {query}\n\nPassages:\n{_format_passages(candidates)}"
    if _repair_note:
        user_message = (
            "REPAIR REQUEST: Score ONLY the expected IDs listed below, exactly once. "
            "The full passage set remains below for comparison context. Do not repeat "
            "IDs that are not requested.\n"
            f"{_repair_note}\nExpected IDs:\n"
            + "\n".join(sorted(response_expected))
            + "\n\n"
            + user_message
        )
    logger.info(
        "%s: sending %d candidates, user_message_len=%d chars",
        step, len(candidates), len(user_message),
    )

    try:
        result = await provider.score(_RERANK_SYSTEM, user_message, 4096)
        cost_tracker.record(
            step, provider.model_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        raw_text = result.text
        scored = _extract_json_array(raw_text)
    except Exception as exc:
        if _repair_attempt == 0:
            logger.warning("%s: call/parse failed (%s) — retrying once", step, exc)
            degradation.record_recovery(
                step,
                "call_or_parse_failed",
                "targeted_retry",
                scope=candidates[0].collection if candidates else None,
                details={"message": str(exc)[:300], "expected": len(response_expected)},
            )
            return await rerank_collection(
                candidates, query, quota, cost_tracker, provider, step,
                _repair_attempt=1, _repair_note=f"Parse/call error: {exc}",
                _expected_ids=response_expected,
            )
        logger.warning("%s: scoring failed: %s", step, exc)
        logger.debug("%s: raw response was: %.500s", step, locals().get("raw_text", "<none>"))
        degradation.record(
            step, "call_or_parse_failed", "rrf_fallback_used",
            details={"message": str(exc)[:300]},
        )
        return fallback_ranked(candidates, quota)

    ranked: list[RankedChunk] = []
    seen_scores: dict[str, tuple[float, bool, str | None]] = {}
    warnings = 0
    conflicts = 0
    conflict_ids: set[str] = set()
    for item in scored:
        chunk_id = str(item.get("chunk_id", ""))
        if (
            not _is_valid_uuid(chunk_id)
            or chunk_id not in candidate_map
            or chunk_id not in response_expected
        ):
            warnings += 1
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            logger.warning(
                "%s: non-numeric score %r for chunk_id '%s'",
                step, item.get("score"), chunk_id,
            )
            conflicts += 1
            if chunk_id in response_expected:
                conflict_ids.add(chunk_id)
            continue
        if not math.isfinite(score):
            logger.warning("%s: non-finite score for chunk_id '%s'", step, chunk_id)
            conflicts += 1
            conflict_ids.add(chunk_id)
            continue
        candidate = candidate_map.get(chunk_id)

        include = bool(item.get("include", True))
        overlap_verdict = item.get("overlap_verdict") or None
        # Safety nets: hard-exclude low-scoring chunks and explicit redundancy
        if score < settings.pointwise_score_cutoff:
            include = False
        if overlap_verdict == "redundant":
            include = False
        normalized = max(0.0, min(1.0, score))
        signature = (normalized, include, overlap_verdict)
        if chunk_id in seen_scores:
            if seen_scores[chunk_id] == signature:
                warnings += 1
            else:
                conflicts += 1
                conflict_ids.add(chunk_id)
            continue
        seen_scores[chunk_id] = signature

        ranked.append(
            RankedChunk(
                chunk_id=candidate.chunk_id,
                content=candidate.content,
                reference=candidate.reference,
                collection=candidate.collection,
                document_id=candidate.document_id,
                document_title=candidate.document_title,
                author=candidate.author,
                reranker_score=normalized,
                include=include,
                anchor=candidate.anchor,
                chapter_key=candidate.chapter_key,
                position=candidate.position,
                annotation=candidate.annotation,
                score_source=provider.name,
            )
        )

    if conflict_ids:
        ranked = [r for r in ranked if r.chunk_id not in conflict_ids]
    returned_ids = {r.chunk_id for r in ranked}
    expected_ids = response_expected
    missing = sorted(expected_ids - returned_ids)
    if warnings:
        logger.warning("%s: ignored %d harmless extra/identical entries", step, warnings)
    if conflicts or missing:
        if _repair_attempt == 0:
            logger.warning(
                "%s: ambiguous/incomplete output (matched=%d expected=%d conflicts=%d) — retrying once",
                step, len(returned_ids), len(expected_ids), conflicts,
            )
            degradation.record_recovery(
                step,
                "incomplete_output",
                "targeted_retry",
                scope=candidates[0].collection if candidates else None,
                details={
                    "matched": len(returned_ids),
                    "expected": len(expected_ids),
                    "conflicting_entries": conflicts,
                    "missing_count": len(missing),
                },
            )
            return await rerank_collection(
                candidates, query, quota, cost_tracker, provider, step,
                _repair_attempt=1,
                _repair_note=(
                    f"Missing expected IDs: {missing}. "
                    f"Conflicting/invalid expected entries: {conflicts}."
                ),
                _expected_ids=set(missing) | conflict_ids,
                _base_ranked=[*(_base_ranked or []), *ranked],
            )
        logger.warning(
            "%s: incomplete output (matched=%d expected=%d conflicts=%d) — using RRF fallback",
            step, len(returned_ids), len(expected_ids), conflicts,
        )
        degradation.record(
            step, "incomplete_output", "rrf_fallback_used",
            scope=candidates[0].collection if candidates else None,
            details={
                "matched": len(returned_ids),
                "expected": len(expected_ids),
                "conflicting_entries": conflicts,
                "missing_ids": missing,
            },
        )
        return fallback_ranked(candidates, quota)

    ranked = [*(_base_ranked or []), *ranked]
    if {r.chunk_id for r in ranked} != set(candidate_map):
        degradation.record(
            step, "incomplete_repair_merge", "rrf_fallback_used",
            scope=candidates[0].collection if candidates else None,
        )
        return fallback_ranked(candidates, quota)
    ranked.sort(key=lambda r: r.reranker_score, reverse=True)

    col_name = candidates[0].collection if candidates else "?"
    included_n = sum(1 for r in ranked if r.include)
    logger.info(
        "%s scores: collection=%s candidates=%d matched=%d included=%d excluded=%d "
        "max_score=%.2f top=%s",
        step, col_name, len(candidates), len(returned_ids), included_n,
        len(ranked) - included_n,
        ranked[0].reranker_score if ranked else 0.0,
        [(round(r.reranker_score, 2), r.include) for r in ranked[:15]],
    )
    return ranked
