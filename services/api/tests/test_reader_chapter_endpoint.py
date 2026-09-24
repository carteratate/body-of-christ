import asyncio
from unittest.mock import patch

from app.models.auth import AuthUser
from app.routes.documents import get_document_reader
from tests.fake_pool import FakePool

_DOC = "11111111-1111-1111-1111-111111111111"


def test_reader_returns_chapter_with_neighbors_and_highlight():
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [
        # document row, not yet outlined: neighbors are derived from chunks
        {"id": _DOC, "collection": "bible", "title": "John", "author": None,
         "year": None, "metadata": None, "cnt": 3, "outline_ready": False},
        # anchor → chapter_key resolution
        {"chapter_key": "john/3"},
    ]
    pool.conn.fetch.side_effect = [
        # passages in chapter john/3
        [{"id": "p1", "anchor": "john/3/16", "chapter_key": "john/3", "chapter_label": "John 3",
          "unit_label": "16", "reference": "John 3:16", "content": "For God so loved…"}],
        # ordered chapter keys for prev/next
        [{"chapter_key": "john/2"}, {"chapter_key": "john/3"}, {"chapter_key": "john/4"}],
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_reader(
            _DOC, anchor="john/3/16", chapter=None, user=AuthUser(user_id="u", email=None)))
    assert resp.chapter_key == "john/3"
    assert resp.prev_chapter_key == "john/2"
    assert resp.next_chapter_key == "john/4"
    assert resp.highlight_anchor == "john/3/16"
    assert resp.passages[0].unit_label == "16"


def test_reader_takes_neighbors_from_the_outline():
    pool = FakePool()
    pool.conn.fetchrow.side_effect = [
        {"id": _DOC, "collection": "bible", "title": "John", "author": None,
         "year": None, "metadata": None, "cnt": 3, "outline_ready": True},
        # first chapter: ordinal 1
        {"chapter_key": "john/1"},
        # neighbors of john/1
        {"prev_key": None, "next_key": "john/2"},
    ]
    pool.conn.fetch.return_value = [
        {"id": "p1", "anchor": "john/1/1", "chapter_key": "john/1", "chapter_label": "John 1",
         "unit_label": "1", "reference": "John 1:1", "content": "In the beginning"},
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_reader(
            _DOC, anchor=None, chapter=None, user=AuthUser(user_id="u", email=None)))

    assert resp.chapter_key == "john/1"
    assert (resp.prev_chapter_key, resp.next_chapter_key) == (None, "john/2")
    # Only the chapter's passages are read from chunks; no chapter-key scan.
    assert pool.conn.fetch.await_count == 1
