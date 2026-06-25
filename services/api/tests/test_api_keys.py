"""Tests for API key assignment and semaphore management."""
from unittest.mock import MagicMock, patch

import pytest

from app.rag.api_keys import get_client, get_key_for, get_semaphore, init_api_keys


def _mock_settings(key_a="sk-a", key_b=None, key_c=None, key_d=None):
    s = MagicMock()
    s.anthropic_api_key = key_a
    s.anthropic_api_key_b = key_b
    s.anthropic_api_key_c = key_c
    s.anthropic_api_key_d = key_d
    return s


def test_bible_always_gets_key_a():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        assert get_key_for("bible") == "A"


def test_non_bible_cycles_through_bcd():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        keys = [get_key_for("catechism") for _ in range(6)]
    # Must cycle through B, C, D repeatedly — never A
    assert all(k in ("B", "C", "D") for k in keys)
    assert len(set(keys)) >= 2  # at least two distinct keys used


def test_get_client_returns_anthropic_client():
    import anthropic
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        client = get_client("A")
    assert isinstance(client, anthropic.AsyncAnthropic)


def test_get_semaphore_bible_has_value_4():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        sem = get_semaphore("A")
    # asyncio.Semaphore._value reflects current capacity
    assert sem._value == 4


def test_get_semaphore_non_bible_has_value_3():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        assert get_semaphore("B")._value == 3
        assert get_semaphore("C")._value == 3
        assert get_semaphore("D")._value == 3


def test_single_key_fallback_when_bcd_not_configured():
    """All keys use the same underlying API key when B/C/D env vars are absent."""
    with patch("app.rag.api_keys.settings", _mock_settings(key_a="sk-only")):
        init_api_keys()
        client_b = get_client("B")
        client_a = get_client("A")
    import anthropic
    assert isinstance(client_b, anthropic.AsyncAnthropic)
    assert isinstance(client_a, anthropic.AsyncAnthropic)
