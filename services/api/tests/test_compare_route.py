"""Tests for the /v1/search/compare endpoint and HTML viewer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app


def test_compare_view_returns_html(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    client = TestClient(app)
    response = client.get("/v1/search/compare/view",
                          headers={"x-internal-secret": "test"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text


def test_compare_post_validates_pipeline_names(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    client = TestClient(app)
    response = client.post(
        "/v1/search/compare",
        json={"query": "test", "collections": ["bible"], "quota": 4,
              "pipelines": ["nonexistent_pipeline"]},
        headers={"x-internal-secret": "test"},
    )
    assert response.status_code == 422


def test_compare_view_offers_every_registered_pipeline(monkeypatch):
    """A registry entry nobody can tick is not requestable by name.

    The viewer used to hand-maintain this list, so adding a pipeline left it
    selectable via the API but invisible in the only UI for running comparisons.
    """
    from app.rag.pipelines.registry import PIPELINES

    monkeypatch.setenv("APP_ENV", "development")
    client = TestClient(app)
    response = client.get("/v1/search/compare/view",
                          headers={"x-internal-secret": "test"})

    missing = [name for name in PIPELINES if f'"{name}"' not in response.text]
    assert not missing, f"viewer omits registered pipelines: {missing}"
