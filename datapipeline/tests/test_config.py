import os

# See tests/test_config_v5.py for why these setdefault() calls exist: config.py
# builds its module-level singleton at import time and the real
# datapipeline/.env lacks QDRANT_URL/QDRANT_API_KEY.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

from config import Settings


def test_overlap_defaults_and_per_collection():
    s = Settings(
        DATABASE_URL="postgres://x",
        OPENAI_API_KEY="sk-x",
        QDRANT_URL="https://q",
        QDRANT_API_KEY="qk",
    )
    assert s.QDRANT_URL == "https://q"
    assert s.MAX_PASSAGE_CHARS == 3500
    # per-collection overlap falls back to the default tuple when unset
    assert s.overlap_for("bible") == s.PER_COLLECTION_OVERLAP["bible"]
    assert s.overlap_for("unknown-collection") == s.DEFAULT_OVERLAP
    assert isinstance(s.overlap_for("summa"), tuple) and len(s.overlap_for("summa")) == 2
