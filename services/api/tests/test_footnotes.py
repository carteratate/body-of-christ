"""A Catechism passage's footnotes, carried with it to every surface (issue #279)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.footnotes import fetch_footnotes, has_footnotes
from app.models.auth import AuthUser
from app.rag.pipeline import run_search_pipeline
from app.rag.search_plan import resolve_search_plan
from app.rag.steps.types import RankedChunk
from app.reader_access import CATECHISM_TITLE

USER_ID = "00000000-0000-0000-0000-000000000001"
SEARCH_ID = "00000000-0000-0000-0000-0000000000aa"
CCC_DOC = "00000000-0000-0000-0000-0000000000d1"
SUMMA_DOC = "00000000-0000-0000-0000-0000000000d2"
CONTENT = "The death penalty is inadmissible."
NOTES = [{"n": 68, "text": "Francis, Address, 11 October 2017.", "at": len(CONTENT)}]


def _id(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _notes_pool(stored: dict[str, object] | None = None, error: Exception | None = None):
    """A pool answering the footnotes query from `stored`; other queries get []."""
    stored = stored or {}

    async def fetch(sql, *args):
        if "metadata->'footnotes'" not in sql:
            return []
        if error is not None:
            raise error
        return [{"id": i, "footnotes": stored[i]} for i in args[0] if i in stored]

    conn = MagicMock(execute=AsyncMock(), executemany=AsyncMock())
    conn.transaction.return_value = AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.fetch = AsyncMock(side_effect=fetch)
    pool.acquire.return_value = AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False),
    )
    return pool


# ── The reader ───────────────────────────────────────────────────────────────

def test_only_the_catechism_document_has_footnotes_looked_up():
    assert has_footnotes("catechism", CATECHISM_TITLE)
    assert not has_footnotes("catechism", "Compendium of the Catechism")
    assert not has_footnotes("summa", CATECHISM_TITLE)


@pytest.mark.asyncio
async def test_notes_are_read_from_metadata():
    pool = _notes_pool({_id(1): NOTES})
    assert await fetch_footnotes(pool, [(_id(1), CONTENT)]) == {_id(1): NOTES}


@pytest.mark.asyncio
async def test_missing_notes_give_none():
    pool = _notes_pool({_id(1): None})
    # _id(2) has no chunks row at all (a stale id).
    assert await fetch_footnotes(pool, [(_id(1), CONTENT), (_id(2), CONTENT)]) == {
        _id(1): [], _id(2): [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [
    "not a list",
    {"n": 1},
    ["note"],
    [{"n": 1, "text": "note"}],
    [{"n": 1, "text": "note", "at": len(CONTENT) + 1}],
    [{"n": 1, "text": "note", "at": -1}],
    [{"n": 1, "text": " ", "at": 0}],
    [{"n": True, "text": "note", "at": 0}],
    [{"n": 0, "text": "note", "at": 0}],
])
async def test_malformed_or_out_of_range_notes_are_not_shown(value):
    pool = _notes_pool({_id(1): value})
    assert await fetch_footnotes(pool, [(_id(1), CONTENT)]) == {_id(1): []}


@pytest.mark.asyncio
async def test_a_failed_query_gives_every_passage_no_notes():
    pool = _notes_pool(error=RuntimeError("db down"))
    assert await fetch_footnotes(pool, [(_id(1), CONTENT), (_id(2), CONTENT)]) == {
        _id(1): [], _id(2): [],
    }
    assert await fetch_footnotes(None, [(_id(1), CONTENT)]) == {_id(1): []}


@pytest.mark.asyncio
async def test_no_passages_makes_no_query():
    pool = _notes_pool()
    assert await fetch_footnotes(pool, []) == {}
    pool.fetch.assert_not_awaited()


# ── Live search events ───────────────────────────────────────────────────────

def _ccc(n: int) -> RankedChunk:
    return RankedChunk(
        chunk_id=_id(n), content=CONTENT, reference=f"CCC {n}", collection="catechism",
        document_id=CCC_DOC, document_title=CATECHISM_TITLE, author="Catholic Church",
        reranker_score=0.9,
    )


def _summa(n: int) -> RankedChunk:
    return RankedChunk(
        chunk_id=_id(n), content="It would seem that...", reference="ST I q.1 a.1",
        collection="summa", document_id=SUMMA_DOC, document_title="Summa Theologiae",
        author="Thomas Aquinas", reranker_score=0.8,
    )


async def _no_explanation(*args, **kwargs):
    return
    yield


async def _events(chunks, pool, user_id):
    result = MagicMock()
    result.chunks = chunks
    result.outcome = "success"
    result.collection_outcomes = {"catechism": "results"}
    result.delivery_outcome = "complete"
    result.total_cost = 0.0
    result.context = {}
    with patch("app.rag.pipeline.run_pipeline", AsyncMock(return_value=result)), \
            patch("app.rag.pipeline.get_pool", return_value=pool), \
            patch("app.rag.pipeline.stream_explanation", _no_explanation):
        return [
            event async for event in run_search_pipeline(
                query="the death penalty", collections=["catechism", "summa"],
                translation="CPDV", quota=4, user_id=user_id,
                search_plan=resolve_search_plan(["catechism", "summa"], 4),
            )
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [USER_ID, None], ids=["authenticated", "guest"])
async def test_each_chunk_event_carries_its_passages_footnotes(user_id):
    pool = _notes_pool({_id(1): NOTES, _id(3): None})
    events = await _events([_ccc(1), _summa(2), _ccc(3)], pool, user_id)

    chunk_events = {e["chunk_id"]: e for e in events if e["type"] == "chunk"}
    assert chunk_events[_id(1)]["footnotes"] == NOTES
    assert chunk_events[_id(2)]["footnotes"] == []
    assert chunk_events[_id(3)]["footnotes"] == []
    assert chunk_events[_id(1)]["content"] == CONTENT  # notes never enter the text
    # Only the Catechism passages are looked up.
    notes_call = next(
        call for call in pool.fetch.await_args_list
        if "metadata->'footnotes'" in call.args[0]
    )
    assert notes_call.args[1] == [_id(1), _id(3)]


@pytest.mark.asyncio
async def test_a_failed_footnote_query_still_completes_the_search():
    pool = _notes_pool(error=RuntimeError("db down"))
    events = await _events([_ccc(1)], pool, None)

    chunk = next(e for e in events if e["type"] == "chunk")
    assert chunk["footnotes"] == []
    assert any(e["type"] == "done" for e in events)
    assert not any(e["type"] == "error" for e in events)


# ── History restore and bookmarks ────────────────────────────────────────────

def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id=USER_ID)
    return TestClient(app)


def _row(n: int, collection="catechism", title=CATECHISM_TITLE):
    return {
        "chunk_id": _id(n), "content": CONTENT, "reference": f"CCC {n}",
        "anchor": f"ccc/{n}", "chapter_key": None, "unit_label": None,
        "document_id": CCC_DOC if collection == "catechism" else SUMMA_DOC,
        "collection": collection, "document_title": title, "author": None,
    }


def _route_pool(content_rows, stored, *, fetchrow=None):
    async def fetch(sql, *args):
        if "metadata->'footnotes'" in sql:
            return [{"id": i, "footnotes": stored[i]} for i in args[0] if i in stored]
        if "FROM retrievals r" in sql or "FROM bookmarks b" in sql:
            return content_rows
        return []

    pool = MagicMock()
    pool.fetch = AsyncMock(side_effect=fetch)
    pool.fetchrow = AsyncMock(return_value=fetchrow)
    return pool


def _restore(content_rows, stored):
    from app.routes.search import router

    rows = [
        {**row, "rank": i, "reranker_score": 0.9, "explanation": None, "position": i}
        for i, row in enumerate(content_rows, start=1)
    ]
    search = {"id": SEARCH_ID, "query": "q", "filters": {"quota": 4}, "result_count": len(rows)}
    with patch("app.routes.search.get_pool", return_value=_route_pool(rows, stored, fetchrow=search)):
        response = _client(router).get(f"/v1/searches/{SEARCH_ID}/results")
    assert response.status_code == 200
    return response.json()["results"]


def _bookmarks(content_rows, stored):
    from app.routes.bookmarks import router

    rows = [
        {**row, "id": _id(500 + i), "created_at": datetime(2026, 10, 28, tzinfo=timezone.utc),
         "note": None}
        for i, row in enumerate(content_rows)
    ]
    with patch("app.routes.bookmarks.get_pool", return_value=_route_pool(rows, stored)):
        response = _client(router).get("/v1/bookmarks")
    assert response.status_code == 200
    return [b["chunk"] for b in response.json()["bookmarks"]]


@pytest.mark.parametrize("load", [_restore, _bookmarks], ids=["history", "bookmarks"])
def test_saved_passages_carry_their_footnotes(load):
    results = load([_row(1), _row(2, "summa", "Summa Theologiae")], {_id(1): NOTES})
    assert results[0]["footnotes"] == NOTES
    assert results[0]["content"] == CONTENT
    assert results[1]["footnotes"] == []


@pytest.mark.parametrize("load", [_restore, _bookmarks], ids=["history", "bookmarks"])
def test_a_malformed_footnotes_value_does_not_fail_the_response(load):
    results = load([_row(1), _row(2)], {_id(1): {"bad": "shape"}})
    assert [r["footnotes"] for r in results] == [[], []]
