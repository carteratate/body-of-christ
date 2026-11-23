"""Document facts on live search chunk events (corpus cleanup 2.4a)."""
import dataclasses
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
        "passage_author": None, "voice": None, "author": "Justin Martyr", "year": 155,
        "translation": "Ante-Nicene Fathers", "date_display": "c. 155", "genre": "treatise",
        "form": None,
        "issuer": None, "issuer_label": None, "certainty": "genuine",
        "attribution_note": None, "notes": None, "source_credit": "Sourced via CCEL.org",
        "superseded_by": None, "superseded_note": None, "work_title": None,
        "work_author": None, "work_year": None, "work_date_display": None,
        "work_genre": None, "work_certainty": None, "work_attribution_note": None,
        "work_notes": None, "text_source": None, "text_status": None,
        "official_latin_url": None,
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
         patch("app.rag.pipeline.fetch_footnotes", AsyncMock(return_value={})), \
         patch("app.rag.pipeline.fetch_headings", AsyncMock(return_value={})):
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


async def test_chunk_events_carry_the_documents_form(monkeypatch):
    """Issue #330: a papal document's form (bull, brief) rides with its facts, and is
    read from documents.form only where 0044 has added the column."""
    monkeypatch.setattr(corpus_schema, "_cached",
                        dataclasses.replace(WITH_0042, form=True))
    pool = MagicMock(fetch=AsyncMock(return_value=[_row(genre="encyclical", form="brief")]))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert (source["facts"]["genre"], source["facts"]["form"]) == ("encyclical", "brief")
    assert "d.form," in pool.fetch.await_args.args[0]


async def test_without_0044_the_facts_query_reads_no_form(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row()]))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert source["facts"]["form"] is None
    sql = pool.fetch.await_args.args[0]
    assert "NULL::text AS form" in sql and "d.form" not in sql


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


# --- voice (corpus cleanup 2.4d) ---

async def test_no_voice_field_in_the_chunk_event_when_unset(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row()]))
    assert "voice" not in _chunk_event(await _events(pool, _result()))["source"]


async def test_a_rejected_passage_is_marked_in_the_chunk_event(with_0042):
    result = _result()
    result.chunks[0].voice = "rejected"
    pool = MagicMock(fetch=AsyncMock(return_value=[_row()]))
    assert _chunk_event(await _events(pool, result))["source"]["voice"] == "rejected"


def test_saved_searches_and_bookmarks_read_voice_from_the_facts_row():
    """Restore and bookmarks build their source from `source_fields`."""
    from app.rag.steps.document_facts import _passage_facts, _sql

    assert "c.voice" in _sql(works=True)
    assert _passage_facts(_row(voice="rejected")).source_fields()["voice"] == "rejected"
    assert "voice" not in _passage_facts(_row()).source_fields()


def test_reader_passages_carry_voice_with_0042():
    from app.routes.documents import _passages_sql

    assert "voice" in _passages_sql(WITH_0042)
    assert "voice" not in _passages_sql(corpus_schema.LEGACY)


# --- text labels (corpus cleanup 2.4f) ---

LATIN = "https://www.vatican.va/content/francesco/la/motu_proprio/documents/de-concordia.html"


async def test_no_text_label_fields_in_the_chunk_event_when_unset(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row()]))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert not {"text_source", "text_status", "official_latin_url"} & set(source)


async def test_a_scanned_passage_is_labelled_in_the_chunk_event(with_0042):
    pool = MagicMock(fetch=AsyncMock(return_value=[_row(text_source="ocr")]))
    source = _chunk_event(await _events(pool, _result()))["source"]
    assert source["text_source"] == "ocr"
    assert not {"text_status", "official_latin_url"} & set(source)


async def test_an_unofficial_english_canon_carries_its_latin_link(with_0042):
    row = _row(text_status="unofficial_english", official_latin_url=LATIN)
    source = _chunk_event(await _events(MagicMock(fetch=AsyncMock(return_value=[row])),
                                        _result()))["source"]
    assert source["text_status"] == "unofficial_english"
    assert source["official_latin_url"] == LATIN


def test_only_the_three_keys_and_known_values_leave_the_api():
    """The SQL names three metadata keys and never the whole column; unknown values and
    a non-web link are dropped rather than sent."""
    from app.rag.steps.document_facts import _passage_facts, _sql

    sql = _sql(works=True)
    for key in ("text_source", "text_status", "official_latin_url"):
        assert f"c.metadata->>'{key}'" in sql
    assert "c.metadata," not in sql and "c.metadata " not in sql
    odd = _row(text_source="typed", text_status="official", official_latin_url="javascript:x")
    fields = _passage_facts(odd).source_fields()
    assert not {"text_source", "text_status", "official_latin_url"} & set(fields)


def test_saved_searches_and_bookmarks_read_text_labels_from_the_facts_row():
    from app.models.bookmarks import BookmarkSource
    from app.models.search import ChunkSource
    from app.rag.steps.document_facts import _passage_facts

    fields = _passage_facts(_row(text_source="ocr", text_status="unofficial_english",
                                 official_latin_url=LATIN)).source_fields()
    base = {"collection": "canon-law", "document_title": "Code", "document_id": DOC}
    for model in (ChunkSource, BookmarkSource):
        parsed = model(**base, **fields)
        assert (parsed.text_source, parsed.text_status, parsed.official_latin_url) == (
            "ocr", "unofficial_english", LATIN)


def test_reader_passages_carry_text_labels_with_0042():
    from app.routes.documents import _passages_sql

    assert "official_latin_url" in _passages_sql(WITH_0042)
    assert "metadata" not in _passages_sql(corpus_schema.LEGACY)
