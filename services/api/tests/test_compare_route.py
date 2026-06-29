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
