"""Unit tests for expand_query."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.query_expand import expand_query


@pytest.mark.asyncio
async def test_expand_query_returns_two_variants():
    """On success, returns exactly the 2 strings from the model response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='["Holy Ghost", "divine mercy"]')]

    with patch("app.rag.query_expand._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await expand_query("What is the Holy Spirit?")

    assert result == ["Holy Ghost", "divine mercy"]


@pytest.mark.asyncio
async def test_expand_query_returns_empty_when_not_initialized():
    """Returns empty list (never raises) when the client has not been initialised."""
    with patch("app.rag.query_expand._client", None):
        result = await expand_query("test query")

    assert result == []


@pytest.mark.asyncio
async def test_expand_query_returns_empty_on_api_failure():
    """Returns empty list (never raises) when the Anthropic API call fails."""
    with patch("app.rag.query_expand._client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=Exception("network error"))
        result = await expand_query("test query")

    assert result == []


@pytest.mark.asyncio
async def test_expand_query_caps_at_two():
    """Never returns more than 2 strings even if the model returns extras."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='["a", "b", "c", "d"]')]

    with patch("app.rag.query_expand._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await expand_query("test")

    assert len(result) <= 2
