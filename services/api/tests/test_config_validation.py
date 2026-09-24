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


def test_concurrency_defaults_let_a_full_search_run_in_one_round(monkeypatch):
    """Production sets neither variable, so the defaults must cover a full search.

    HyDE must let every passage call of a full search run at once: 4 Bible genres
    plus one per other collection. (The Bible genre pick finishes before its 4
    genre calls start, so it never needs a 14th slot.) Cohere must cover one call
    per collection.
    """
    from app.rag.constants import VALID_COLLECTIONS

    monkeypatch.delenv("HYDE_LUNA_CONCURRENCY", raising=False)
    monkeypatch.delenv("COHERE_CONCURRENCY", raising=False)
    settings = Settings(_env_file=None)

    assert settings.hyde_luna_concurrency >= 4 + (len(VALID_COLLECTIONS) - 1)
    assert settings.cohere_concurrency >= len(VALID_COLLECTIONS)
