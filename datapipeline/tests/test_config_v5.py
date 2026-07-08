import os

# config.py constructs its module-level singleton at import time via
# _require_env(), which raises if these vars are absent. The real
# datapipeline/.env does not define QDRANT_URL/QDRANT_API_KEY, so we need
# placeholders present before the first `import config` in this process
# (matching the convention used by other test files, e.g.
# tests/test_apostolic_exhortations.py). setdefault() never overwrites a
# real value and is a one-time bootstrap, not per-test monkeypatching.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import pytest

from config import Settings


def _base_kwargs(**overrides):
    kwargs = dict(
        DATABASE_URL="postgres://x",
        OPENAI_API_KEY="sk-x",
        QDRANT_URL="https://q",
        QDRANT_API_KEY="qk",
    )
    kwargs.update(overrides)
    return kwargs


def test_embedding_dims_is_3072():
    s = Settings(**_base_kwargs())
    assert s.EMBEDDING_DIMS == 3072


def test_enrich_model_default():
    s = Settings(**_base_kwargs())
    assert s.ANTHROPIC_ENRICH_MODEL == "claude-opus-4-8"


def test_require_anthropic_raises_when_missing():
    s = Settings(**_base_kwargs(ANTHROPIC_API_KEY=None))
    with pytest.raises(EnvironmentError):
        s.require_anthropic()


def test_cost_constants_present():
    s = Settings(**_base_kwargs())
    assert s.OPUS_INPUT_COST_PER_M == 5.0
    assert s.OPUS_OUTPUT_COST_PER_M == 25.0
    assert s.EMBED_COST_PER_M == 0.13
