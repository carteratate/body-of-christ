import importlib
import pytest


def test_embedding_dims_is_3072(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("QDRANT_URL", "https://q")
    monkeypatch.setenv("QDRANT_API_KEY", "qk")
    import config
    importlib.reload(config)
    assert config.settings.EMBEDDING_DIMS == 3072


def test_enrich_model_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("QDRANT_URL", "https://q")
    monkeypatch.setenv("QDRANT_API_KEY", "qk")
    import config
    importlib.reload(config)
    assert config.settings.ANTHROPIC_ENRICH_MODEL == "claude-opus-4-8"


def test_require_anthropic_raises_when_missing(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("QDRANT_URL", "https://q")
    monkeypatch.setenv("QDRANT_API_KEY", "qk")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import config
    reloaded = importlib.reload(config)
    with pytest.raises(EnvironmentError):
        reloaded.settings.require_anthropic()


def test_cost_constants_present(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("QDRANT_URL", "https://q")
    monkeypatch.setenv("QDRANT_API_KEY", "qk")
    import config
    importlib.reload(config)
    assert config.settings.OPUS_INPUT_COST_PER_M == 5.0
    assert config.settings.OPUS_OUTPUT_COST_PER_M == 25.0
    assert config.settings.EMBED_COST_PER_M == 0.13
