"""The passage-role label must survive every hop from retrieval to ranked output.

39.3% of the Summa is objections Aquinas states in order to REFUTE. The label is the
only thing distinguishing them — `ingest/summa.py` strips the "Objection 1" prefix out
of `content` and into `unit_label`, so a candidate that loses the label along the way
reaches the reranker as bare "It would seem that..." with nothing marking it.

Each hop is tested separately because they fail independently: a field can be selected
but not mapped, mapped but not carried through rerank, carried but not serialised.
"""
from __future__ import annotations

from app.rag.steps import retrieve_fts, rrf
from app.rag.steps.rerank_cohere import _as_ranked
from app.rag.steps.types import ChunkCandidate


def _fts_row(**over):
    row = {
        "id": "c1", "content": "It would seem that...", "reference": "ST I q1 a1",
        "collection": "summa", "document_id": "d1", "document_title": "Summa Theologiae",
        "author": "Thomas Aquinas", "anchor": "a1", "chapter_key": "ck1",
        "position": 1, "annotation": None, "unit_label": "Objection 1",
        "rrf_score": 0.9,
    }
    row.update(over)
    return row


# --- hop 1: the FTS query must ask Postgres for the column ---

def test_fts_query_selects_unit_label():
    assert "unit_label" in retrieve_fts._SQL


# --- hop 2: RRF builds ChunkCandidate from raw dicts ---

def test_rrf_propagates_unit_label_into_candidates():
    merged = rrf.run({}, {"summa": [_fts_row()]}, quota=4)
    assert merged["summa"][0].unit_label == "Objection 1"


def test_rrf_tolerates_a_missing_unit_label():
    """Most collections have no dialectical structure; absence is normal, not an error."""
    row = _fts_row()
    del row["unit_label"]
    merged = rrf.run({}, {"bible": [dict(row, collection="bible")]}, quota=4)
    assert merged["bible"][0].unit_label is None


# --- hop 3: reranking rebuilds the object; the label must be carried, not dropped ---

def test_cohere_rerank_carries_unit_label_onto_the_ranked_chunk():
    candidate = ChunkCandidate(
        chunk_id="c1", content="It would seem that...", reference="ST I q1 a1",
        collection="summa", document_id="d1", document_title="Summa Theologiae",
        author=None, rrf_score=0.9, unit_label="Objection 1",
    )
    assert _as_ranked(candidate, 0.8).unit_label == "Objection 1"


def test_listwise_rerank_carries_unit_label():
    from app.rag.steps.llm_rerank.listwise import _as_ranked as listwise_as_ranked
    from app.rag.steps.types import RankedChunk

    ranked = RankedChunk(
        chunk_id="c1", content="It would seem that...", reference="ST I q1 a1",
        collection="summa", document_id="d1", document_title="Summa Theologiae",
        author=None, reranker_score=0.5, unit_label="Objection 1",
    )
    assert listwise_as_ranked(ranked, 0.9, "luna").unit_label == "Objection 1"


def test_pointwise_rerank_carries_unit_label():
    from app.rag.steps.llm_rerank.pointwise import _ranked

    candidate = ChunkCandidate(
        chunk_id="c1", content="It would seem that...", reference="ST I q1 a1",
        collection="summa", document_id="d1", document_title="Summa Theologiae",
        author=None, rrf_score=0.9, unit_label="Objection 1",
    )
    assert _ranked(candidate, 0.8, True, "haiku").unit_label == "Objection 1"


# --- hop 4: the reranker prompts must explain what the label MEANS ---

def test_both_rerank_prompts_explain_that_an_objection_is_refuted():
    """The label is inert unless the model knows an objection argues AGAINST."""
    from app.rag.steps.llm_rerank.listwise import _LISTWISE_SYSTEM
    from app.rag.steps.llm_rerank.pointwise import _RERANK_SYSTEM

    for prompt in (_LISTWISE_SYSTEM, _RERANK_SYSTEM):
        assert "PASSAGE ROLE" in prompt
        assert "REFUTE" in prompt
        assert "'Objection N'" in prompt
        assert "'I answer that'" in prompt


def test_fetch_positions_backfills_unit_label_for_qdrant_candidates():
    """Qdrant payloads carry no unit_label until the payload reconcile runs, so the
    Postgres backfill is the only source for most collections today."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.rag.steps import fetch_positions

    candidate = ChunkCandidate(
        chunk_id="11111111-1111-1111-1111-111111111111",
        content="It would seem that...", reference="ST I q1 a1", collection="summa",
        document_id="d1", document_title="Summa Theologiae", author=None,
        rrf_score=0.9, position=None, unit_label=None,
    )
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "position": 7, "annotation": None,
        "chapter_key": "ck1", "unit_label": "Objection 1",
    }
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[row])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=pool):
        out = asyncio.run(fetch_positions.run({"summa": [candidate]}))

    assert out["summa"][0].unit_label == "Objection 1"
    assert out["summa"][0].position == 7


def test_fetch_positions_does_not_overwrite_a_payload_supplied_unit_label():
    """Post-reconcile the payload already carries it; the backfill must leave it be,
    so the DB round trip shrinks to nothing as the reconcile rolls out."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.rag.steps import fetch_positions

    candidate = ChunkCandidate(
        chunk_id="22222222-2222-2222-2222-222222222222",
        content="It would seem that...", reference="ST I q1 a1", collection="summa",
        document_id="d1", document_title="Summa Theologiae", author=None,
        rrf_score=0.9, position=None, unit_label="Objection 1",
    )
    row = {
        "id": "22222222-2222-2222-2222-222222222222",
        "position": 7, "annotation": None,
        "chapter_key": "ck1", "unit_label": "SOMETHING ELSE",
    }
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[row])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=pool):
        out = asyncio.run(fetch_positions.run({"summa": [candidate]}))

    assert out["summa"][0].unit_label == "Objection 1"


def test_label_is_lost_when_fetch_positions_degrades_and_payload_lacks_it():
    """The gap that `--fields structural` closes, pinned as an executable fact.

    Until the payload reconcile has run, fetch_positions is the only source of
    unit_label for a chunk the vector path found. (RRF metadata is first-writer-wins
    with vector lists first, so a chunk found by BOTH paths also takes the vector
    row's None and depends on the same backfill.) When its pool is unavailable it
    returns early without backfilling, so the candidate reaches the reranker
    unlabelled. Today that is
    survivable because Qdrant's stale `content` still carries an inline "Objection 1 "
    prefix — but that prefix is exactly what a content sync removes.

    Ordering consequence: a content sync is only safe once the label reaches the
    reranker independently of fetch_positions, i.e. once it is IN the payload.
    """
    import asyncio
    from unittest.mock import patch

    from app.rag.steps import fetch_positions

    candidate = ChunkCandidate(
        chunk_id="33333333-3333-3333-3333-333333333333",
        content="It would seem that...", reference="ST I q1 a1", collection="summa",
        document_id="d1", document_title="Summa Theologiae", author=None,
        rrf_score=0.9, position=None, unit_label=None,
    )

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=None):
        out = asyncio.run(fetch_positions.run({"summa": [candidate]}))

    assert out["summa"][0].unit_label is None


def test_payload_supplied_label_survives_a_degraded_fetch_positions():
    """With the label in the Qdrant payload, the degraded path keeps it."""
    import asyncio
    from unittest.mock import patch

    from app.rag.steps import fetch_positions
    from app.rag.steps.rerank_docs import llm_card

    candidate = ChunkCandidate(
        chunk_id="44444444-4444-4444-4444-444444444444",
        content="It would seem that...", reference="ST I q1 a1", collection="summa",
        document_id="d1", document_title="Summa Theologiae", author=None,
        rrf_score=0.9, position=None, unit_label="Objection 1",
    )

    with patch("app.rag.steps.fetch_positions.get_pool", return_value=None):
        out = asyncio.run(fetch_positions.run({"summa": [candidate]}))

    assert out["summa"][0].unit_label == "Objection 1"
    assert "Objection 1" in llm_card(out["summa"][0])


# --- hop 0: the Qdrant payload mapping (fed by the step-2 payload reconcile) ---

def test_retrieve_vector_maps_unit_label_from_the_payload():
    """Mutation-undetected before this test existed. This is the hop the payload
    reconcile exists to feed: post-reconcile the label arrives here, not via the
    Postgres backfill."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.rag.steps import retrieve_vector

    point = MagicMock()
    point.id = "55555555-5555-5555-5555-555555555555"
    point.payload = {
        "content": "It would seem that...", "collection": "summa",
        "document_id": "d1", "document_title": "Summa Theologiae",
        "reference": "ST I q1 a1", "unit_label": "Objection 1",
    }
    response = MagicMock()
    response.points = [point]
    client = AsyncMock()
    client.query_points = AsyncMock(return_value=response)

    with patch("app.rag.steps.retrieve_vector.get_qdrant_client", return_value=client):
        out = asyncio.run(retrieve_vector.run([0.1], {}, ["summa"], quota=4))

    assert out["summa"][0][0]["unit_label"] == "Objection 1"


# --- final hop: the live SSE stream the user actually sees ---

def test_live_chunk_event_carries_unit_label():
    """The restore endpoint had a test; the PRIMARY path did not — a mutation that
    dropped this field from the live stream passed the whole suite."""
    import inspect

    from app.rag import pipeline

    source = inspect.getsource(pipeline.run_search_pipeline)
    chunk_event = source[source.index('"type": "chunk"'):source.index('"reranker_score"')]
    assert '"unit_label": chunk.unit_label' in chunk_event


# --- the explanation path: the only place attributed prose is generated ---

def test_explanation_receives_the_unit_label():
    """`retrievals.explanation` is persisted and re-served forever, so an explanation
    written as though an objection were Aquinas' teaching is durable, not transient."""
    import inspect

    from app.rag import pipeline

    source = inspect.getsource(pipeline.run_search_pipeline)
    call = source[source.index("stream_explanation("):]
    assert "unit_label=chunk.unit_label" in call[:250]


def test_explain_prompt_explains_the_inversion_and_the_locator_exception():
    from app.rag.steps.explain import _EXPLAIN_SYSTEM

    assert "PASSAGE ROLE" in _EXPLAIN_SYSTEM
    assert "REFUTE" in _EXPLAIN_SYSTEM
    assert "locator" in _EXPLAIN_SYSTEM


def test_explain_header_marks_the_role_without_touching_the_passage_text():
    """The role must not be appended to the passage, or the model may read it as part
    of the source text it is asked to be faithful to."""
    import asyncio
    from unittest.mock import patch

    from app.rag.steps import explain

    captured = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    raise RuntimeError("stop after capture")

    async def _drain():
        with patch.object(explain, "_client", _FakeClient()):
            async for _ in explain.stream(
                "It would seem that...", "ST II-II q64 a6", "summa",
                "is it lawful to kill the innocent", unit_label="Objection 1",
            ):
                pass

    asyncio.run(_drain())
    user = captured["messages"][1]["content"]
    assert "Passage (ST II-II q64 a6 — Objection 1):" in user
    assert user.endswith("It would seem that...")


def test_explain_omits_a_label_the_reference_already_contains():
    """Non-Summa references end with their label ("Can. 33"); repeating it is noise."""
    import asyncio
    from unittest.mock import patch

    from app.rag.steps import explain

    captured = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    raise RuntimeError("stop after capture")

    async def _drain():
        with patch.object(explain, "_client", _FakeClient()):
            async for _ in explain.stream(
                "The Christian faithful are bound...", "Code of Canon Law, Can. 33",
                "canon-law", "what does canon 33 require", unit_label="Can. 33",
            ):
                pass

    asyncio.run(_drain())
    user = captured["messages"][1]["content"]
    assert "Passage (Code of Canon Law, Can. 33):" in user


# --- pointwise: the prompt was dead instruction without this ---

def test_pointwise_passage_record_carries_the_role():
    from app.rag.steps.llm_rerank import pointwise
    import json as _json

    candidate = ChunkCandidate(
        chunk_id="c1", content="It would seem that...", reference="ST I q1 a1",
        collection="summa", document_id="d1", document_title="Summa Theologiae",
        author=None, rrf_score=0.9, unit_label="Objection 1",
    )
    record = _json.loads(pointwise._format_passages([candidate]))
    assert record["role"] == "Objection 1"


def test_pointwise_passage_record_omits_a_redundant_role():
    from app.rag.steps.llm_rerank import pointwise
    import json as _json

    candidate = ChunkCandidate(
        chunk_id="c1", content="The Christian faithful...",
        reference="Code of Canon Law, Can. 33", collection="canon-law",
        document_id="d1", document_title="Code of Canon Law",
        author=None, rrf_score=0.9, unit_label="Can. 33",
    )
    record = _json.loads(pointwise._format_passages([candidate]))
    assert "role" not in record


def test_cohere_document_omits_a_redundant_role():
    from app.rag.steps.rerank_docs import cohere_document

    candidate = ChunkCandidate(
        chunk_id="c1", content="The Christian faithful...",
        reference="Code of Canon Law, Can. 33", collection="canon-law",
        document_id="d1", document_title="Code of Canon Law",
        author=None, rrf_score=0.9, unit_label="Can. 33",
    )
    assert cohere_document(candidate) == "[Code of Canon Law, Can. 33] The Christian faithful..."


def test_cohere_only_pipelines_are_segmented_for_the_document_change():
    """cohere_document now injects the label, so Cohere's INPUT changed. Without a
    marker, pre- and post-change hyde_cohere runs both record None and pool."""
    from app.rag.steps.rerank import RerankConfig, contract_version

    assert contract_version(RerankConfig(use_cohere=True, llm_provider=None)) is not None
