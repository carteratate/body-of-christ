"""Excerpt-only documents (issue #265): the API refuses their reader and contents, and
labels their passages so clients link to the source instead."""
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from fastapi import HTTPException

from app import reader_access
from app.models.auth import AuthUser
from app.routes import sources
from app.routes.documents import get_document, get_document_reader, get_document_toc
from tests.fake_pool import FakePool

DOC = "11111111-1111-1111-1111-111111111111"
URL = "https://www.papalencyclicals.net/leo13/l13liber.htm"
USER = AuthUser(user_id="u", email=None)


def _doc_row(access, metadata=None, collection="encyclicals"):
    return {"id": DOC, "collection": collection, "title": "Libertas", "author": "Pope Leo XIII",
            "year": 1888, "translation": None,
            "metadata": {"url": URL} if metadata is None else metadata,
            "cnt": 40, "outline_ready": True, "reader_access": access}


def _pool(row):
    pool = FakePool()
    pool.conn.fetchrow.return_value = row
    return pool


@pytest.mark.parametrize("route", [get_document_toc, get_document_reader])
@pytest.mark.parametrize("user", [USER, None], ids=["signed-in", "no-user"])
def test_reader_and_toc_refuse_an_excerpt_only_document(route, user):
    """The refusal is in the route body, after require_document_access admits the
    caller, so it holds for a guest (user None) exactly as for a signed-in reader."""
    pool = _pool(_doc_row("excerpt"))
    kwargs = {"anchor": None, "chapter": None} if route is get_document_reader else {}
    with patch("app.routes.documents.get_pool", return_value=pool):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(route(DOC, user=user, **kwargs))
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "reader_restricted"
    assert caught.value.detail["source_url"] == URL
    # Refused before any chapter or passage is read.
    pool.conn.fetch.assert_not_awaited()
    assert pool.conn.fetchrow.await_count == 1


def test_a_full_document_still_opens():
    pool = _pool(_doc_row("full"))
    pool.conn.fetch.side_effect = [[{"chapter_key": "c1", "chapter_label": "Libertas"}], []]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_toc(DOC, user=USER))
    assert [c.chapter_key for c in resp.chapters] == ["c1"]
    assert resp.document.reader_access == "full"
    assert resp.document.source_url is None


def test_document_metadata_names_the_access_and_the_source():
    with patch("app.routes.documents.get_pool", return_value=_pool(_doc_row("excerpt"))):
        resp = asyncio.run(get_document(DOC, user=None))
    assert resp.reader_access == "excerpt"
    assert resp.source_url == URL


def test_without_migration_0041_every_document_reads_as_full():
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [
        asyncpg.UndefinedColumnError('column d.reader_access does not exist'), _doc_row("full")]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document(DOC, user=USER))
    assert resp.reader_access == "full"
    first, second = [c.args[0] for c in pool.conn.fetchrow.await_args_list]
    assert "d.reader_access" in first
    assert "'full' AS reader_access" in second and "d.chunk_count" in second


def test_a_missing_outline_never_switches_off_the_access_check():
    """Without 0037 the row falls back for the outline only, so an excerpt-only
    document stays refused."""
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [
        asyncpg.UndefinedColumnError('column d.chunk_count does not exist'), _doc_row("excerpt")]
    with patch("app.routes.documents.get_pool", return_value=pool):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(get_document_toc(DOC, user=USER))
    assert caught.value.status_code == 403
    second = pool.conn.fetchrow.await_args_list[1].args[0]
    assert "d.reader_access" in second and "d.chunk_count" not in second


def test_an_unrelated_missing_column_is_not_swallowed():
    pool = FakePool()
    pool.conn.fetchrow.side_effect = asyncpg.UndefinedColumnError('column d.metadata does not exist')
    with patch("app.routes.documents.get_pool", return_value=pool):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(get_document(DOC, user=USER))
    assert caught.value.status_code == 503
    assert pool.conn.fetchrow.await_count == 1


def test_the_catechism_and_canon_law_link_to_the_official_edition():
    assert reader_access.source_url("catechism", None).startswith("https://www.usccb.org/")
    assert reader_access.source_url("canon-law", {}).startswith("https://www.vatican.va/")
    assert reader_access.source_url("church-fathers", {}) is None
    assert reader_access.source_url("encyclicals", {"url": "javascript:alert(1)"}) is None


def test_each_rights_holder_gets_its_credit_line():
    notice = reader_access.source_credit("catechism", None)
    # The USCCB's required notice, verbatim, for any use of the Catechism.
    assert notice.startswith("Excerpts from the English translation of the Catechism")
    assert "Used with Permission." in notice
    assert reader_access.source_credit("encyclicals", "https://www.vatican.va/x.html") == \
        reader_access.VATICAN_CREDIT
    assert reader_access.source_credit("encyclicals", "http://www.vatican.va/x.html") == \
        reader_access.VATICAN_CREDIT
    # No credit is invented for sources whose rights holder isn't known.
    assert reader_access.source_credit("councils", "https://www.papalencyclicals.net/x") is None
    assert reader_access.source_credit("encyclicals", "https://evil.example/vatican.va") is None
    assert reader_access.source_credit("church-fathers", None) is None


def test_a_full_document_carries_no_credit():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {"id": uuid.UUID(DOC), "collection": "encyclicals", "metadata": {"url": URL},
         "reader_access": "full"},
    ]
    access = asyncio.run(reader_access.document_access(pool, [DOC]))
    assert reader_access.access_fields(access, DOC) == {
        "reader_access": "full", "source_url": None, "source_credit": None}


def test_document_access_maps_each_id_and_tolerates_a_missing_column():
    excerpt = uuid.UUID(DOC)
    pool = AsyncMock()
    pool.fetch.return_value = [
        {"id": excerpt, "collection": "catechism", "metadata": None, "reader_access": "excerpt"},
    ]
    access = asyncio.run(reader_access.document_access(pool, [DOC, None, DOC]))
    assert access[DOC].reader_access == "excerpt"
    assert access[DOC].source_url.startswith("https://www.usccb.org/")
    assert access[DOC].source_credit == reader_access.CATECHISM_NOTICE
    assert reader_access.access_fields(access, "unknown-id") == {
        "reader_access": "full", "source_url": None, "source_credit": None}

    pool.fetch.side_effect = asyncpg.UndefinedColumnError("reader_access")
    assert asyncio.run(reader_access.document_access(pool, [DOC])) == {}


def _source(doc_id, title):
    return {"id": doc_id, "collection": "encyclicals", "title": title, "author": None,
            "year": None, "translation": None, "metadata": {"url": URL}, "chunk_count": 3}


def test_sources_marks_excerpt_documents_from_a_fresh_read_past_the_cache():
    pool = FakePool()
    pool.conn.fetch.side_effect = [
        [_source("a", "Libertas"), _source("b", "Rerum Novarum")],
        [{"id": "a"}],
        [],  # second request: the sync reopened it; the cached list is reused
    ]
    with (patch("app.routes.sources.get_pool", return_value=pool),
          patch.object(sources, "_sources_cache", None)):
        first = asyncio.run(sources.get_sources(user=USER))
        second = asyncio.run(sources.get_sources(user=USER))
    by_id = {s.id: s for s in first.sources}
    assert (by_id["a"].reader_access, by_id["a"].source_url) == ("excerpt", URL)
    assert (by_id["b"].reader_access, by_id["b"].source_url) == ("full", None)
    assert {s.reader_access for s in second.sources} == {"full"}
    assert pool.conn.fetch.await_count == 3


def test_sources_without_migration_0041_reads_as_full():
    pool = FakePool()
    pool.conn.fetch.side_effect = [[_source("a", "Libertas")],
                                   asyncpg.UndefinedColumnError("reader_access")]
    with (patch("app.routes.sources.get_pool", return_value=pool),
          patch.object(sources, "_sources_cache", None)):
        resp = asyncio.run(sources.get_sources(user=USER))
    assert resp.sources[0].reader_access == "full"


# ── Passage sources: every surface learns which documents are excerpt-only ──────

def _excerpt_for(doc_id):
    return AsyncMock(return_value={
        str(doc_id): reader_access.DocumentAccess("excerpt", URL, reader_access.VATICAN_CREDIT)})


@pytest.mark.asyncio
async def test_search_chunk_events_carry_reader_access():
    from unittest.mock import MagicMock

    from app.rag.pipeline import run_search_pipeline
    from app.rag.search_plan import resolve_search_plan
    from app.rag.steps.types import RankedChunk

    chunk = RankedChunk(chunk_id="00000000-0000-0000-0000-000000000001", content="x",
                        reference="Libertas 1", collection="encyclicals", document_id=DOC,
                        document_title="Libertas", author="Pope Leo XIII", reranker_score=0.9)
    result = MagicMock(chunks=[chunk], outcome="success", total_cost=0.0, context={},
                       collection_outcomes={"encyclicals": "results"}, delivery_outcome=None)

    async def no_explanation(*args, **kwargs):
        return
        yield

    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
         patch("app.rag.pipeline.get_pool", return_value=MagicMock()), \
         patch("app.rag.pipeline.document_access", _excerpt_for(DOC)), \
         patch("app.rag.pipeline.stream_explanation", no_explanation):
        events = [e async for e in run_search_pipeline(
            query="liberty", collections=["encyclicals"], translation="CPDV", quota=3,
            user_id=None, search_plan=resolve_search_plan(["encyclicals"], 3))]

    [event] = [e for e in events if e["type"] == "chunk"]
    assert event["source"]["reader_access"] == "excerpt"
    assert event["source"]["source_url"] == URL
    assert event["source"]["source_credit"] == reader_access.VATICAN_CREDIT


@pytest.mark.asyncio
async def test_a_failed_access_lookup_degrades_to_the_reader_link():
    from unittest.mock import MagicMock

    from app.rag.pipeline import _document_access_for

    with patch("app.rag.pipeline.get_pool", return_value=MagicMock()), \
         patch("app.rag.pipeline.document_access", AsyncMock(side_effect=OSError("down"))):
        assert await _document_access_for([MagicMock(document_id=DOC)]) == {}


def _client(router):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.deps.auth import get_current_user

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id="u", email=None)
    return TestClient(app)


def test_bookmarks_carry_reader_access():
    from datetime import datetime, timezone

    from app.routes.bookmarks import router

    pool = AsyncMock()
    pool.fetch.return_value = [{
        "id": "00000000-0000-0000-0000-0000000000b1",
        "chunk_id": "00000000-0000-0000-0000-0000000000c1",
        "created_at": datetime(2026, 10, 16, tzinfo=timezone.utc), "note": None,
        "content": "Liberty, the highest of natural endowments...", "reference": "Libertas 1",
        "anchor": "a1", "chapter_key": "c1", "unit_label": None, "document_id": DOC,
        "collection": "encyclicals", "document_title": "Libertas", "author": "Pope Leo XIII",
    }]
    with patch("app.routes.bookmarks.get_pool", return_value=pool), \
         patch("app.routes.bookmarks.document_access", _excerpt_for(DOC)):
        body = _client(router).get("/v1/bookmarks").json()
    source = body["bookmarks"][0]["chunk"]["source"]
    assert (source["reader_access"], source["source_url"]) == ("excerpt", URL)
    assert source["source_credit"] == reader_access.VATICAN_CREDIT


# ── Reading progress ─────────────────────────────────────────────────────────

def test_reading_progress_is_not_written_for_an_excerpt_only_document():
    from app.routes.reading_progress import router

    pool = AsyncMock()
    with patch("app.routes.reading_progress.get_pool", return_value=pool), \
         patch("app.routes.reading_progress.document_access", _excerpt_for(DOC)):
        resp = _client(router).put(f"/v1/reading-progress/{DOC}",
                                   json={"chapter_key": "c1", "anchor": None})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "reader_restricted"
    pool.fetchrow.assert_not_awaited()


def test_reading_progress_filters_excerpt_documents_before_the_limit():
    """The filter is in the query, ahead of LIMIT: hidden rows never take the place of
    readable ones, however many recent documents are excerpt-only."""
    from app.routes.reading_progress import router

    pool = AsyncMock()
    pool.fetch.return_value = []
    pool.fetchrow.return_value = None
    with patch("app.routes.reading_progress.get_pool", return_value=pool):
        client = _client(router)
        client.get("/v1/reading-progress?limit=3")
        single = client.get(f"/v1/reading-progress/{DOC}")
    list_sql, _, limit = pool.fetch.await_args.args
    assert list_sql.index("reader_access <> 'excerpt'") < list_sql.index("LIMIT $2")
    assert limit == 3
    assert "reader_access <> 'excerpt'" in pool.fetchrow.await_args.args[0]
    assert single.status_code == 404


def test_reading_progress_without_migration_0041_lists_everything():
    from datetime import datetime, timezone

    from app.routes.reading_progress import router

    row = {"document_id": DOC, "chapter_key": "c1", "chapter_label": "C1", "anchor": None,
           "updated_at": datetime(2026, 10, 16, tzinfo=timezone.utc),
           "collection": "encyclicals", "document_title": "T", "author": None}
    pool = AsyncMock()
    pool.fetch.side_effect = [
        asyncpg.UndefinedColumnError("column d.reader_access does not exist"), [row]]
    with patch("app.routes.reading_progress.get_pool", return_value=pool):
        items = _client(router).get("/v1/reading-progress").json()["items"]
    assert [i["document_id"] for i in items] == [DOC]
    assert "reader_access" not in pool.fetch.await_args_list[1].args[0]
