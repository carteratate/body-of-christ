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
    """Remote targets, an empty lock whatever the shipped file holds, and no network."""
    import asyncpg
    import publish_lock
    import writers.qdrant

    monkeypatch.setattr(publish_lock, "settings_targets", lambda: publish_lock.WriteTargets(
        "postgresql://u:p@db.example.supabase.co/postgres", "https://q.example.qdrant.io"))
    monkeypatch.setattr(publish_lock, "load_lock",
                        lambda path=None: publish_lock.PublishLock(reason="test", entries=()))

    def no_network(*args, **kwargs):
        raise AssertionError("the lock must refuse before any network call")

    monkeypatch.setattr(asyncpg, "create_pool", no_network)
    monkeypatch.setattr(writers.qdrant, "get_client", no_network)


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
                       "--release", "test-release-never-approved"]) == 2
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


def _health_stubs(monkeypatch, bad: set[str]):
    """Two collections whose parse output is clean unless named in `bad`, no lock, and
    stage runners that record what they would write."""
    import pipeline
    import stages.parse
    from model import Document, Passage

    def parse(collection):
        content = " " if collection in bad else "Clean text of a passage."
        return [Document(id=f"doc-{collection}", collection=collection, title="T", passages=[
            Passage(content=content, reference="r", anchor="a", chapter_key="c",
                    chapter_label="C", position=0)])]
    writes = []

    async def record(collection, docs, res, **kwargs):
        writes.append(collection)
    monkeypatch.setattr(stages.parse, "parse", parse)
    monkeypatch.setattr(stages.parse, "BUILDERS", {"medieval": None, "summa": None})
    monkeypatch.setattr(pipeline, "_guard_live_writes", lambda args, stages: None)
    monkeypatch.setattr(pipeline, "validate_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline._Resources, "cache", lambda self: None)
    for name in ("_run_reader", "_run_embed", "_run_enrich"):
        monkeypatch.setattr(pipeline, name, record)
    return writes


def _run(argv):
    import asyncio
    import pipeline
    asyncio.run(pipeline._main(pipeline._parse_args(argv)))


@pytest.mark.parametrize("stage", ["reader", "embed", "enrich"])
def test_publishing_stages_refuse_health_block_violations(monkeypatch, stage):
    """The 0.1b block rules run on parsed documents before a reader, embed or full
    enrich run touches the stores."""
    writes = _health_stubs(monkeypatch, bad={"medieval"})
    argv = ["--stage", stage, "--collection", "medieval"] + (["--yes"] * (stage == "enrich"))
    with pytest.raises(ValueError, match="REFUSING: 1 health block-rule violations"):
        _run(argv)
    assert writes == []


def test_collection_all_checks_every_collection_before_any_write(monkeypatch):
    writes = _health_stubs(monkeypatch, bad={"summa"})
    with pytest.raises(ValueError, match="REFUSING: .* in 'summa'"):
        _run(["--stage", "reader", "--collection", "all"])
    assert writes == []
    writes = _health_stubs(monkeypatch, bad=set())
    _run(["--stage", "reader", "--collection", "all"])
    assert writes == ["medieval", "summa"]


def test_dry_run_of_a_publishing_stage_runs_the_health_rules(monkeypatch, tmp_path):
    import pipeline
    _health_stubs(monkeypatch, bad={"medieval"})
    monkeypatch.setattr(pipeline, "CACHE_PATH", str(tmp_path / "cache.db"))
    with pytest.raises(ValueError, match="REFUSING"):
        _run(["--stage", "reader", "--collection", "medieval", "--dry-run"])
    _run(["--stage", "reader", "--collection", "summa", "--dry-run"])


def test_health_refusal_exits_2_with_a_message(monkeypatch, capsys):
    _health_stubs(monkeypatch, bad={"medieval"})
    assert _main_exit(["--stage", "reader", "--collection", "medieval"]) == 2
    assert "pipeline: REFUSING: 1 health" in capsys.readouterr().err
