"""Listwise reranking: every candidate from every collection in ONE call.

Two reasons this exists alongside pointwise:

Quality — the redundancy and source-diversity instructions in the prompt ask the
model to compare passages against each other. Pointwise scores each collection in
its own call, so those comparisons cannot see across collections: a Catechism
paragraph and a Summa article making the identical point both survive. A single call
sees the whole set.

Cost — one call sends the system prompt once and carries compressed cards instead of
full passages, which measures roughly half the pointwise cost for the same query.

Output is `[{"chunk_id", "score"}]` only. `include` is derived locally from the score
rather than asked for, and there is no `overlap_verdict` field: at 40 candidates the
four-field pointwise shape costs ~1,800 more output tokens for information the
pipeline can compute itself.
"""
from __future__ import annotations

import json
import logging
import math
import random
import uuid as _uuid_mod

from app.config import settings
from app.rag.steps import degradation
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank.base import RerankProvider
from app.rag.steps.rerank_docs import llm_card
from app.rag.steps.types import RankedChunk

logger = logging.getLogger(__name__)

# Cards are truncated so the whole pool fits one prompt; annotation and reference
# are never truncated (see rerank_docs.llm_card).
_CARD_CONTENT_CHARS = 600

_LISTWISE_SYSTEM = (
    "You are ranking Catholic theological passages for relevance to a user's "
    "question. You see ALL candidate passages at once, drawn from several "
    "collections, and must rank them against each other.\n\n"
    "Each passage is presented as:\n"
    "[chunk_id] (collection) reference\n"
    "<annotation, when available: a SUMMARY line plus [KIND | grounding] segments>\n"
    "<passage text>\n\n"
    "When an annotation is present, use it. The [KIND | grounding] labels tell you "
    "what kind of claim a passage supports and how directly the passage's own words "
    "support it — 'explicit' means the passage states it outright, 'settled' means "
    "one evident step away, 'inferential' means it requires a further connection. A "
    "narrative passage whose annotation names the doctrinal insight a searcher is "
    "asking about is relevant even when the narrative's surface wording does not "
    "mention the topic.\n\n"
    "SCORING — use the FULL 0.0-1.0 range; scores should spread meaningfully:\n"
    "  0.9-1.0: Directly answers the specific question with substance.\n"
    "  0.7-0.89: Clearly relevant — a useful angle on the topic.\n"
    "  0.4-0.69: Tangentially related — shares theme but does not directly help.\n"
    "  0.0-0.39: Off-topic.\n\n"
    "SOURCE DIVERSITY: because you see every collection at once, penalise genuine "
    "redundancy across the whole set, not just within one source. Two passages "
    "making the same argument should not both score highly — drop the weaker by "
    "0.15-0.25. Do NOT penalise a passage that earns 0.9+ on its own merits, and do "
    "not penalise passages that approach one question from genuinely different "
    "angles (a lament, a doctrinal definition, and a canon are three perspectives, "
    "not redundancy).\n\n"
    "INTENT: consider why the user is asking. A devotional question ranks pastoral "
    "passages higher; a doctrinal question ranks definitional passages higher; a "
    "historical question ranks primary sources and councils higher.\n\n"
    "OUTPUT — score EVERY passage you were given, including ones you judge "
    "irrelevant. Do NOT filter: a low score is how you exclude a passage, and the "
    "pipeline applies the cutoff itself. Omitting a passage is treated as scoring it "
    "0.0, which is not the same as ranking it last.\n\n"
    "Respond with ONLY a JSON array, ranked best-first, with exactly one entry per "
    "passage given above. Copy each chunk_id exactly. No text before or after the "
    "array:\n"
    '[{"chunk_id":"<id>","score":<float>}]'
)


def _is_valid_uuid(val: str) -> bool:
    try:
        _uuid_mod.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False


def _extract_json_array(text: str) -> tuple[list[dict], bool]:
    """Decode the first complete JSON array without greedily consuming later text.

    Returns ``(items, contract_violation)``. Whitespace and a closing markdown fence
    are tolerated after the array. Other trailing output is recoverable only when the
    array itself later passes the exact-coverage validation.
    """
    start = text.find("[")
    if start < 0:
        raise ValueError("No JSON array found in response")
    value, end = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(value, list):
        raise ValueError("First JSON value is not an array")
    trailing = text[end:].strip()
    if trailing in ("", "```"):
        return value, False
    return value, True


def _as_ranked(
    candidate: RankedChunk, score: float, include: bool, score_source: str,
) -> RankedChunk:
    return RankedChunk(
        chunk_id=candidate.chunk_id,
        content=candidate.content,
        reference=candidate.reference,
        collection=candidate.collection,
        document_id=candidate.document_id,
        document_title=candidate.document_title,
        author=candidate.author,
        reranker_score=max(0.0, min(1.0, score)),
        include=include,
        anchor=candidate.anchor,
        position=candidate.position,
        annotation=candidate.annotation,
        score_source=score_source,
    )


def _build_prompt(pool: list[RankedChunk]) -> str:
    cards = [llm_card(c, _CARD_CONTENT_CHARS) for c in pool]
    return "\n\n".join(cards)


async def rerank_pool(
    pool: list[RankedChunk],
    query: str,
    cost_tracker: CostTracker,
    provider: RerankProvider,
    step: str = "rerank_listwise",
    *,
    _repair_attempt: int = 0,
    _repair_note: str | None = None,
    _shuffled: list[RankedChunk] | None = None,
    _expected_ids: set[str] | None = None,
    _base_scores: dict[str, float] | None = None,
) -> list[RankedChunk]:
    """Rank the whole pool in one call.

    `pool` arrives already scored by an upstream reranker (Cohere), so the fallback
    on any failure is simply that upstream order — never an empty result.

    Luna is intentionally single-attempt. Its upstream Cohere order is already a
    complete, useful ranking, so a second long model call is a poor production
    latency tradeoff. Other providers retain one targeted repair attempt.
    """
    if not pool or not provider.is_ready():
        logger.warning("%s: provider not ready or empty pool; keeping upstream order", step)
        if pool:
            degradation.record(step, "provider_not_ready", "upstream_order_used")
        return pool

    # Randomise order per query: a listwise model weights earlier items more, so a
    # fixed collection order would give whichever collection sorts first a permanent
    # advantage across every query.
    shuffled = list(_shuffled) if _shuffled is not None else list(pool)
    if _shuffled is None:
        random.shuffle(shuffled)

    candidate_map = {c.chunk_id: c for c in shuffled}
    response_expected = set(_expected_ids or candidate_map)
    allow_repair = provider.name != "luna"
    user_message = f"Query: {query}\n\nPassages:\n{_build_prompt(shuffled)}"
    if _repair_note:
        user_message = (
            "REPAIR REQUEST: Score ONLY the expected IDs listed below, exactly once "
            "each. The full passage set remains below so scores retain their original "
            "global context. Do not repeat IDs that are not requested.\n"
            f"{_repair_note}\nExpected IDs:\n"
            + "\n".join(sorted(response_expected))
            + "\n\n"
            + user_message
        )
    logger.info(
        "%s: pool=%d collections=%d user_message_len=%d chars",
        step, len(shuffled), len({c.collection for c in shuffled}), len(user_message),
    )

    try:
        result = await provider.score(
            _LISTWISE_SYSTEM, user_message, settings.llm_rerank_max_tokens,
        )
        cost_tracker.record(
            step, provider.model_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        scored, contract_violation = _extract_json_array(result.text)
    except Exception as exc:
        if _repair_attempt == 0 and allow_repair:
            logger.warning("%s: call/parse failed (%s) — retrying once", step, exc)
            degradation.record_recovery(
                step,
                "call_or_parse_failed",
                "targeted_retry",
                details={"message": str(exc)[:300], "expected": len(response_expected)},
            )
            return await rerank_pool(
                pool, query, cost_tracker, provider, step,
                _repair_attempt=1, _repair_note=f"Parse/call error: {exc}",
                _shuffled=shuffled, _expected_ids=set(candidate_map),
            )
        logger.warning(
            "%s: scoring failed (%s) — keeping upstream rerank order for %d candidates",
            step, exc, len(pool),
        )
        degradation.record(
            step, "call_or_parse_failed", "upstream_order_used",
            details={"message": str(exc)[:300]},
        )
        return pool

    parsed_scores: dict[str, float] = {}
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
            conflicts += 1
            if chunk_id in response_expected:
                conflict_ids.add(chunk_id)
            continue
        if not math.isfinite(score):
            conflicts += 1
            conflict_ids.add(chunk_id)
            continue
        normalized = max(0.0, min(1.0, score))
        if chunk_id in parsed_scores:
            if parsed_scores[chunk_id] == normalized:
                warnings += 1
            else:
                conflicts += 1
                conflict_ids.add(chunk_id)
            continue
        parsed_scores[chunk_id] = normalized

    for chunk_id in conflict_ids:
        parsed_scores.pop(chunk_id, None)

    if warnings or conflicts:
        logger.warning(
            "%s: output extras=%d conflicts=%d out of %d returned",
            step, warnings, conflicts, len(scored),
        )

    if not parsed_scores:
        if _repair_attempt == 0 and allow_repair:
            logger.warning("%s: no valid entries — retrying once", step)
            degradation.record_recovery(
                step,
                "no_valid_entries",
                "targeted_retry",
                details={"expected": len(response_expected), "returned": len(scored)},
            )
            return await rerank_pool(
                pool, query, cost_tracker, provider, step,
                _repair_attempt=1,
                _repair_note="No valid expected candidate entries were returned.",
                _shuffled=shuffled,
                _expected_ids=response_expected,
                _base_scores=_base_scores,
            )
        logger.warning(
            "%s: no valid entries parsed from %d returned — keeping upstream order",
            step, len(scored),
        )
        degradation.record(step, "no_valid_entries", "upstream_order_used")
        return pool

    missing = sorted(response_expected - set(parsed_scores))
    coverage = len(parsed_scores) / len(response_expected) if response_expected else 1.0
    if conflicts or missing:
        if _repair_attempt == 0 and allow_repair:
            logger.warning(
                "%s: ambiguous/incomplete output (coverage=%.0f%% conflicts=%d) — retrying once",
                step, coverage * 100, conflicts,
            )
            degradation.record_recovery(
                step,
                "incomplete_output",
                "targeted_retry",
                details={
                    "coverage": coverage,
                    "conflicting_entries": conflicts,
                    "expected": len(response_expected),
                    "matched": len(parsed_scores),
                    "missing_count": len(missing),
                },
            )
            return await rerank_pool(
                pool, query, cost_tracker, provider, step,
                _repair_attempt=1,
                _repair_note=(
                    f"Missing expected IDs: {missing}. "
                    f"Conflicting/invalid expected entries: {conflicts}."
                ),
                _shuffled=shuffled,
                _expected_ids=set(missing) | conflict_ids,
                _base_scores={
                    **(_base_scores or {}),
                    **parsed_scores,
                },
            )
        logger.warning(
            "%s: LOW COVERAGE / incomplete output (coverage=%.0f%% conflicts=%d) — keeping complete "
            "upstream order instead of mixing LLM scores with synthetic zeros",
            step, coverage * 100, conflicts,
        )
        degradation.record(
            step, "incomplete_output", "upstream_order_used",
            details={
                "coverage": coverage,
                "conflicting_entries": conflicts,
                "expected": len(response_expected),
                "matched": len(parsed_scores),
                "missing_ids": missing,
            },
        )
        return pool

    if contract_violation:
        logger.warning("%s: valid complete JSON array had trailing output", step)
        degradation.record_recovery(
            step,
            "trailing_output",
            "accepted_complete_payload",
            details={"expected": len(response_expected)},
        )

    combined_scores = {**(_base_scores or {}), **parsed_scores}
    if set(combined_scores) != set(candidate_map):
        degradation.record(
            step, "incomplete_repair_merge", "upstream_order_used",
            details={"matched": len(combined_scores), "expected": len(candidate_map)},
        )
        return pool

    ranked = [
        _as_ranked(
            candidate_map[chunk_id],
            combined_scores[chunk_id],
            combined_scores[chunk_id] >= settings.listwise_include_floor,
            provider.name,
        )
        for chunk_id in combined_scores
    ]
    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    included_n = sum(1 for r in ranked if r.include)
    logger.info(
        "%s: pool=%d matched=%d (%.0f%% coverage) included=%d excluded=%d max_score=%.2f",
        step, len(shuffled), len(combined_scores),
        len(combined_scores) / len(shuffled) * 100, included_n,
        len(ranked) - included_n, ranked[0].reranker_score if ranked else 0.0,
    )
    return ranked
