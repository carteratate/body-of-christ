"""Document facts on live search chunk events (corpus cleanup 2.4a)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import corpus_schema
from app.rag.pipeline import run_search_pipeline
from app.rag.steps import document_facts
from app.rag.steps.types import RankedChunk

CHUNK = "00000000-0000-0000-0000-000000000001"
DOC = "00000000-0000-0000-0000-000000000099"

WITH_0042 = corpus_schema.CorpusSchema(retired=True, searchable=True, facts=True,
                                       works=True, tombstones=True, redirects=True)


def _row(**overrides):
    row = {
        "chunk_id": CHUNK, "language": None, "note": "A note.",
        "passage_author": None, "author": "Justin Martyr", "year": 155,
        "translation": "Ante-Nicene Fathers", "date_display": "c. 155", "genre": "treatise",
        "issuer": None, "issuer_label": None, "certainty": "genuine",
        "attribution_note": None, "notes": None, "source_credit": "Sourced via CCEL.org",
        "superseded_by": None, "superseded_note": None, "work_title": None,
        "work_author": None, "work_year": None, "work_date_display": None,
        "work_genre": None, "work_certainty": None, "work_attribution_note": None,
        "work_notes": None,
    }
    row.update(overrides)
    return row


def _result():
    result = MagicMock()
    result.chunks = [RankedChunk(
        chunk_id=CHUNK, content="text", reference="1 Apol. 1",
        collection="church-fathers", document_id=DOC, document_title="First Apology",
        author="Payload Author", reranker_score=0.9)]
    result.outcome = "success"
    result.collection_outcomes = {"church-fathers": "results"}
    result.delivery_outcome = None
    result.total_cost = 0.0
    result.context = {}
    result.recovery_events = []
    result.degradation_events = []
    return result


async def _no_explanation(*args, **kwargs):
    if False:
        yield ""


async def _events(pool, result):
    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
         patch("app.rag.pipeline.get_pool", return_value=pool), \
         patch("app.rag.pipeline.stream_explanation", _no_explanation), \
         patch("app.rag.pipeline.fetch_footnotes", AsyncMock(return_value={})):
        return [e async for e in run_search_pipeline(
            query="logos", collections=["church-fathers"], translation="CPDV", quota=3,
            user_id=None)]


def _chunk_event(events):
    return next(e for e in events if e["type"] == "chunk")


@pytest.fixture()
def with_0042(monkeypatch):
    monkeypatch.setattr(corpus_schema, "_cached", WITH_0042)


async def test_chunk_events_include_facts_when_0042_exists(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row()]))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert source["facts"]["date_display"] == "c. 155"
    assert source["facts"]["source_credit"] == "Sourced via CCEL.org"
    assert source["passage_note"] == "A note."
    assert source["language"] is None and source["passage_author"] is None


async def test_the_author_shown_comes_from_postgres_when_the_payload_disagrees(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row()]))
    assert _chunk_event(await _events(pool, _result()))["source"]["author"] == "Justin Martyr"


async def test_work_values_override_document_values(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row(
        work_title="Dubious Writings", work_author="Pseudo-Justin",
        work_certainty="pseudonymous", work_date_display="4th c.")]))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert source["author"] == "Pseudo-Justin"
    assert source["facts"]["certainty"] == "pseudonymous"
    assert source["facts"]["date_display"] == "4th c."
    assert source["facts"]["work_title"] == "Dubious Writings"
    assert source["facts"]["genre"] == "treatise"  # no work value: the document's


async def test_an_excerpt_documents_required_notice_wins_over_the_stored_credit():
    facts = document_facts._passage_facts(_row())
    assert facts.source_fields("© LEV")["facts"]["source_credit"] == "© LEV"
    assert facts.source_fields(None)["facts"]["source_credit"] == "Sourced via CCEL.org"


async def test_a_failing_facts_query_yields_events_without_facts_and_a_recovery(with_0042):
    pool = MagicMock(fetch=AsyncMock(side_effect=OSError("connection reset")))
    result = _result()
    events = await _events(pool, result)
    source = _chunk_event(events)["source"]
    assert "facts" not in source and source["author"] == "Payload Author"
    assert [e["stage"] for e in result.recovery_events] == ["document_facts"]
    assert result.degradation_events == []
    assert any(e["type"] == "done" for e in events)


async def test_without_0042_no_query_runs_and_the_event_is_todays():
    pool = MagicMock(fetch=AsyncMock(side_effect=AssertionError("no query expected")))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert set(source) == {
        "collection", "document_title", "author", "reference", "document_id", "anchor",
        "chapter_key", "unit_label", "reader_access", "source_url", "source_credit"}
    assert source["author"] == "Payload Author"
