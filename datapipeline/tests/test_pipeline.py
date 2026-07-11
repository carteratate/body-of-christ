import pytest
from pipeline import (
    resolve_stages, validate_dependencies, estimate_enrich_cost,
    all_execution_order, PipelineError,
)


def test_resolve_all_is_dependency_ordered():
    order = resolve_stages(["all"])
    assert order.index("parse") < order.index("reader") < order.index("enrich") < order.index("embed")
    assert order.index("enrich") < order.index("bm25-annotation-fit")
    assert order.index("bm25-content-fit") < order.index("bm25-index")
    assert order.index("bm25-annotation-fit") < order.index("bm25-index")


def test_resolve_unknown_stage_raises():
    with pytest.raises(PipelineError):
        resolve_stages(["frobnicate"])


def test_estimate_enrich_cost_uses_constants():
    est = estimate_enrich_cost(1000)
    assert est["usd"] > 0
    assert est["input_tokens"] > 0 and est["output_tokens"] > 0


def test_all_execution_order_has_global_gates_between_collections():
    order = all_execution_order(["bible", "summa"])
    stages = [s for s, _ in order]
    # per-collection enrich for both appears before the global annotation fit
    last_enrich = max(i for i, (s, c) in enumerate(order) if s == "enrich")
    ann_fit = stages.index("bm25-annotation-fit")
    assert last_enrich < ann_fit
    # bm25-index appears after both fits
    assert stages.index("bm25-index") > stages.index("bm25-content-fit")
    assert stages.index("bm25-index") > ann_fit


class _CacheNoEnrich:
    def get_collection_status(self, c): return None


def test_validate_embed_before_enrich_raises(tmp_path):
    with pytest.raises(PipelineError):
        validate_dependencies("bible", "embed", _CacheNoEnrich(), model_paths={})
