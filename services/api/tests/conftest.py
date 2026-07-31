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
