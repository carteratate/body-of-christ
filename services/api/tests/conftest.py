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
