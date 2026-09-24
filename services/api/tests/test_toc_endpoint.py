import asyncio
from unittest.mock import patch

from app.models.auth import AuthUser
from app.routes.documents import get_document_toc
from tests.fake_pool import FakePool

_DOC = "11111111-1111-1111-1111-111111111111"


def _doc_row(outline_ready):
    return {"id": _DOC, "collection": "bible", "title": "John", "author": None,
            "year": None, "translation": "WEB-C", "metadata": None, "cnt": 2,
            "outline_ready": outline_ready}


def _toc(outline_ready):
    pool = FakePool()
    pool.conn.fetchrow.return_value = _doc_row(outline_ready)
    pool.conn.fetch.return_value = [
        {"chapter_key": "john/1", "chapter_label": "John 1"},
        {"chapter_key": "john/2", "chapter_label": "John 2"},
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_toc(_DOC, user=AuthUser(user_id="u", email=None)))
    return resp, pool.conn.fetch.await_args.args[0]


def test_toc_returns_ordered_chapters():
    resp, _ = _toc(outline_ready=True)
    assert [c.chapter_label for c in resp.chapters] == ["John 1", "John 2"]
    assert resp.document.title == "John"
    assert resp.document.translation == "WEB-C"


def test_toc_reads_the_outline_when_it_is_built_and_chunks_otherwise():
    _, outline_sql = _toc(outline_ready=True)
    _, legacy_sql = _toc(outline_ready=False)
    assert "FROM document_chapters" in outline_sql
    assert "FROM chunks" in legacy_sql and "GROUP BY" in legacy_sql
