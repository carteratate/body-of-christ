"""Corpus cleanup 2.4d: a rejected passage's `voice` reaches every model and the card.

`roles.voice_reaches_model_inputs` in the spec. One search goes through
`run_search_pipeline` and the real runner, with a real Postgres migrated through 0043
for the keyword search and the position lookup, and fakes only at the provider edges:
Qdrant, Cohere, the listwise model and the explanation model. Three rejected passages
go in, each reaching the candidates a different way:

  VECTOR    found only by vector search; `voice` is on the Qdrant payload
  KEYWORD   found only by keyword search; `voice` comes from the SQL
  BACKFILL  found only by vector search; the payload lacks `voice`, so
            `fetch_positions` fills it from Postgres

Each must reach the Cohere document, the listwise card, the explanation input, the chunk
event and the eval judge's input with its note, in every rerank mode the registry's
pipelines use (Cohere alone; Cohere then listwise), on the scored path and on the RRF
fallback path. With the position lookup skipped (the degraded path) the payload value
still reaches the rerankers.

docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.4d.
"""
import contextlib
import json
import types
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from app import corpus_schema
from app.db import _init_connection
from app.rag import pipeline
from app.rag.compare import judge
from app.rag.compare.overlap import OverlapReport
from app.rag.steps.llm_rerank.base import ScoreResult
from app.rag.steps.passage_role import REJECTED_INSTRUCTION
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

pytestmark = pytest.mark.real_corpus_schema

COLLECTION = "papal"
# One document each, so dedup's per-source cap keeps all three.
DOC_V = "00000000-0000-0000-0000-00000000b001"
DOC_K = "00000000-0000-0000-0000-00000000b002"
DOC_B = "00000000-0000-0000-0000-00000000b003"
VECTOR = "00000000-0000-0000-0000-0000000000c1"
KEYWORD = "00000000-0000-0000-0000-0000000000c2"
BACKFILL = "00000000-0000-0000-0000-0000000000c3"
LABELS = {
    VECTOR: "Condemned proposition 31",
    KEYWORD: "Condemned proposition 32",
    BACKFILL: "Condemned proposition 33",
}
NOTES = {cid: f"Rejected position ({label}): the document states this in order to "
              "reject it." for cid, label in LABELS.items()}

SEED = f"""
    INSERT INTO documents (id, collection, title, author, metadata) VALUES
      ('{DOC_V}', '{COLLECTION}', 'Exsurge Domine', 'Pope Leo X', '{{}}'),
      ('{DOC_K}', '{COLLECTION}', 'Exsurge Domine II', 'Pope Leo X', '{{}}'),
      ('{DOC_B}', '{COLLECTION}', 'Exsurge Domine III', 'Pope Leo X', '{{}}');
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, content,
                        unit_label, voice) VALUES
      ('{VECTOR}', '{DOC_V}', 0, 'p31', 'c1', 'lorem ipsum dolor',
       '{LABELS[VECTOR]}', 'rejected'),
      ('{KEYWORD}', '{DOC_K}', 0, 'p32', 'c1', 'a just man sins in every good work',
       '{LABELS[KEYWORD]}', 'rejected'),
      ('{BACKFILL}', '{DOC_B}', 0, 'p33', 'c1', 'sit amet consectetur',
       '{LABELS[BACKFILL]}', 'rejected');
"""
QUERY = "does the just man sin in every good work"


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-rejected-voice-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name,
                        "0046_collection_keys.sql", "0048_drop_legacy_collection_keys.sql")
        running.sql(SEED)
        yield running


def _point(chunk_id, doc_id, content, *, voice):
    payload = {
        "content": content, "collection": COLLECTION, "document_id": doc_id,
        "document_title": "Exsurge Domine", "reference": f"Exsurge Domine, {chunk_id[-2:]}",
        "unit_label": LABELS[chunk_id],
    }
    if voice:
        payload["voice"] = "rejected"
    return types.SimpleNamespace(id=chunk_id, payload=payload)


class _Qdrant:
    """Vector search finds VECTOR (voice on its payload) and BACKFILL (none)."""

    async def query_points(self, **kwargs):
        return types.SimpleNamespace(points=[
            _point(VECTOR, DOC_V, "lorem ipsum dolor", voice=True),
            _point(BACKFILL, DOC_B, "sit amet consectetur", voice=False),
        ])


class _Cohere:
    def __init__(self):
        self.documents: list[str] = []

    async def rerank(self, **kwargs):
        self.documents.extend(kwargs["documents"])
        return types.SimpleNamespace(
            results=[types.SimpleNamespace(index=i, relevance_score=0.9)
                     for i in range(len(kwargs["documents"]))],
            meta=types.SimpleNamespace(billed_units=types.SimpleNamespace(search_units=1)),
        )


class _Explain:
    """The OpenAI client the explanation step streams from."""

    def __init__(self):
        self.requests: list[list[dict]] = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append(kwargs["messages"])

        async def deltas():
            yield types.SimpleNamespace(
                usage=None,
                choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="ok"))])
        return deltas()


@contextlib.asynccontextmanager
async def _search(cluster, *, pipeline_name, cohere_scores=True, listwise_scores=True,
                  degraded=False):
    """Run one search; yield what each model and the client received."""
    pool = await asyncpg.create_pool(
        host=str(cluster.socket), user="postgres", database="postgres",
        min_size=1, max_size=3, statement_cache_size=0, init=_init_connection,
    )
    seen = types.SimpleNamespace(cohere=_Cohere(), explain=_Explain(), listwise=[],
                                 events=[], results=[])

    async def listwise_call(provider, system, user, max_tokens, schema):
        seen.listwise.append((system, user))
        if not listwise_scores:
            raise RuntimeError("listwise down")
        count = user.count('"position":')
        return ScoreResult(json.dumps({"results": [
            {"position": i, "score": 0.9} for i in range(count)]}), 10, 10)

    real_run = pipeline.run_pipeline

    async def run_and_keep(**kwargs):
        result = await real_run(**kwargs)
        seen.results.append(result)
        return result

    try:
        with (
            patch("app.rag.pipeline._PRODUCTION_PIPELINE", pipeline_name),
            patch("app.rag.pipeline.run_pipeline", run_and_keep),
            patch("app.rag.pipeline.get_pool", return_value=None),
            patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1] * 1536)),
            patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
            patch("app.rag.steps.hyde_none.run", new=AsyncMock(return_value={})),
            patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=_Qdrant()),
            patch("app.rag.steps.retrieve_fts.get_pool", return_value=pool),
            patch("app.rag.steps.fetch_positions.get_pool",
                  return_value=None if degraded else pool),
            patch("app.rag.steps.fetch_context.get_pool", return_value=pool),
            patch("app.corpus_schema.get_pool", return_value=pool),
            patch("app.rag.steps.rerank_cohere._client",
                  seen.cohere if cohere_scores else None),
            patch("app.rag.steps.llm_rerank.openai_provider._client", object()),
            patch("app.rag.steps.rerank_haiku._client", object()),
            patch("app.rag.steps.llm_rerank.listwise.call_provider", listwise_call),
            patch("app.rag.steps.explain._client", seen.explain),
        ):
            async for event in pipeline.run_search_pipeline(
                QUERY, [COLLECTION], "", 3, None,
            ):
                seen.events.append(event)
        yield seen
    finally:
        await pool.close()


def _assert_reaches_rerankers(seen, ids, *, listwise: bool, cohere_scored: bool):
    if cohere_scored:
        for cid in ids:
            [doc] = [d for d in seen.cohere.documents if LABELS[cid] in d]
            assert NOTES[cid] in doc
    if listwise:
        [(system, user)] = seen.listwise
        assert system.count(REJECTED_INSTRUCTION) == 1
        for cid in ids:
            assert json.dumps(NOTES[cid])[1:-1] in user


def _assert_reaches_outputs(seen, ids):
    chunks = {e["chunk_id"]: e for e in seen.events if e["type"] == "chunk"}
    assert set(ids) <= set(chunks)
    for cid in ids:
        assert chunks[cid]["source"]["voice"] == "rejected"
    # The explanation: the note above the passage, the instruction in the system prompt.
    explained = {
        cid: messages for messages in seen.explain.requests
        for cid in ids if f"({LABELS[cid]})" in messages[1]["content"]
    }
    assert set(explained) == set(ids)
    for cid, messages in explained.items():
        assert messages[0]["content"].endswith(REJECTED_INSTRUCTION)
        assert f"{NOTES[cid]}\nPassage (" in messages[1]["content"]
    # The judge reads the runner's result, as the eval suite does.
    [result] = seen.results
    report = OverlapReport(shared=[], partial={}, unique={}, rank_divergence={},
                           score_delta={})
    prompt = judge._build_prompt(QUERY, [result], report)
    for cid in ids:
        assert NOTES[cid] in prompt
    assert [b["text"] for b in judge._system_blocks([result])][1:] == [REJECTED_INSTRUCTION]


ALL = [VECTOR, KEYWORD, BACKFILL]
MODES = [
    # (pipeline, Cohere scores, listwise scores): every scored and fallback path.
    pytest.param("hyde_cohere", True, None, id="cohere-scored"),
    pytest.param("hyde_cohere", False, None, id="cohere-rrf-fallback"),
    pytest.param("hyde_cohere_luna_seats10t80", True, True, id="listwise-scored"),
    pytest.param("hyde_cohere_luna_seats10t80", True, False, id="listwise-fallback"),
    pytest.param("hyde_cohere_luna_seats10t80", False, True, id="cohere-fallback-listwise"),
]


@pytest.mark.parametrize("pipeline_name, cohere_scores, listwise_scores", MODES)
async def test_voice_reaches_model_inputs(cluster, pipeline_name, cohere_scores,
                                          listwise_scores):
    async with _search(cluster, pipeline_name=pipeline_name, cohere_scores=cohere_scores,
                       listwise_scores=bool(listwise_scores)) as seen:
        assert corpus_schema.LEGACY != await corpus_schema.current()
    _assert_reaches_rerankers(seen, ALL, listwise=listwise_scores is not None,
                              cohere_scored=cohere_scores)
    _assert_reaches_outputs(seen, ALL)


async def test_degraded_path_keeps_the_payload_voice(cluster):
    """With the position lookup skipped, nothing backfills, so the payload and the SQL
    are the only sources: VECTOR and KEYWORD keep their note, BACKFILL has none."""
    async with _search(cluster, pipeline_name="hyde_cohere_luna_seats10t80",
                       degraded=True) as seen:
        pass
    _assert_reaches_rerankers(seen, [VECTOR, KEYWORD], listwise=True, cohere_scored=True)
    [doc] = [d for d in seen.cohere.documents if LABELS[BACKFILL] in d]
    assert "Rejected position" not in doc
    _assert_reaches_outputs(seen, [VECTOR, KEYWORD])
