import os
from pathlib import Path
import subprocess
import sys

import pytest

from publication import PublicationResult, PublicationTarget
from run_collection import build_parser, main


class RecordingRunner:
    def __init__(self, error: ValueError | None = None):
        self.request = None
        self.error = error

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
