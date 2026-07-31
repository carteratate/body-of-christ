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

from unittest.mock import AsyncMock, patch

import pytest

from app.rag.steps import rerank


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


@pytest.mark.asyncio
async def test_live_search_readiness_checks_database_and_qdrant():
    from app import main

    pool = AsyncMock()
    pool.fetchval.return_value = 1
    qdrant = AsyncMock()
    qdrant.get_collection.return_value = object()
    with (
        patch.object(main, "get_pool", return_value=pool),
        patch.object(main, "get_qdrant_client", return_value=qdrant),
    ):
        live = await main._live_search_readiness()

    assert live == {"database": True, "qdrant": True}
    pool.fetchval.assert_awaited_once_with("SELECT 1")
    qdrant.get_collection.assert_awaited_once_with("chunks")
