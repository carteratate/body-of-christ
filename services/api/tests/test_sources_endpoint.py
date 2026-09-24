import asyncio
from unittest.mock import patch

from app.db import POOL_ACQUIRE_TIMEOUT_SECONDS
from app.models.auth import AuthUser
from app.routes import sources
from app.routes.sources import get_sources
from tests.fake_pool import FakePool


def test_sources_returns_real_document_ids():
    pool = FakePool()
    pool.conn.fetch.return_value = [
        {"id": "d-john", "collection": "bible", "title": "John", "author": None,
         "year": None, "translation": "WEB-C", "metadata": None, "chunk_count": 21},
        {"id": "d-clement", "collection": "church-fathers",
         "title": "First Epistle to the Corinthians", "author": "Clement of Rome",
         "year": None, "translation": None, "metadata": None, "chunk_count": 65},
    ]
    with (
        patch("app.routes.sources.get_pool", return_value=pool),
        patch.object(sources, "_sources_cache", None),
    ):
        resp = asyncio.run(get_sources(user=AuthUser(user_id="u", email=None)))
    ids = {s.id for s in resp.sources}
    assert ids == {"d-john", "d-clement"}
    cf = [s for s in resp.sources if s.collection == "church-fathers"][0]
    assert ":" not in cf.id   # plain document id, no synthetic "id:author:work"
    assert pool.acquire_timeouts == [POOL_ACQUIRE_TIMEOUT_SECONDS]
    # The precomputed count, falling back to counting only when it is NULL.
    sql = pool.conn.fetch.await_args.args[0]
    assert "COALESCE(d.chunk_count" in sql and "GROUP BY" not in sql
