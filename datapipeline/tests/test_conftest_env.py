from config import settings


def test_optional_anthropic_key_is_stubbed_before_config_import():
    # Without conftest's pytest_configure, whichever test module imports config
    # first decides this value, and the enrichment tests fail in full-suite order.
    assert settings.ANTHROPIC_API_KEY is not None
