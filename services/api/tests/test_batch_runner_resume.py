"""Batch resume must never append incompatible methodology/config records."""
from __future__ import annotations

import json

import pytest
from app.config import settings

from compare_batch.queries import QuerySpec
from compare_batch.runner import (
    _batch_fingerprint, _exclusive_batch_lock, _validate_resume_file,
)


def _queries() -> list[QuerySpec]:
    return [QuerySpec("What is grace?", "doctrinal", ["catechism"])]


@pytest.fixture(autouse=True)
def _evaluation_identity(monkeypatch):
    monkeypatch.setattr(settings, "evaluation_build_id", "test-build")
    monkeypatch.setattr(settings, "evaluation_corpus_id", "test-corpus")


def test_batch_fingerprint_covers_query_and_requested_config():
    base = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)
    assert base != _batch_fingerprint(
        [QuerySpec("What is faith?", "doctrinal", ["catechism"])],
        ["hyde_haiku"], ["catechism"], 4,
    )
    assert base != _batch_fingerprint(_queries(), ["hyde_cohere"], ["catechism"], 4)
    assert base != _batch_fingerprint(_queries(), ["hyde_haiku"], ["bible"], 4)
    assert base != _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 5)
    assert base != _batch_fingerprint(
        _queries(), ["hyde_haiku"], ["catechism"], 4, concurrency=4,
    )
    assert base != _batch_fingerprint(
        _queries(), ["hyde_haiku"], ["catechism"], 4,
        base_url="https://evaluation.example",
    )


def test_batch_fingerprint_requires_deployment_and_corpus_identity(monkeypatch):
    monkeypatch.setattr(settings, "evaluation_corpus_id", None)

    with pytest.raises(ValueError, match="EVALUATION_CORPUS_ID"):
        _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)


def test_resume_rejects_legacy_or_mismatched_artifact(tmp_path):
    output = tmp_path / "results.jsonl"
    output.write_text(json.dumps({"query_idx": 0}) + "\n")
    expected = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)

    with pytest.raises(ValueError, match="different or legacy"):
        _validate_resume_file(output, expected)


def test_resume_accepts_matching_fingerprint(tmp_path):
    output = tmp_path / "results.jsonl"
    expected = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)
    output.write_text(json.dumps({
        "query_idx": 0,
        "batch_fingerprint": expected,
    }) + "\n")

    _validate_resume_file(output, expected)


def test_resume_newline_terminates_valid_final_record(tmp_path):
    output = tmp_path / "results.jsonl"
    expected = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)
    record = json.dumps({"query_idx": 0, "batch_fingerprint": expected})
    output.write_text(record)

    _validate_resume_file(output, expected)

    assert output.read_text() == record + "\n"


def test_resume_repairs_only_truncated_final_record(tmp_path):
    output = tmp_path / "results.jsonl"
    expected = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)
    valid = json.dumps({"query_idx": 0, "batch_fingerprint": expected}) + "\n"
    output.write_text(valid + '{"query_idx": 1')

    _validate_resume_file(output, expected)

    assert output.read_text() == valid


def test_resume_rejects_malformed_nonfinal_record(tmp_path):
    output = tmp_path / "results.jsonl"
    expected = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)
    output.write_text('{bad}\n{"query_idx": 1}\n')

    with pytest.raises(ValueError, match="not the final"):
        _validate_resume_file(output, expected)


def test_batch_lock_rejects_second_writer(tmp_path):
    output = tmp_path / "results.jsonl"
    with _exclusive_batch_lock(output):
        with pytest.raises(RuntimeError, match="Another batch process"):
            with _exclusive_batch_lock(output):
                pass


def test_resume_rejects_duplicate_query_indices(tmp_path):
    output = tmp_path / "results.jsonl"
    expected = _batch_fingerprint(_queries(), ["hyde_haiku"], ["catechism"], 4)
    record = json.dumps({"query_idx": 0, "batch_fingerprint": expected})
    output.write_text(record + "\n" + record + "\n")

    with pytest.raises(ValueError, match="duplicate query_idx 0"):
        _validate_resume_file(output, expected)
