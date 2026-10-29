"""RRF `k` as a configured, per-pipeline, measurable axis.

`k` decides when agreement between retrieval paths stops beating a single path's
precision, so two pipelines differing only in `k` are a real comparison. These
tests pin the three things that have to hold for that comparison to mean
anything: the value is configured rather than hardcoded, it travels with the
pipeline, and two arms that differ in it are distinguishable in the eval harness's
fingerprint.
"""
from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from app.config import Settings, settings
from app.rag.pipelines.registry import PIPELINES, RetrievalConfig

_spec = importlib.util.spec_from_file_location(
    "run_eval_suite", Path(__file__).resolve().parents[1] / "scripts" / "run_eval_suite.py"
)
suite = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(suite)


def test_retrieval_config_carries_a_per_pipeline_rrf_k():
    """`None` means "use the configured default", like `retrieval_k_override`."""
    assert RetrievalConfig().rrf_k is None
    assert RetrievalConfig(rrf_k=60).rrf_k == 60


def test_k_alone_changes_the_eval_fingerprint(monkeypatch):
    """Two arms whose fingerprints match cannot be told apart in a results file.

    Holding the *name* fixed and varying only `rrf_k` is the point: the name is
    inside the fingerprinted config, so comparing two differently named entries
    would pass on the name alone and survive deleting `rrf_k` outright.
    """
    name = "hyde_cohere_luna"
    control = PIPELINES[name]
    variant = dataclasses.replace(
        control, retrieval=dataclasses.replace(control.retrieval, rrf_k=60),
    )

    before = suite._fingerprint([name], quota=4)
    monkeypatch.setitem(PIPELINES, name, variant)
    after = suite._fingerprint([name], quota=4)

    assert before["pipeline_configs"] != after["pipeline_configs"]
    assert before["artifact_fingerprint"] != after["artifact_fingerprint"]


def test_rrf_k_is_env_overridable_like_every_other_pipeline_parameter():
    assert Settings(RRF_K=45).rrf_k == 45


def test_rrf_k_must_be_positive():
    """k is a rank denominator; 0 or negative makes 1/(k+rank) meaningless."""
    with pytest.raises(ValueError, match="positive"):
        Settings(RRF_K=0)


@pytest.mark.parametrize("bad", [0, -1, -60])
def test_a_pipeline_cannot_pin_a_nonpositive_k(bad):
    """The registry is the only way a bad k can reach the merge, and it fails quietly.

    `settings.rrf_k` is validated, and no request field reaches `rrf_k`. That leaves a hand-edited
    registry literal as the sole path in, and the failure is silent rather than
    loud: `_rrf_merge` clamps every negative contribution to 0.0 via the
    per-family `max`, so a typo yields all-zero scores and arbitrary ordering
    instead of an error. Someone pinning k for an ablation is exactly the person
    who would ship that result as a finding.
    """
    with pytest.raises(ValueError, match="rrf_k"):
        RetrievalConfig(rrf_k=bad)


def test_the_configured_default_k_is_recorded_for_unpinned_pipelines(monkeypatch):
    """Most pipelines pin nothing, so the default is what actually scored them.

    An unpinned arm records `rrf_k: None`, so the default it resolved to has to
    appear in the fingerprint too, or two deployments running different `RRF_K`
    values fingerprint identically while merging differently.
    """
    unpinned = "hyde_cohere_luna"
    assert PIPELINES[unpinned].retrieval.rrf_k is None

    monkeypatch.setattr(settings, "rrf_k", 20)
    at_20 = suite._fingerprint([unpinned], quota=4)
    monkeypatch.setattr(settings, "rrf_k", 60)
    at_60 = suite._fingerprint([unpinned], quota=4)

    assert at_20["thresholds"]["rrf_k"] == 20
    assert at_60["thresholds"]["rrf_k"] == 60
    assert at_20["artifact_fingerprint"] != at_60["artifact_fingerprint"]
