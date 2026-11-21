import os
from pathlib import Path
import subprocess
import sys

import pytest

from model import ContentsNode, Document, Passage
from run_collection import build_parser, main


class RecordingBuilder:
    def __init__(self, error: ValueError | None = None):
        self.calls = []
        self.error = error

    def __call__(self, collection, *, limit=None):
        self.calls.append((collection, limit))
        if self.error is not None:
            raise self.error
        return [
            Document(
                id="11111111-1111-1111-1111-111111111111",
                collection=collection,
                title="On Loving God",
                author="Bernard of Clairvaux",
                translation="William Harman van Allen (1909)",
                passages=[
                    Passage(content=f"Passage {n}", reference=str(n), anchor=str(n),
                            chapter_key="c1", chapter_label="Chapter 1", position=n)
                    for n in range(3)
                ],
            )
        ]


def test_help_offers_only_the_dry_run():
    help_text = build_parser().format_help()

    assert "--dry-run" in help_text
    for removed in ("--target", "--reset-search-index", "--wipe-reader",
                    "--confirm-reader-wipe", "--release", "--clean"):
        assert removed not in help_text


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
    assert "--dry-run" in completed.stdout
    assert completed.stderr == ""


def test_live_publish_points_to_publish_py(capsys):
    """2.2w: a live invocation exits 2 and names publish.py; nothing is built."""
    builder = RecordingBuilder()

    with pytest.raises(SystemExit) as raised:
        main(["--collection", "medieval"], builder=builder)

    assert raised.value.code == 2
    assert builder.calls == []
    assert "publish.py stage" in capsys.readouterr().err


@pytest.mark.parametrize("flag", [
    ["--target", "both"], ["--reset-search-index"], ["--wipe-reader"],
    ["--confirm-reader-wipe", "medieval"], ["--release", "x"], ["--clean"],
])
def test_removed_flags_are_rejected(capsys, flag):
    builder = RecordingBuilder()

    with pytest.raises(SystemExit) as raised:
        main(["--collection", "medieval", "--dry-run", *flag], builder=builder)

    assert raised.value.code == 2
    assert builder.calls == []
    assert "unrecognized arguments" in capsys.readouterr().err


def test_build_refusal_is_reported_as_a_cli_usage_failure(capsys):
    builder = RecordingBuilder(ValueError("REFUSING: 1 health block-rule violations"))

    with pytest.raises(SystemExit) as raised:
        main(["--collection", "medieval", "--dry-run"], builder=builder)

    assert raised.value.code == 2
    assert "REFUSING: 1 health" in capsys.readouterr().err


def test_dry_run_prints_counts(capsys):
    builder = RecordingBuilder()

    exit_code = main(["--collection", "medieval", "--dry-run", "--limit", "5"],
                     builder=builder)

    assert exit_code == 0
    assert builder.calls == [("medieval", 5)]
    assert "medieval: dry run, 1 documents, 3 passages; nothing written" in capsys.readouterr().out


def test_dry_run_reports_a_contents_tree_and_the_chapters_it_misses(capsys):
    class TreeBuilder(RecordingBuilder):
        def __call__(self, collection, *, limit=None):
            [document] = super().__call__(collection, limit=limit)
            document.passages[2].chapter_key = "c2"
            document.contents = [ContentsNode(key="book-1", kind="chapter", label="Book 1",
                                              short_label="Book 1", chapter_key="c1")]
            return [document]

    assert main(["--collection", "medieval", "--dry-run"], builder=TreeBuilder()) == 0
    out = capsys.readouterr().out
    assert ("contents tree: On Loving God, 1 nodes; WARNING 1 chapters no node opens, "
            "first 'c2'") in out
