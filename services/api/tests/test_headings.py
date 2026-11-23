"""Headings marked inside a passage (issue #445), carried to every surface that shows
it: live search events, history restore, bookmarks and the reader."""
import asyncio
from unittest.mock import patch

import pytest

from app.headings import fetch_headings, validated
from app.models.auth import AuthUser
from app.routes.documents import get_document_reader
from tests.fake_pool import FakePool
from tests.test_footnotes import (CONTENT, _bookmarks, _ccc, _events, _id, _notes_pool,
                                  _restore, _route_pool, _row, _summa)

MARKED = "SECTION 1 The Avoidance of War\n\nEven though recent wars ..."
MARKS = [{"at": 0, "end": 30, "role": "heading", "level": 2}]


def test_validated_keeps_well_formed_marks_in_reading_order():
    content = "Article 1\n\nTHE REVELATION OF GOD\n\n\"Thou shalt\"\n\nBody."
    value = [
        {"at": 33, "end": 46, "role": "epigraph", "level": None},
        {"at": 0, "end": 9, "role": "heading", "level": 1, "pairs_next": True,
         "chapter_title": True, "extra": "ignored"},
        {"at": 11, "end": 32, "role": "heading", "level": 1, "pairs_next": False},
    ]
    assert validated(value, content) == [
        {"at": 0, "end": 9, "role": "heading", "level": 1, "pairs_next": True,
         "chapter_title": True},
        {"at": 11, "end": 32, "role": "heading", "level": 1},
        {"at": 33, "end": 46, "role": "epigraph"},
    ]
    assert validated(None, content) == []


@pytest.mark.parametrize("value", [
    {"at": 0},
    ["x"],
    [{"at": 0, "end": 99, "role": "heading", "level": 1}],          # past the content
    [{"at": 5, "end": 5, "role": "heading", "level": 1}],           # empty
    [{"at": 0, "end": 5, "role": "heading", "level": 4}],
    [{"at": 0, "end": 5, "role": "heading"}],
    [{"at": 0, "end": 5, "role": "caption", "level": 1}],
    [{"at": True, "end": 5, "role": "heading", "level": 1}],
    [{"at": 0, "end": 6, "role": "heading", "level": 1},
     {"at": 5, "end": 9, "role": "heading", "level": 2}],          # overlapping
])
def test_validated_refuses_a_malformed_value(value):
    assert validated(value, MARKED) is None


def _marks_pool(stored, error=None):
    pool = _notes_pool()

    async def fetch(sql, *args):
        if "metadata->'headings'" not in sql:
            return []
        if error is not None:
            raise error
        return [{"id": i, "headings": stored[i]} for i in args[0] if i in stored]

    pool.fetch.side_effect = fetch
    return pool


@pytest.mark.asyncio
async def test_fetch_headings_falls_back_to_none():
    pool = _marks_pool({_id(1): MARKS, _id(2): "bad"})
    assert await fetch_headings(pool, [(_id(1), MARKED), (_id(2), MARKED), (_id(3), "x")]) == {
        _id(1): MARKS, _id(2): [], _id(3): []}
    failing = _marks_pool({}, error=RuntimeError("db down"))
    assert await fetch_headings(failing, [(_id(1), MARKED)]) == {_id(1): []}
    assert await fetch_headings(None, [(_id(1), MARKED)]) == {_id(1): []}
    assert await fetch_headings(pool, []) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", ["00000000-0000-0000-0000-000000000001", None],
                         ids=["authenticated", "guest"])
async def test_a_chunk_event_carries_headings_only_when_its_passage_has_some(user_id):
    first, second = _ccc(1), _summa(2)
    first.content = MARKED
    events = await _events([first, second], _marks_pool({_id(1): MARKS}), user_id)
    chunks = {e["chunk_id"]: e for e in events if e["type"] == "chunk"}
    assert chunks[_id(1)]["headings"] == MARKS
    assert chunks[_id(1)]["content"] == MARKED       # marks never change the text
    assert "headings" not in chunks[_id(2)]


def _marked_route_pool(content_rows, stored, *, fetchrow=None):
    pool = _route_pool(content_rows, {}, fetchrow=fetchrow)
    plain = pool.fetch.side_effect

    async def fetch(sql, *args):
        if "metadata->'headings'" in sql:
            return [{"id": i, "headings": stored[i]} for i in args[0] if i in stored]
        return await plain(sql, *args)

    pool.fetch.side_effect = fetch
    return pool


@pytest.mark.parametrize("load", [_restore, _bookmarks], ids=["history", "bookmarks"])
def test_saved_passages_carry_their_headings(load):
    marks = [{"at": 0, "end": 3, "role": "heading", "level": 3}]
    with patch("tests.test_footnotes._route_pool", _marked_route_pool):
        results = load([_row(1), _row(2)], {_id(1): marks})
    assert results[0]["headings"] == [{**marks[0], "pairs_next": False,
                                       "chapter_title": False}]
    assert results[0]["content"] == CONTENT
    assert results[1]["headings"] == []


def _reader(passage_row):
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [
        {"id": "11111111-1111-1111-1111-111111111111", "collection": "councils",
         "title": "Gaudium et Spes", "author": None, "year": None, "metadata": None,
         "cnt": 1, "reader_access": "full", "outline_ready": False},
    ]
    pool.conn.fetch.side_effect = [[passage_row], [{"chapter_key": "c5"}]]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_reader(
            "11111111-1111-1111-1111-111111111111", anchor=None, chapter="c5",
            user=AuthUser(user_id="u", email=None)))
    sql = pool.conn.fetch.await_args_list[0].args[0]
    assert "metadata->'headings' AS headings" in sql
    return resp.passages[0]


@pytest.mark.parametrize("stored,expected", [
    (MARKS, MARKS),
    (None, []),
    ([{"at": 0, "end": 999, "role": "heading", "level": 2}], []),
])
def test_reader_passages_carry_their_headings(stored, expected):
    passage = _reader({"id": "p1", "anchor": "gs/79", "chapter_key": "c5",
                       "chapter_label": "Chapter V", "unit_label": "§79",
                       "reference": "GS 79", "content": MARKED, "headings": stored})
    assert [h.model_dump(exclude_defaults=True) for h in passage.headings] == expected
