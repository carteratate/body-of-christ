"""Passage links into vatican.va (2.4e, #292): an excerpt-only passage links to its
opening words on the vatican.va page with a text fragment."""
import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app import catechism_pages, reader_access, source_links
from app.reader_access import DocumentAccess, access_fields
from app.routes.documents import get_document_reader
from tests.fake_pool import FakePool

DOC = "11111111-1111-1111-1111-111111111111"
CHUNK = "00000000-0000-0000-0000-0000000000c1"
VATICAN = ("https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/"
           "vat-ii_const_19651207_gaudium-et-spes_en.html")
GS22 = ("The truth is that only in the mystery of the incarnate Word does the mystery of "
        "man take on light.")
GS22_URL = (VATICAN + "#:~:text=The%20truth%20is%20that%20only%20in%20the%20mystery")


def _excerpt(url=VATICAN, credit=reader_access.VATICAN_CREDIT):
    return {DOC: DocumentAccess("excerpt", url, credit)}


# ── The fragment's words ────────────────────────────────────────────────────

@pytest.mark.parametrize("content,expected", [
    (GS22, "The truth is that only in the mystery"),
    # A passage that starts with its own paragraph number keeps it out.
    ("22. " + GS22, "The truth is that only in the mystery"),
    ("(22) " + GS22, "The truth is that only in the mystery"),
    ("22.\n\n" + GS22, "The truth is that only in the mystery"),
    # Footnote markers: fixed to a word's punctuation, spaced after it, in brackets.
    ("Emphasizing the ars celebrandi leads to norms.12 and more words",
     "Emphasizing the ars celebrandi leads to norms."),
    ('In his intimate life, God "is love," 36 the essential love shared',
     'In his intimate life, God "is love,"'),
    ("Together with the Synod Fathers, ( 179 ) I ask these institutions",
     "Together with the Synod Fathers,"),
    ('the heart of [a] father could ever be more tender', "the heart of"),
    # A reference inside a token goes whole: "8:" may not end a word on the page.
    ("We know that all things work, Rom 8:28, for good", "We know that all things work, Rom"),
    # Quotation marks the stored text spaced from their words.
    ("Consequently I renew my encouragement to “ recover the deepest meaning",
     "Consequently I renew my encouragement to"),
    ("“ Caritas in veritate ” is the principle", "Caritas in veritate"),
    # A heading line is its own block on the page: the first full line is used.
    ("Worker Solidarity\n\nWhen dealing with human work in the fundamental dimension",
     "When dealing with human work in the fundamental"),
    # A passage opening on a citation's tail starts after it.
    ('Jas. 1:17). As the Council teaches, Mary "stands out among the poor',
     'As the Council teaches, Mary "stands out among'),
    ("(a) To bishops, as successors of the Apostles, in the dioceses",
     "To bishops, as successors of the Apostles, in"),
    # It never ends on a dash the page may break differently.
    ("The dignity and the vocation of women - a subject of reflection",
     "The dignity and the vocation of women"),
])
def test_fragment_text_takes_the_reliable_opening_words(content, expected):
    assert source_links.fragment_text(content) == expected


@pytest.mark.parametrize("content", [None, "", "VI", "Mt 25:31-46).", "Behold [your] mother"])
def test_too_few_reliable_words_give_no_fragment(content):
    assert source_links.fragment_text(content) is None


def test_with_fragment_encodes_the_directive_syntax():
    assert source_links.with_fragment("https://www.vatican.va/a.html", "one-two, three & four") \
        == "https://www.vatican.va/a.html#:~:text=one%2Dtwo%2C%20three%20%26%20four"
    # A URL that already has a fragment takes the directive after it.
    assert source_links.with_fragment("https://www.vatican.va/a.html#top", "a b c") \
        == "https://www.vatican.va/a.html#top:~:text=a%20b%20c"


# ── Which links get one ─────────────────────────────────────────────────────

def test_a_vatican_passage_links_to_its_opening_words():
    fields = access_fields(_excerpt(), DOC, "§22", chunk_id=CHUNK, content=GS22)
    assert fields == {"reader_access": "excerpt", "source_url": GS22_URL,
                      "source_credit": reader_access.VATICAN_CREDIT}
    plain_host = VATICAN.replace("https://www.", "http://")
    assert access_fields(_excerpt(plain_host), DOC, content=GS22)["source_url"].startswith(
        plain_host + "#:~:text=")


@pytest.mark.parametrize("url", [
    "https://www.papalencyclicals.net/leo13/l13liber.htm",
    "https://evil.example/www.vatican.va/x.html",
    "https://vatican.va.evil.example/x.html",
    # Canon Law's link is the vatican.va index, which does not hold the canon's text.
    "https://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html",
])
def test_other_links_are_unchanged(url):
    assert access_fields(_excerpt(url), DOC, content=GS22)["source_url"] == url


def test_the_catechism_and_full_documents_are_unchanged():
    catechism = _excerpt(catechism_pages.COVER_URL, reader_access.CATECHISM_NOTICE)
    assert access_fields(catechism, DOC, "§1127", content=GS22)["source_url"] == \
        catechism_pages.page_url("§1127")
    assert access_fields({}, DOC, content=GS22)["source_url"] is None


def test_a_passage_with_no_content_keeps_the_plain_url():
    assert access_fields(_excerpt(), DOC, chunk_id=CHUNK)["source_url"] == VATICAN


def test_a_listed_miss_keeps_the_plain_url():
    with patch.object(source_links, "_misses", return_value=frozenset({CHUNK})):
        assert access_fields(_excerpt(), DOC, chunk_id=uuid.UUID(CHUNK),
                             content=GS22)["source_url"] == VATICAN
        other = "00000000-0000-0000-0000-0000000000c2"
        assert access_fields(_excerpt(), DOC, chunk_id=other,
                             content=GS22)["source_url"] == GS22_URL


def test_the_generated_miss_list_loads():
    data = json.loads(Path(source_links.__file__).with_name("source_link_misses.json")
                      .read_text())
    assert data["chunk_ids"] == sorted(set(data["chunk_ids"]))
    for chunk_id in data["chunk_ids"]:
        uuid.UUID(chunk_id)
    source_links._misses.cache_clear()
    assert source_links._misses() == frozenset(data["chunk_ids"])


def test_no_miss_list_means_no_misses(tmp_path):
    source_links._misses.cache_clear()
    try:
        with patch.object(source_links, "_MISSES", tmp_path / "absent.json"):
            assert source_links._misses() == frozenset()
    finally:
        source_links._misses.cache_clear()


# ── Every surface that carries source_url ───────────────────────────────────

@pytest.mark.asyncio
async def test_search_chunk_events_link_to_the_passage():
    from app.rag.pipeline import run_search_pipeline
    from app.rag.search_plan import resolve_search_plan
    from app.rag.steps.types import RankedChunk

    chunk = RankedChunk(chunk_id=CHUNK, content=GS22, reference="Gaudium et Spes 22",
                        collection="councils", document_id=DOC,
                        document_title="Gaudium et Spes", author=None, reranker_score=0.9)
    result = MagicMock(chunks=[chunk], outcome="success", total_cost=0.0, context={},
                       collection_outcomes={"councils": "results"}, delivery_outcome=None)

    async def no_explanation(*args, **kwargs):
        return
        yield

    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
         patch("app.rag.pipeline.get_pool", return_value=MagicMock()), \
         patch("app.rag.pipeline.document_access", AsyncMock(return_value=_excerpt())), \
         patch("app.rag.pipeline.stream_explanation", no_explanation):
        events = [e async for e in run_search_pipeline(
            query="incarnate word", collections=["councils"], translation="CPDV", quota=3,
            user_id=None, search_plan=resolve_search_plan(["councils"], 3))]

    [event] = [e for e in events if e["type"] == "chunk"]
    assert event["source"]["source_url"] == GS22_URL


def _client(router):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.deps.auth import get_current_user
    from app.models.auth import AuthUser

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id="u", email=None)
    return TestClient(app)


_ROW = {
    "chunk_id": CHUNK, "content": GS22, "reference": "Gaudium et Spes 22", "position": 4,
    "anchor": "gs-22", "chapter_key": "c1", "unit_label": "§22", "document_id": DOC,
    "collection": "councils", "document_title": "Gaudium et Spes", "author": None,
}


def test_history_restore_links_to_the_passage():
    from app.routes.search import router

    search_id = "00000000-0000-0000-0000-0000000000a1"
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": search_id, "query": "incarnate word",
                                  "filters": {"collections": ["councils"]}, "result_count": 1}
    pool.fetch.return_value = [{"rank": 1, "reranker_score": 0.4, "explanation": None, **_ROW}]
    with patch("app.routes.search.get_pool", return_value=pool), \
         patch("app.routes.search.document_access", AsyncMock(return_value=_excerpt())):
        body = _client(router).get(f"/v1/searches/{search_id}/results").json()
    assert body["results"][0]["source"]["source_url"] == GS22_URL


def test_bookmarks_link_to_the_passage():
    from datetime import datetime, timezone

    from app.routes.bookmarks import router

    pool = AsyncMock()
    pool.fetch.return_value = [{
        "id": "00000000-0000-0000-0000-0000000000b1", "note": None,
        "created_at": datetime(2026, 11, 9, tzinfo=timezone.utc), **_ROW}]
    with patch("app.routes.bookmarks.get_pool", return_value=pool), \
         patch("app.routes.bookmarks.document_access", AsyncMock(return_value=_excerpt())):
        body = _client(router).get("/v1/bookmarks").json()
    assert body["bookmarks"][0]["chunk"]["source"]["source_url"] == GS22_URL


def _doc_row(url=VATICAN, collection="councils"):
    return {"id": uuid.UUID(DOC), "collection": collection, "title": "Gaudium et Spes",
            "author": None, "year": 1965, "translation": None,
            "metadata": {"url": url} if url else {}, "cnt": 40, "outline_ready": True,
            "reader_access": "excerpt"}


def _refusal(pool, anchor):
    with patch("app.routes.documents.get_pool", return_value=pool):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(get_document_reader(DOC, anchor=anchor, chapter=None, user=None))
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "reader_restricted"
    return caught.value.detail["source_url"]


def test_the_reader_refusal_links_to_the_passage_its_anchor_names():
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [_doc_row(), {"id": uuid.UUID(CHUNK), "content": GS22}]
    assert _refusal(pool, "gs-22") == GS22_URL
    assert "anchor=$2" in pool.conn.fetchrow.await_args.args[0]


def test_the_reader_refusal_without_a_passage_links_to_the_document():
    pool = FakePool()
    pool.conn.fetchrow.return_value = _doc_row()
    assert _refusal(pool, None) == VATICAN
    assert pool.conn.fetchrow.await_count == 1

    pool = FakePool()
    pool.conn.fetchrow.side_effect = [_doc_row(), None]   # an anchor that names nothing
    assert _refusal(pool, "gs-999") == VATICAN


def test_the_catechism_refusal_keeps_the_cover():
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [
        {**_doc_row(None, "catechism"), "title": reader_access.CATECHISM_TITLE},
        {"id": uuid.UUID(CHUNK), "content": GS22}]
    assert _refusal(pool, "ccc-1127") == catechism_pages.COVER_URL
