"""Every rerank provider must be ready after the real startup sequence.

A provider whose client was never initialised fails SILENTLY: `is_ready()` returns
False and both rerank shapes fall back to upstream order without raising, so every
search quietly degrades while looking healthy. That is exactly what happened when a
second Anthropic client was introduced in `llm_rerank/` while `main.py` only
initialised the one in `rerank_haiku` — 264 tests passed because each of them patched
the client directly instead of exercising the startup wiring.

These tests drive `app.main.lifespan` and then assert against the provider registry,
so a provider added without an init call fails here rather than in production.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from qdrant_client.models import AliasDescription, CollectionsAliasesResponse

from app.rag.steps import hyde_luna, rerank


@pytest.mark.asyncio
async def test_every_registered_provider_is_ready_after_lifespan():
    from app.main import app, lifespan

    # Only the network-touching bits are stubbed; every init_*/close_* call in the
    # lifespan body runs for real, which is the point of the test.
    with (
        patch("app.main.init_pool", new=AsyncMock()),
        patch("app.main.close_pool", new=AsyncMock()),
        patch("app.main.get_pool", return_value=None),
    ):
        async with lifespan(app):
            assert hyde_luna.is_ready()
            not_ready = [
                name for name, provider in rerank.PROVIDERS.items()
                if not provider.is_ready()
            ]
            assert not not_ready, (
                f"provider(s) {not_ready} not initialised by main.lifespan — every "
                f"rerank using them would silently fall back to upstream order"
            )


@pytest.mark.asyncio
async def test_providers_are_closed_after_lifespan_exits():
    """A client left open after shutdown leaks its connection pool."""
    from app.main import app, lifespan

    with (
        patch("app.main.init_pool", new=AsyncMock()),
        patch("app.main.close_pool", new=AsyncMock()),
        patch("app.main.get_pool", return_value=None),
    ):
        async with lifespan(app):
            pass

    still_open = [
        name for name, provider in rerank.PROVIDERS.items() if provider.is_ready()
    ]
    assert not hyde_luna.is_ready()
    assert not still_open, f"provider(s) {still_open} still hold a client after shutdown"


def test_evaluate_route_shares_the_haiku_client_rather_than_opening_its_own():
    """routes/evaluate.py reads `rerank_haiku._client` directly. Keeping one client
    per API is what prevents 'which one did I initialise?' from recurring."""
    import app.rag.steps.rerank_haiku as rerank_haiku

    assert rerank.PROVIDERS["haiku"] is rerank_haiku.PROVIDER


def test_search_readiness_covers_every_production_dependency():
    from app import main

    with (
        patch.object(main, "get_pool", return_value=object()),
        patch.object(main, "embed_is_ready", return_value=True),
        patch.object(main, "hyde_is_ready", return_value=True),
        patch.object(main, "hyde_luna_is_ready", return_value=True),
        patch.object(main, "get_qdrant_client", return_value=object()),
        patch.object(main, "cohere_is_ready", return_value=True),
        patch.object(main.luna_provider, "is_ready", return_value=True),
    ):
        readiness = main._search_readiness()

    assert readiness == {
        "database": True,
        "embeddings": True,
        "hyde": True,
        "qdrant": True,
        "cohere": True,
        "terminal_reranker": True,
    }


def test_search_readiness_requires_luna_for_genre_selection():
    from app import main

    with (
        patch.object(main.settings, "hyde_passage_provider", "haiku"),
        patch.object(main.settings, "hyde_genre_provider", "luna"),
        patch.object(main, "hyde_is_ready", return_value=True),
        patch.object(main, "hyde_luna_is_ready", return_value=False),
    ):
        assert main._search_readiness()["hyde"] is False


@pytest.mark.asyncio
async def test_live_search_readiness_checks_database_and_qdrant():
    from app import main

    pool = AsyncMock()
    pool.fetchval.return_value = 1
    qdrant = AsyncMock()
    qdrant.get_aliases.return_value = CollectionsAliasesResponse(aliases=[])
    qdrant.get_collection.return_value = object()
    with (
        patch.object(main, "get_pool", return_value=pool),
        patch.object(main, "get_qdrant_client", return_value=qdrant),
    ):
        live, read = await main._live_search_readiness()

    assert live == {"database": True, "qdrant": True}
    assert read == {"qdrant_read": "chunks", "qdrant_target": "chunks",
                    "qdrant_searchable_filter": False}
    pool.fetchval.assert_awaited_once_with("SELECT 1")
    qdrant.get_collection.assert_awaited_once_with("chunks")


@pytest.mark.asyncio
async def test_health_reports_alias_and_target(monkeypatch):
    """With `QDRANT_READ_COLLECTION=chunks_live`, /health/search names the alias and the
    collection it points at, and checks that collection (corpus cleanup 2.2b)."""
    from app import main

    monkeypatch.setattr(main.settings, "qdrant_read_collection", "chunks_live")
    pool = AsyncMock()
    pool.fetchval.return_value = 1
    qdrant = AsyncMock()
    qdrant.get_aliases.return_value = CollectionsAliasesResponse(aliases=[
        AliasDescription(alias_name="other", collection_name="elsewhere"),
        AliasDescription(alias_name="chunks_live", collection_name="chunks"),
    ])
    qdrant.get_collection.return_value = object()
    with (
        patch.object(main, "get_pool", return_value=pool),
        patch.object(main, "get_qdrant_client", return_value=qdrant),
        patch.object(main, "_search_readiness", return_value={"qdrant": True}),
    ):
        response = await main.health_search()

    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["qdrant_read"] == "chunks_live"
    assert body["qdrant_target"] == "chunks"
    qdrant.get_collection.assert_awaited_once_with("chunks")


@pytest.mark.asyncio
async def test_health_reports_no_target_when_qdrant_fails():
    from app import main

    qdrant = AsyncMock()
    qdrant.get_aliases.side_effect = OSError("down")
    with (
        patch.object(main, "get_pool", return_value=None),
        patch.object(main, "get_qdrant_client", return_value=qdrant),
    ):
        live, read = await main._live_search_readiness()

    assert live["qdrant"] is False
    assert read == {"qdrant_read": "chunks", "qdrant_target": None,
                    "qdrant_searchable_filter": None}
