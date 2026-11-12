"""Corpus cleanup 2.4d: what each model reads for a rejected passage, and that nothing
else changes.

No live passage has `voice` until the Phase 4 apply, so a request without a rejected
passage must produce exactly the text it produced before this item: the Cohere document,
the listwise card and system prompt, the explanation's messages and the judge's prompt.
The system prompts are pinned by their SHA-256 on master before 2.4d (bc02506), the
cards by their text. A request with one rejected passage adds the note to that card only
and the instruction once.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from app.rag.compare import judge
from app.rag.compare.overlap import OverlapReport
from app.rag.steps import explain
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import listwise
from app.rag.steps.llm_rerank.base import ScoreResult
from app.rag.steps.passage_role import REJECTED_INSTRUCTION
from app.rag.steps.rerank_docs import cohere_document, llm_card
from app.rag.steps.types import ChunkCandidate, PipelineResult, RankedChunk

# SHA-256 of each system prompt on master before 2.4d.
TODAY_LISTWISE_SHA = "0892abc655b218192b6c783935b9fdcdbe9727c820477dcdf42451286cf9697d"
TODAY_EXPLAIN_SHA = "8a3d2d5b501758520baa1b7a8a823abed19d19b7ce2d94cf4e49302c33e4d0a0"
TODAY_JUDGE_SHA = "36e6fb8953c1ff488c981ec131afde3bc32781ce07ffc49fb2e3f4ec6f308013"

OBJECTION = dict(
    chunk_id="c1", content="It would seem that the just man sins.",
    reference="Summa Theologiae I-II, q. 109, a. 2", collection="summa",
    document_id="d1", document_title="Summa Theologiae", author="Thomas Aquinas",
    unit_label="Objection 1",
)
CANON = dict(
    chunk_id="c2", content="The Christian faithful are bound.",
    reference="Code of Canon Law, Can. 33", collection="canon-law", document_id="d2",
    document_title="Code of Canon Law", author=None, unit_label="Can. 33",
    annotation="SUMMARY: duties.",
)
CONDEMNED = dict(
    chunk_id="c3", content="In every good work the just man sins.",
    reference="Pope Leo X — Exsurge Domine, §31", collection="papal-documents",
    document_id="d3", document_title="Exsurge Domine", author="Pope Leo X",
    unit_label="Condemned proposition 31", voice="rejected",
)
NOTE = ("Rejected position (Condemned proposition 31): the document states this in "
        "order to reject it.")

# Master's output for OBJECTION and CANON, which carry no voice.
TODAY_COHERE = {
    "c1": "[Summa Theologiae I-II, q. 109, a. 2] [Objection 1] It would seem that the "
          "just man sins.",
    "c2": "[Code of Canon Law, Can. 33] SUMMARY: duties.\nThe Christian faithful are bound.",
}
TODAY_CARD = {
    "c1": "[c1] (summa) Summa Theologiae I-II, q. 109, a. 2 — Objection 1\nIt would seem "
          "that the just man sins.",
    "c2": "[c2] (canon-law) Code of Canon Law, Can. 33\nSUMMARY: duties.\nThe Christian "
          "faithful are bound.",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _candidate(fields) -> ChunkCandidate:
    return ChunkCandidate(rrf_score=0.5, **fields)


def _ranked(fields) -> RankedChunk:
    return RankedChunk(reranker_score=0.5, **fields)


# --- the Cohere document and the listwise card ---

def test_cards_without_a_rejected_passage_are_todays():
    for fields in (OBJECTION, CANON):
        assert cohere_document(_candidate(fields)) == TODAY_COHERE[fields["chunk_id"]]
        assert llm_card(_candidate(fields)) == TODAY_CARD[fields["chunk_id"]]


def test_a_rejected_passage_carries_its_note():
    assert cohere_document(_candidate(CONDEMNED)) == (
        "[Pope Leo X — Exsurge Domine, §31] [Condemned proposition 31]\n"
        f"{NOTE}\n"
        "In every good work the just man sins.")
    assert llm_card(_candidate(CONDEMNED)) == (
        "[c3] (papal-documents) Pope Leo X — Exsurge Domine, §31 — Condemned proposition 31\n"
        f"{NOTE}\n"
        "In every good work the just man sins.")
    annotated = _candidate(dict(CONDEMNED, annotation="SUMMARY: condemned."))
    assert cohere_document(annotated).endswith(
        f"]\n{NOTE}\nSUMMARY: condemned.\nIn every good work the just man sins.")


def test_a_summa_objection_with_voice_keeps_its_role_and_adds_the_note():
    objection = _candidate(dict(OBJECTION, voice="rejected"))
    note = "Rejected position (Objection 1): the document states this in order to reject it."
    assert llm_card(objection) == f"{TODAY_CARD['c1'].split(chr(10))[0]}\n{note}\n" \
                                  "It would seem that the just man sins."


# --- the listwise request ---

def _listwise_request(pool):
    seen = {}

    async def call(provider, system, user, max_tokens, schema):
        seen.update(system=system, user=user)
        return ScoreResult(json.dumps({"results": [
            {"position": i, "score": 0.5} for i in range(len(pool))]}), 1, 1)

    class _Provider:
        name = "luna"
        model_id = "test"

        def is_ready(self):
            return True

    with patch.object(listwise, "call_provider", call), \
         patch.object(listwise.random, "shuffle", lambda items: None):
        asyncio.run(listwise.rerank_pool(pool, "q", CostTracker(), _Provider()))
    return seen["system"], seen["user"]


def test_listwise_request_without_a_rejected_passage_is_todays():
    system, user = _listwise_request([_ranked(OBJECTION), _ranked(CANON)])
    assert _sha(system) == TODAY_LISTWISE_SHA
    assert user == "Query: q\n\nPassages:\n" + "\n".join(
        json.dumps({"position": i, "source_material": TODAY_CARD[cid]}, ensure_ascii=False)
        for i, cid in enumerate(("c1", "c2")))


def test_listwise_request_with_a_rejected_passage_adds_the_instruction_once():
    system, user = _listwise_request(
        [_ranked(OBJECTION), _ranked(CONDEMNED), _ranked(CANON)])
    assert system.count(REJECTED_INSTRUCTION) == 1
    assert system.replace(f"{REJECTED_INSTRUCTION}\n\n", "") == listwise._LISTWISE_SYSTEM
    # After the role rules, before the scoring bands.
    assert system.index("Section, canon, and verse locators") < system.index(
        REJECTED_INSTRUCTION) < system.index("First assign relevance")
    assert user.count("Rejected position") == 1
    assert json.dumps(NOTE, ensure_ascii=False)[1:-1] in user


# --- the explanation ---

def _explain_messages(fields):
    captured = {}

    class _Client:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    raise RuntimeError("stop after capture")

    async def drain():
        with patch.object(explain, "_client", _Client()):
            async for _ in explain.stream(
                fields["content"], fields["reference"], fields["collection"], "q",
                unit_label=fields["unit_label"], voice=fields.get("voice"),
            ):
                pass

    asyncio.run(drain())
    return captured["messages"]


def test_explanation_without_a_rejected_passage_is_todays():
    system, user = _explain_messages(OBJECTION)
    assert _sha(system["content"]) == TODAY_EXPLAIN_SHA
    assert user["content"] == (
        "Question: q\n\nPassage (Summa Theologiae I-II, q. 109, a. 2 — Objection 1): "
        "It would seem that the just man sins.")


def test_explanation_of_a_rejected_passage_has_the_note_and_the_instruction():
    system, user = _explain_messages(CONDEMNED)
    assert system["content"] == f"{explain._EXPLAIN_SYSTEM}\n\n{REJECTED_INSTRUCTION}"
    assert user["content"] == (
        f"Question: q\n\n{NOTE}\n"
        "Passage (Pope Leo X — Exsurge Domine, §31 — Condemned proposition 31): "
        "In every good work the just man sins.")


# --- the eval judge ---

def _result(*fields) -> PipelineResult:
    return PipelineResult(pipeline="p", chunks=[_ranked(f) for f in fields],
                          step_timings=[], total_duration_s=0.0, cost_breakdown={},
                          total_cost=0.0)


REPORT = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={}, score_delta={})


def test_judge_without_a_rejected_passage_is_todays():
    result = _result(OBJECTION, CANON)
    assert _sha(judge._JUDGE_SYSTEM) == TODAY_JUDGE_SHA
    assert judge._system_blocks([result]) == [
        {"type": "text", "text": judge._JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}]
    assert judge._build_prompt("q", [result], REPORT) == "\n".join([
        "Query: q\n", "Shared chunks (in ALL pipelines): []",
        "Unique chunks per pipeline: {}\n", "=== Pipeline: p ===",
        "  [1] (UNIQUE) score=0.500 ref=Summa Theologiae I-II, q. 109, a. 2 role=Objection 1\n"
        "      It would seem that the just man sins.",
        "  [2] (UNIQUE) score=0.500 ref=Code of Canon Law, Can. 33\n"
        "      The Christian faithful are bound.",
        "",
    ])


def test_judge_with_a_rejected_passage_sees_what_production_sees():
    result = _result(OBJECTION, CONDEMNED)
    blocks = judge._system_blocks([result])
    assert [b["text"] for b in blocks] == [judge._JUDGE_SYSTEM, REJECTED_INSTRUCTION]
    prompt = judge._build_prompt("q", [result], REPORT)
    assert prompt.count("Rejected position") == 1
    assert (f"role=Condemned proposition 31\n      {NOTE}\n"
            "      In every good work the just man sins.") in prompt


# --- every RankedChunk built under app/rag passes voice on ---

def test_every_ranked_chunk_constructor_passes_voice():
    """A new constructor that forgets `voice` would silently drop the role for every
    passage it builds; this lists them all."""
    root = Path(__file__).resolve().parents[1] / "app" / "rag"
    missing, found = [], 0
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "RankedChunk"):
                found += 1
                keywords = {k.arg for k in node.keywords}
                if "voice" not in keywords and None not in keywords:  # None: **kwargs
                    missing.append(f"{path.relative_to(root)}:{node.lineno}")
    assert found >= 3
    assert missing == []
