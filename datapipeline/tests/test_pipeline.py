import pytest
from pipeline import (
    resolve_stages, validate_dependencies, estimate_enrich_cost,
    all_execution_order, execution_plan, PipelineError,
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


def test_execution_plan_only_expands_requested_stages():
    plan = execution_plan(["enrich", "embed"], ["bible", "summa"])
    assert plan == [("enrich", "bible"), ("embed", "bible"),
                    ("enrich", "summa"), ("embed", "summa")]


def test_execution_plan_runs_global_fits_once_after_every_collection():
    plan = execution_plan(["enrich", "bm25-annotation-fit"], ["bible", "summa"])
    assert plan == [("enrich", "bible"), ("enrich", "summa"),
                    ("bm25-annotation-fit", None)]


def test_execution_plan_global_only_needs_no_collection():
    assert execution_plan(["bm25-content-fit"], []) == [("bm25-content-fit", None)]


def test_execution_plan_puts_bm25_index_after_the_global_fits():
    plan = execution_plan(["bm25-content-fit", "bm25-index"], ["bible"])
    assert plan == [("bm25-content-fit", None), ("bm25-index", "bible")]


def test_all_execution_order_still_matches_the_full_plan():
    cols = ["bible", "summa"]
    assert all_execution_order(cols) == execution_plan(resolve_stages(["all"]), cols)


def _lock_remote(monkeypatch):
    import publish_lock

    monkeypatch.setattr(publish_lock, "settings_targets", lambda: publish_lock.WriteTargets(
        "postgresql://u:p@db.example.supabase.co/postgres", "https://q.example.qdrant.io"))


def _main_exit(argv):
    from pipeline import main

    with pytest.raises(SystemExit) as raised:
        main(argv)
    return raised.value.code


def test_reader_stage_is_refused_while_locked(monkeypatch, capsys):
    _lock_remote(monkeypatch)
    assert _main_exit(["--stage", "reader", "--collection", "medieval"]) == 2
    assert "locked" in capsys.readouterr().err


def test_enrich_stage_is_refused_while_locked(monkeypatch, capsys):
    _lock_remote(monkeypatch)
    assert _main_exit(["--stage", "enrich", "--collection", "medieval", "--yes",
                       "--release", "2026-11-cleanup"]) == 2
    assert "locked" in capsys.readouterr().err


def test_embed_and_bm25_index_stages_are_refused_while_locked(monkeypatch, capsys):
    _lock_remote(monkeypatch)
    for stage in ("embed", "bm25-index"):
        assert _main_exit(["--stage", stage, "--collection", "medieval"]) == 2
    assert "locked" in capsys.readouterr().err


def test_sample_enrich_writes_only_samples_and_needs_no_entry(monkeypatch):
    import argparse
    from pipeline import _guard_live_writes

    _lock_remote(monkeypatch)
    args = argparse.Namespace(sample=3, collection="medieval", release=None)
    _guard_live_writes(args, ["enrich"])
