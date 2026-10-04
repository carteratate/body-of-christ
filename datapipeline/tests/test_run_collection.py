import os
from pathlib import Path
import subprocess
import sys

import pytest

from model import Document, Passage
import publish_lock
from publication import PublicationResult, PublicationTarget, production_runner
from run_collection import build_parser, main


class RecordingRunner:
    def __init__(self, error: ValueError | None = None):
        self.request = None
        self.error = error
        self.built = None

    def build(self, request):
        self.built = request
        return [
            Document(
                id="11111111-1111-1111-1111-111111111111",
                collection=request.collection,
                title="On Loving God",
                author="Bernard of Clairvaux",
                passages=[
                    Passage(content=f"Passage {n}", reference=str(n), anchor=str(n),
                            chapter_key="c1", chapter_label="Chapter 1", position=n)
                    for n in range(3)
                ],
            )
        ]

    async def publish(self, request):
        self.request = request
        if self.error is not None:
            raise self.error
        return PublicationResult(
            collection=request.collection,
            target=request.target,
            document_count=2,
            passage_count=12,
        )


def test_help_describes_normal_and_destructive_publication_options():
    help_text = build_parser().format_help()

    assert "reconcile one collection" in help_text
    assert "--target {reader,search,both}" in help_text
    assert "--reset-search-index" in help_text
    assert "--wipe-reader" in help_text
    assert "--confirm-reader-wipe COLLECTION" in help_text
    assert "--clean" not in help_text


def test_help_does_not_require_store_or_embedding_credentials(tmp_path):
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL="",
        OPENAI_API_KEY="",
        QDRANT_URL="",
        QDRANT_API_KEY="",
    )

    completed = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "run_collection.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--reset-search-index" in completed.stdout
    assert completed.stderr == ""


def test_cli_builds_a_complete_publication_request(capsys):
    runner = RecordingRunner()

    exit_code = main(
        [
            "--collection",
            "medieval",
            "--target",
            "both",
            "--reset-search-index",
            "--wipe-reader",
            "--confirm-reader-wipe",
            "medieval",
        ],
        runner=runner,
    )

    assert exit_code == 0
    assert runner.request.collection == "medieval"
    assert runner.request.target is PublicationTarget.BOTH
    assert runner.request.reset_search_index is True
    assert runner.request.wipe_reader is True
    assert runner.request.wipe_reader_confirmation == "medieval"
    assert "2 documents, 12 passages" in capsys.readouterr().out


def test_retired_clean_spelling_is_rejected_before_runner_acquisition(capsys):
    runner = RecordingRunner()

    with pytest.raises(SystemExit) as raised:
        main(
            ["--collection", "medieval", "--target", "search", "--clean"],
            runner=runner,
        )

    assert raised.value.code == 2
    assert runner.request is None
    assert "unrecognized arguments: --clean" in capsys.readouterr().err


def test_runner_refusal_is_reported_as_a_cli_usage_failure(capsys):
    runner = RecordingRunner(ValueError("reader-wipe confirmation must exactly match"))

    with pytest.raises(SystemExit) as raised:
        main(["--collection", "medieval", "--wipe-reader"], runner=runner)

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert "reader-wipe confirmation must exactly match" in captured.err


def test_dry_run_acquires_no_store_and_prints_counts(capsys):
    runner = RecordingRunner()

    exit_code = main(["--collection", "medieval", "--dry-run"], runner=runner)

    assert exit_code == 0
    assert runner.request is None
    assert runner.built.collection == "medieval"
    assert "medieval: dry run, 1 documents, 3 passages; nothing written" in capsys.readouterr().out


def test_release_is_passed_into_the_request():
    runner = RecordingRunner()

    main(["--collection", "medieval", "--release", "2026-11-cleanup"], runner=runner)

    assert runner.request.release == "2026-11-cleanup"


def test_live_publish_is_refused_while_locked(tmp_path, monkeypatch, capsys):
    lock_path = tmp_path / "PUBLISH_LOCK.json"
    lock_path.write_text('{"since": "2026-10-04", "reason": "test", "approved_applies": []}')
    monkeypatch.setattr(publish_lock, "settings_targets", lambda: publish_lock.WriteTargets(
        "postgresql://u:p@db.example.supabase.co/postgres", "https://q.example.qdrant.io"))

    def no_network(*args, **kwargs):
        raise AssertionError("the lock must refuse before any network call")

    monkeypatch.setattr("asyncpg.connect", no_network)
    runner = production_runner(lock_path=lock_path)
    runner._source_adapters = {"catechism": no_network}

    with pytest.raises(SystemExit) as raised:
        main(["--collection", "catechism", "--target", "both", "--release", "x"],
             runner=runner)

    assert raised.value.code == 2
    assert "locked" in capsys.readouterr().err
