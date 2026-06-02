"""Tests for _validate_collections dependency in search routes."""
import pytest
from fastapi import HTTPException

from app.models.search import SearchFilters, SearchRequest
from app.rag.constants import VALID_COLLECTIONS
from app.routes.search import _validate_collections


@pytest.mark.asyncio
async def test_validate_collections_returns_valid_subset():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=["bible", "not-a-collection"], translation="CPDV"),
        quota=3,
    )
    result = await _validate_collections(body)
    assert result == ["bible"]


@pytest.mark.asyncio
async def test_validate_collections_raises_400_when_all_invalid():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=["not-a-collection", "also-invalid"], translation="CPDV"),
        quota=3,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate_collections(body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_collections_raises_400_when_empty():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=[], translation="CPDV"),
        quota=3,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate_collections(body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_collections_accepts_all_valid():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(
            collections=list(VALID_COLLECTIONS),
            translation="CPDV",
        ),
        quota=3,
    )
    result = await _validate_collections(body)
    assert set(result) == set(VALID_COLLECTIONS)
