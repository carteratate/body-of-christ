import importlib
import pytest


@pytest.fixture(autouse=True)
def restore_config_after_test():
    """Restore config singleton after each test that reloads it.

    Tests in this file reload the config module with monkeypatched environment
    variables. monkeypatch automatically restores the environment after the test,
    but the config module remains in sys.modules with a stale singleton created
    from fake values. This fixture reloads config one more time after each test
    to restore the singleton for subsequent tests. If the reload fails due to
    missing env vars, that's okay—the important thing is we've cleared the stale
    singleton, allowing the next test to set its own monkeypatched environment.
    """
    yield
    # After the test completes and monkeypatch has restored the environment,
    # reload config to restore the settings singleton.
    import config
    try:
        importlib.reload(config)
    except EnvironmentError:
        # Reload may fail if real env vars are incomplete. That's fine—the
        # stale singleton has been cleared, and the next test will set its own env.
        pass


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
