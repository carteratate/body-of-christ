"""RRF `k` as a configured, per-pipeline, measurable axis.

`k` decides when agreement between retrieval paths stops beating a single path's
precision, so two pipelines differing only in `k` are a real comparison. These
tests pin the three things that have to hold for that comparison to mean
anything: the value is configured rather than hardcoded, it travels with the
pipeline, and two arms that differ in it are distinguishable downstream.
"""
from __future__ import annotations

import dataclasses

import pytest

from app.config import Settings, settings
from app.rag.compare import methodology
from app.rag.pipelines.registry import PIPELINES, RetrievalConfig


def test_retrieval_config_carries_a_per_pipeline_rrf_k():
    """`None` means "use the configured default", like `retrieval_k_override`."""
    assert RetrievalConfig().rrf_k is None
    assert RetrievalConfig(rrf_k=60).rrf_k == 60


def test_registry_pins_an_alternate_k_so_a_run_can_be_requested_by_name():
    """An arm has to exist by name, or `compare/` cannot be asked to run it."""
    alternates = {
        name: config.retrieval.rrf_k
        for name, config in PIPELINES.items()
        if config.retrieval.rrf_k is not None
    }
    assert alternates, "no pipeline pins an alternate rrf_k"
    assert any(k != settings.rrf_k for k in alternates.values())


def test_the_alternate_arm_differs_from_its_control_only_in_k():
    """An ablation that moves two variables measures neither."""
    control = PIPELINES["hyde_luna"]
    variant = PIPELINES["hyde_luna_rrf60"]

    assert variant.rerank == control.rerank
    assert variant.retrieval.hyde == control.retrieval.hyde
    assert variant.retrieval.fts == control.retrieval.fts
    assert variant.retrieval.retrieval_k_override == control.retrieval.retrieval_k_override
    assert variant.retrieval.rrf_k == 60
    assert control.retrieval.rrf_k is None


def test_k_alone_changes_the_methodology_fingerprint(monkeypatch):
    """Same fingerprint would make two arms unsegmentable in `compare/`.

    Holding the *name* fixed and varying only `rrf_k` is the whole point. An
    earlier version of this test compared two real registry entries, which
    proved nothing: their names differ, the name is inside the snapshotted
    config, so the assertion passed on the name alone and would have survived
    deleting `rrf_k` outright.
    """
    control = PIPELINES["hyde_luna"]
    variant = dataclasses.replace(
        control, retrieval=dataclasses.replace(control.retrieval, rrf_k=60),
    )

    before = methodology.fingerprint(methodology.snapshot(["hyde_luna"]))
    monkeypatch.setitem(PIPELINES, "hyde_luna", variant)
    after = methodology.fingerprint(methodology.snapshot(["hyde_luna"]))

    assert before != after


def test_the_recorded_difference_between_the_arms_is_k_and_nothing_else():
    """Names aside, the two shipped arms must differ in exactly one field."""
    both = methodology.snapshot(["hyde_luna", "hyde_luna_rrf60"])
    control = both["pipelines"]["hyde_luna"]["config"]
    variant = both["pipelines"]["hyde_luna_rrf60"]["config"]
    assert control is not None and variant is not None

    differing = {
        key for key in control["retrieval"]
        if control["retrieval"][key] != variant["retrieval"][key]
    }
    assert differing == {"rrf_k"}
    assert control["rerank"] == variant["rerank"]


def test_methodology_records_k_per_pipeline_not_as_a_global_fixed_parameter():
    """A global entry would claim one k for a run that deliberately varies it."""
    snap = methodology.snapshot(["hyde_luna_rrf60"])
    assert "rrf_k" not in snap["fixed_parameters"]
    assert snap["pipelines"]["hyde_luna_rrf60"]["config"]["retrieval"]["rrf_k"] == 60


def test_rrf_k_is_env_overridable_like_every_other_pipeline_parameter():
    assert Settings(RRF_K=45).rrf_k == 45


def test_rrf_k_must_be_positive():
    """k is a rank denominator; 0 or negative makes 1/(k+rank) meaningless."""
    with pytest.raises(ValueError, match="positive"):
        Settings(RRF_K=0)


@pytest.mark.parametrize("bad", [0, -1, -60])
def test_a_pipeline_cannot_pin_a_nonpositive_k(bad):
    """The registry is the only way a bad k can reach the merge, and it fails quietly.

    `settings.rrf_k` is validated, and no request field reaches `rrf_k` — the
    compare route accepts registry *names* only. That leaves a hand-edited
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

    Making k per-pipeline removed the global `fixed_parameters.rrf_k` entry, and
    for a pinned arm the per-pipeline value replaces it. But an unpinned arm
    records `rrf_k: None` — the default it resolved to has to appear somewhere,
    or two deployments running different `RRF_K` values fingerprint identically
    while merging differently, which is exactly what this module exists to
    prevent. It belongs in `rerank_settings` because it is a setting; the
    per-pipeline entry stays the override, not the effective value.
    """
    unpinned = "hyde_cohere_luna"
    assert PIPELINES[unpinned].retrieval.rrf_k is None

    monkeypatch.setattr(settings, "rrf_k", 20)
    at_20 = methodology.snapshot([unpinned])
    monkeypatch.setattr(settings, "rrf_k", 60)
    at_60 = methodology.snapshot([unpinned])

    assert at_20["rerank_settings"]["rrf_k"] == 20
    assert at_60["rerank_settings"]["rrf_k"] == 60
    assert methodology.fingerprint(at_20) != methodology.fingerprint(at_60)
