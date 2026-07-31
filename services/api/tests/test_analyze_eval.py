"""The analyzer re-scores stored runs under current weights.

Weights are a decision we want to be able to revisit after a run, which only works
if the composite is derived from persisted per-dimension scores rather than the
`weighted_total` frozen into the file at judging time.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.rag.compare.judge import WEIGHTS

_spec = importlib.util.spec_from_file_location(
    "analyze_eval", Path(__file__).resolve().parents[1] / "scripts" / "analyze_eval.py"
)
analyze_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze_eval)


def _row(**dims):
    return {
        "pipeline": "p",
        "dimensions": {d: {"score": dims.get(d, 0.0), "reasoning": ""} for d in WEIGHTS},
        # Deliberately wrong: a value frozen under some older weighting.
        "weighted_total": 0.123,
    }


def test_total_ignores_the_stored_weighted_total():
    assert analyze_eval.total(_row(retrieval_relevance=1.0)) != pytest.approx(0.123)


def test_total_recomputes_from_dimensions_under_current_weights():
    row = _row(**{d: 1.0 for d in WEIGHTS})
    assert analyze_eval.total(row) == pytest.approx(1.0)
    only_one = _row(retrieval_relevance=1.0)
    assert analyze_eval.total(only_one) == pytest.approx(WEIGHTS["retrieval_relevance"])


def test_dims_track_the_judge_rather_than_a_local_copy():
    """A hardcoded DIMS list would silently omit a newly added dimension from the
    per-dimension table while the composite still counted it."""
    assert analyze_eval.DIMS == list(WEIGHTS)
