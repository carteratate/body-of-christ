"""Tests for the evaluate endpoint models and helpers."""
import pytest
from pydantic import ValidationError

from app.models.evaluate import EvaluateRequest


def test_evaluate_request_valid():
    req = EvaluateRequest(query="What is the Eucharist?")
    assert req.query == "What is the Eucharist?"


def test_evaluate_request_rejects_empty():
    with pytest.raises(ValidationError):
        EvaluateRequest(query="")


def test_evaluate_request_rejects_too_long():
    with pytest.raises(ValidationError):
        EvaluateRequest(query="x" * 501)


from app.routes.evaluate import _extract_scores


def test_extract_scores_from_clean_json():
    text = '[{"collection":"bible","score":0.9,"explanation":"test"}]'
    result = _extract_scores(text)
    assert len(result) == 1
    assert result[0]["collection"] == "bible"


def test_extract_scores_from_markdown_fenced():
    text = '```json\n[{"collection":"bible","score":0.9,"explanation":"test"}]\n```'
    result = _extract_scores(text)
    assert len(result) == 1


def test_extract_scores_raises_on_no_array():
    with pytest.raises(ValueError, match="No JSON array"):
        _extract_scores("No valid JSON here")


def test_the_prompt_names_the_song_of_songs_by_both_titles():
    """1.4a renames the book "Song of Songs" at the Phase 4 apply, after this deploys (C-24)."""
    from app.routes.evaluate import _EVALUATE_SYSTEM

    assert "Song of Songs (Song of Solomon)" in _EVALUATE_SYSTEM
