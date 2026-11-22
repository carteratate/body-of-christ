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


def _most_scopes_and_passages() -> tuple[int, int]:
    """The most scopes and HyDE passage calls one search can have (5.1b.1).

    A plan drops an old key named beside its new one, so each new collection
    contributes either itself or its old keys, whichever is more. Passages: 4 Bible
    genres, one per papal kind a `papal` scope includes, one per other collection.
    (The Bible genre pick finishes before its 4 genre calls start.)"""
    from app.rag.constants import CANONICAL_COLLECTIONS, LEGACY_COLLECTIONS
    from app.rag.steps.hyde_s25 import papal_hyde_kinds

    def passages(key: str) -> int:
        return {"bible": 4, "papal": len(papal_hyde_kinds())}.get(key, 1)

    scopes = calls = 0
    for key in CANONICAL_COLLECTIONS:
        old = [k for k, v in LEGACY_COLLECTIONS.items() if v.canonical == key]
        scopes += max(1, len(old))
        calls += max(passages(key), sum(passages(k) for k in old))
    return scopes, calls


def test_concurrency_defaults_let_a_full_search_run_in_one_round(monkeypatch):
    """Production sets neither variable, so the defaults must cover a full search:
    HyDE every passage call at once, Cohere one call per scope."""
    monkeypatch.delenv("HYDE_LUNA_CONCURRENCY", raising=False)
    monkeypatch.delenv("COHERE_CONCURRENCY", raising=False)
    settings = Settings(_env_file=None)

    scopes, calls = _most_scopes_and_passages()
    assert (scopes, calls) == (10, 13)
    assert settings.hyde_luna_concurrency >= calls
    assert settings.cohere_concurrency >= scopes
