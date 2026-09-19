"""RRF `k` as a configured, per-pipeline, measurable axis.

`k` decides when agreement between retrieval paths stops beating a single path's
precision, so two pipelines differing only in `k` are a real comparison. These
tests pin the three things that have to hold for that comparison to mean
anything: the value is configured rather than hardcoded, it travels with the
pipeline, and two arms that differ in it are distinguishable downstream.
"""
from __future__ import annotations

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


def test_two_arms_differing_only_in_k_have_different_fingerprints():
    """Same fingerprint would make the two arms unsegmentable in `compare/`."""
    both = methodology.snapshot(["hyde_luna", "hyde_luna_rrf60"])
    # Guard against the trivial pass: an unknown name snapshots as None, which
    # would differ from anything without exercising the axis at all.
    assert both["pipelines"]["hyde_luna"]["config"] is not None
    assert both["pipelines"]["hyde_luna_rrf60"]["config"] is not None
    assert (
        both["pipelines"]["hyde_luna"]["config"]
        != both["pipelines"]["hyde_luna_rrf60"]["config"]
    )
    assert methodology.fingerprint(
        methodology.snapshot(["hyde_luna"])
    ) != methodology.fingerprint(
        methodology.snapshot(["hyde_luna_rrf60"])
    )


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
