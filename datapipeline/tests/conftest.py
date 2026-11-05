import sys
import os
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    """Set stub environment variables before any test module imports config.

    config.settings is built once, at first import, so a test module that sets
    a variable after another module has imported config has no effect. Setting
    them here, before collection, makes the suite independent of test order and
    of whether datapipeline/.env exists. setdefault never overwrites a variable
    already exported in the shell.
    """
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("QDRANT_URL", "http://localhost")
    os.environ.setdefault("QDRANT_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")


@pytest.fixture()
def write_collection(monkeypatch):
    """Name QDRANT_WRITE_COLLECTION for a test; returns the name."""
    import writers.qdrant as qd

    monkeypatch.setattr(qd, "settings", replace(qd.settings, QDRANT_WRITE_COLLECTION="chunks-test"))
    return "chunks-test"
