# Shared fixtures and session-wide configuration for pytest.
import os


def pytest_configure(config):
    """Set stub environment variables before any test module is imported.

    The app.config.Settings() runs at import time, so these must be set
    here (in pytest_configure) before collection starts — monkeypatch/setenv
    inside individual tests fires too late.
    """
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    os.environ.setdefault("SUPABASE_PROJECT_URL", "https://test.supabase.co")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    os.environ.setdefault("QDRANT_API_KEY", "test-key")
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    # Disable the Cohere client-side throttle for tests. It is a real 60s sliding
    # window against a live rate limit; leaving it on made the suite wait ~60s once
    # stubbed calls exceeded the per-minute budget. The limiter itself is covered by
    # a dedicated test that sets the limit explicitly.
    os.environ.setdefault("COHERE_MAX_CALLS_PER_MINUTE", "0")


import pytest


@pytest.fixture(autouse=True)
def _clear_cohere_rate_limiter():
    """Reset the module-level Cohere throttle window between tests.

    It is shared module state, so one test's recorded calls would otherwise leak
    into the next and make ordering-dependent failures appear at random.
    """
    from app.rag.steps import rerank_cohere

    rerank_cohere._rate_limiter._calls.clear()
    yield
    rerank_cohere._rate_limiter._calls.clear()


# Every route that annotates passages with reader access (issue #265) makes one extra
# query for it. Fakes elsewhere answer every query with the same rows, so the lookup is
# stubbed to "all full" unless a test opts in with @pytest.mark.real_reader_access.
_READER_ACCESS_SITES = (
    "app.routes.bookmarks.document_access",
    "app.routes.search.document_access",
    "app.routes.reading_progress.document_access",
    "app.rag.pipeline.document_access",
)


def pytest_collection_modifyitems(config, items):
    config.addinivalue_line("markers", "real_reader_access: use the real reader-access lookup")


@pytest.fixture(autouse=True)
def _stub_reader_access(request):
    if request.node.get_closest_marker("real_reader_access"):
        yield
        return
    from unittest.mock import AsyncMock, patch

    patches = [patch(site, AsyncMock(return_value={})) for site in _READER_ACCESS_SITES]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()
