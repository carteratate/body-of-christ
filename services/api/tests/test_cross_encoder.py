"""Tests for BGE cross-encoder scoring module."""
from unittest.mock import MagicMock, patch

import pytest

from app.rag.cross_encoder import _sigmoid, score_candidates
from app.rag.retrieve import ChunkCandidate
from app.rag.rerank import RankedChunk


def _make_candidate(
    chunk_id: str,
    content: str = "Test content about grace.",
    annotation: dict | None = None,
    position: int | None = None,
) -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=chunk_id,
        content=content,
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
        position=position,
        annotation=annotation,
    )


def test_sigmoid_of_zero_is_half():
    assert _sigmoid(0.0) == pytest.approx(0.5)


def test_sigmoid_of_large_positive_approaches_one():
    assert _sigmoid(10.0) > 0.99


def test_sigmoid_of_large_negative_approaches_zero():
    assert _sigmoid(-10.0) < 0.01


def test_score_candidates_returns_ranked_chunks():
    candidates = [
        _make_candidate("00000000-0000-0000-0000-000000000001"),
        _make_candidate("00000000-0000-0000-0000-000000000002"),
    ]
    mock_model = MagicMock()
    mock_model.predict.return_value = [2.0, -1.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        result = score_candidates(candidates, "what is grace?")

    assert len(result) == 2
    assert all(isinstance(r, RankedChunk) for r in result)
    # sorted descending — higher raw score first
    assert result[0].chunk_id == "00000000-0000-0000-0000-000000000001"
    assert result[1].chunk_id == "00000000-0000-0000-0000-000000000002"


def test_score_candidates_normalizes_scores_to_0_1():
    candidates = [_make_candidate("00000000-0000-0000-0000-000000000003")]
    mock_model = MagicMock()
    mock_model.predict.return_value = [5.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        result = score_candidates(candidates, "query")

    assert 0.0 <= result[0].reranker_score <= 1.0
    assert result[0].reranker_score == pytest.approx(_sigmoid(5.0))


def test_score_candidates_prepends_annotation_when_present():
    """When annotation dict has 'annotation' key, it must be prepended to content."""
    annotation = {"topics": ["grace"], "annotation": "Theological note on grace."}
    candidate = _make_candidate(
        "00000000-0000-0000-0000-000000000004",
        content="For by grace you have been saved.",
        annotation=annotation,
    )
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        score_candidates([candidate], "grace and salvation")

    # The pair passed to model.predict must include the annotation text
    call_pair = mock_model.predict.call_args[0][0][0]  # first pair
    assert "Theological note on grace." in call_pair[1]
    assert "For by grace you have been saved." in call_pair[1]


def test_score_candidates_uses_content_only_when_annotation_is_none():
    candidate = _make_candidate(
        "00000000-0000-0000-0000-000000000005",
        content="The word of God is living.",
        annotation=None,
    )
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5]

    with patch("app.rag.cross_encoder._model", mock_model):
        score_candidates([candidate], "scripture")

    call_pair = mock_model.predict.call_args[0][0][0]
    assert call_pair[1] == "The word of God is living."


def test_score_candidates_falls_back_to_rrf_order_when_model_none():
    candidates = [
        _make_candidate("00000000-0000-0000-0000-000000000006"),
        _make_candidate("00000000-0000-0000-0000-000000000007"),
    ]
    with patch("app.rag.cross_encoder._model", None):
        result = score_candidates(candidates, "query")

    assert len(result) == 2
    assert all(isinstance(r, RankedChunk) for r in result)
    # fallback assigns descending scores
    assert result[0].reranker_score >= result[1].reranker_score


def test_score_candidates_propagates_position_to_ranked_chunk():
    candidate = _make_candidate("00000000-0000-0000-0000-000000000008", position=13)
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        result = score_candidates([candidate], "query")

    assert result[0].position == 13


def test_score_candidates_empty_input_returns_empty():
    result = score_candidates([], "query")
    assert result == []
