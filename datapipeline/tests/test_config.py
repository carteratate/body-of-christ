import importlib


def test_overlap_defaults_and_per_collection(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("QDRANT_URL", "https://q")
    monkeypatch.setenv("QDRANT_API_KEY", "qk")
    import config
    importlib.reload(config)
    s = config.settings
    assert s.QDRANT_URL == "https://q"
    assert s.MAX_PASSAGE_CHARS == 3500
    # per-collection overlap falls back to the default tuple when unset
    assert s.overlap_for("bible") == s.PER_COLLECTION_OVERLAP["bible"]
    assert s.overlap_for("unknown-collection") == s.DEFAULT_OVERLAP
    assert isinstance(s.overlap_for("summa"), tuple) and len(s.overlap_for("summa")) == 2
