import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("COHERE_CONCURRENCY", "0"),
        ("LLM_POOL_GLOBAL_CAP", "0"),
        ("RETRIEVAL_K_MIN", "-1"),
        ("CANDIDATE_MULTIPLIER", "0"),
    ],
)
def test_invalid_pipeline_limits_fail_at_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_retrieval_range_fails_at_startup(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_K_MIN", "60")
    monkeypatch.setenv("RETRIEVAL_K_MAX", "10")
    with pytest.raises(ValidationError, match="RETRIEVAL_K_MIN"):
        Settings()
