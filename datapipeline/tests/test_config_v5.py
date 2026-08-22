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

from config import Settings, _env_bool


def _base_kwargs(**overrides):
    kwargs = dict(
        DATABASE_URL="postgres://x",
        OPENAI_API_KEY="sk-x",
        QDRANT_URL="https://q",
        QDRANT_API_KEY="qk",
    )
    kwargs.update(overrides)
    return kwargs


def test_the_default_format_is_the_one_that_is_deployed():
    """A writer configured for a shape the collection does not have cannot write to it —
    which is exactly how the pipeline sat unusable while the app served 1536 unnamed."""
    s = Settings(**_base_kwargs())
    assert s.QDRANT_FORMAT == "live"
    assert s.EMBEDDING_DIMS == 1536
    assert s.VECTOR_IS_NAMED is False


def test_v5_dimensions_stay_reachable_by_selecting_the_format():
    s = Settings(**_base_kwargs())
    s = Settings(**_base_kwargs(QDRANT_FORMAT="v5"))
    assert s.EMBEDDING_DIMS == 3072
    assert s.VECTOR_IS_NAMED is True


def test_enrich_model_default():
    s = Settings(**_base_kwargs())
    assert s.ANTHROPIC_ENRICH_MODEL == "claude-opus-5"


def test_require_anthropic_raises_when_missing():
    s = Settings(**_base_kwargs(ANTHROPIC_API_KEY=None))
    with pytest.raises(EnvironmentError):
        s.require_anthropic()


def test_cost_constants_present():
    s = Settings(**_base_kwargs())
    assert s.OPUS_INPUT_COST_PER_M == 5.0
    assert s.OPUS_OUTPUT_COST_PER_M == 25.0
    assert s.EMBED_COST_PER_M == 0.13


def test_per_pass_temperature_defaults():
    s = Settings(**_base_kwargs())
    # Pass 1 must stay None: Opus 5 removed `temperature`, so sending it at all
    # is a 400, and client.py omits the parameter entirely when it is None.
    assert s.PASS1_TEMPERATURE is None
    assert s.PASS2_TEMPERATURE == 0.0
    assert s.PASS3_TEMPERATURE == 0.3


def test_pass1_thinking_defaults_off_at_default_effort():
    s = Settings(**_base_kwargs())
    # Opus 5 thinks by default and max_tokens caps thinking + output together,
    # so Pass 1 disables it to protect a 4096-token tool payload. Disabling is
    # only legal at effort `high` or below, and None means "omit" (API default
    # `high`) — so these two defaults are only valid together.
    assert s.PASS1_THINKING is False
    assert s.PASS1_EFFORT is None


def test_pilot_mode_defaults_false():
    s = Settings(**_base_kwargs())
    assert s.PILOT_MODE is False


def test_pilot_mode_can_be_set_true():
    s = Settings(**_base_kwargs(PILOT_MODE=True))
    assert s.PILOT_MODE is True


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("True", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("", False),
])
def test_env_bool_parses_common_truthy_falsy_strings(value, expected):
    os.environ["_TEST_ENV_BOOL"] = value
    try:
        assert _env_bool("_TEST_ENV_BOOL", False) is expected
    finally:
        del os.environ["_TEST_ENV_BOOL"]


def test_env_bool_uses_default_when_unset():
    os.environ.pop("_TEST_ENV_BOOL_UNSET", None)
    assert _env_bool("_TEST_ENV_BOOL_UNSET", True) is True
    assert _env_bool("_TEST_ENV_BOOL_UNSET", False) is False
