import asyncio
from unittest.mock import AsyncMock, patch
from app.models.auth import AuthUser
from app.routes.documents import get_document_toc

_DOC = "11111111-1111-1111-1111-111111111111"


def test_toc_returns_ordered_chapters():
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": _DOC, "collection": "bible", "title": "John",
                                  "author": None, "year": None, "translation": "WEB-C",
                                  "metadata": None, "cnt": 2}
    pool.fetch.return_value = [
        {"chapter_key": "john/1", "chapter_label": "John 1"},
        {"chapter_key": "john/2", "chapter_label": "John 2"},
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_toc(_DOC, user=AuthUser(user_id="u", email=None)))
    assert [c.chapter_label for c in resp.chapters] == ["John 1", "John 2"]
    assert resp.document.title == "John"
    assert resp.document.translation == "WEB-C"
