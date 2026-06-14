import asyncio
from unittest.mock import AsyncMock, patch
from app.models.auth import AuthUser
from app.routes.documents import get_document_reader

_DOC = "11111111-1111-1111-1111-111111111111"


def test_reader_returns_chapter_with_neighbors_and_highlight():
    pool = AsyncMock()
    pool.fetchrow.side_effect = [
        # document row
        {"id": _DOC, "collection": "bible", "title": "John", "author": None,
         "year": None, "metadata": None, "cnt": 3},
        # anchor → chapter_key resolution
        {"chapter_key": "john/3"},
    ]
    pool.fetch.side_effect = [
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
