import asyncio
from unittest.mock import AsyncMock, patch
from app.models.auth import AuthUser
from app.routes.sources import get_sources


def test_sources_returns_real_document_ids():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {"id": "d-john", "collection": "bible", "title": "John", "author": None,
         "year": None, "translation": "WEB-C", "metadata": None, "chunk_count": 21},
        {"id": "d-clement", "collection": "church-fathers",
         "title": "First Epistle to the Corinthians", "author": "Clement of Rome",
         "year": None, "translation": None, "metadata": None, "chunk_count": 65},
    ]
    with patch("app.routes.sources.get_pool", return_value=pool):
        resp = asyncio.run(get_sources(user=AuthUser(user_id="u", email=None)))
    ids = {s.id for s in resp.sources}
    assert ids == {"d-john", "d-clement"}
    cf = [s for s in resp.sources if s.collection == "church-fathers"][0]
    assert ":" not in cf.id   # plain document id, no synthetic "id:author:work"
