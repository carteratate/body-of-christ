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
    # Registered here, not at collection: a module-level `pytestmark` uses it on import.
    config.addinivalue_line("markers", "real_corpus_schema: probe the corpus schema for real")
    config.addinivalue_line(
        "markers", "qdrant_live: needs a real Qdrant server at QDRANT_TEST_URL (skipped without)",
    )


import pytest


@pytest.fixture(autouse=True)
def _forget_searchable_index():
    """Corpus cleanup 2.2b caches whether Qdrant has the `searchable` index; one test's
    answer must not reach the next. Without a client the check answers False."""
    from app.rag import qdrant_client

    qdrant_client.forget_searchable_index()
    yield
    qdrant_client.forget_searchable_index()


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
    "app.routes.reading_progress.document_access",  # the PUT check
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


@pytest.fixture(autouse=True)
def _no_flipbook_check():
    """Catechism page links check the live flipbook's GUID in the background once a day
    (app/catechism_pages.py). Tests start each run as freshly checked and unchanged, so
    none reaches usccb.org; tests of the check itself call it directly."""
    import time

    from app.catechism_pages import _publication

    _publication.republished, _publication.task = False, None
    _publication.checked_at = time.monotonic()
    yield
    _publication.republished, _publication.task = False, None


# Corpus cleanup 2.4a reads `corpus_schema.current()` before building SQL. Fakes answer
# every query alike, so the probe is pinned to "no 0042" (today's SQL and responses)
# unless a test opts in with @pytest.mark.real_corpus_schema or sets the cache itself.
@pytest.fixture(autouse=True)
def _legacy_corpus_schema(request, monkeypatch):
    from app import corpus_schema

    corpus_schema.invalidate()
    if not request.node.get_closest_marker("real_corpus_schema"):
        monkeypatch.setattr(corpus_schema, "_cached", corpus_schema.LEGACY)
        monkeypatch.setattr(corpus_schema, "_cached_at", float("inf"))
    yield
    corpus_schema.invalidate()
