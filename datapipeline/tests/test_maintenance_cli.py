from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).parents[1] / "scripts"


def test_backfill_cli_reports_an_unknown_collection_without_crashing():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "backfill_missing_vectors.py"),
            "--collection",
            "not-a-collection",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "unknown collection" in completed.stderr
    assert "ImportError" not in completed.stderr


def test_reembed_cli_reports_an_unknown_collection_without_crashing():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "reembed_drifted_vectors.py"),
            "--collection",
            "not-a-collection",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "unknown collection" in completed.stderr
    assert "ImportError" not in completed.stderr


def test_reconcile_cli_reports_an_unknown_collection_without_crashing():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "reconcile_qdrant_payloads.py"),
            "--collection",
            "not-a-collection",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "unknown collection" in completed.stderr
    assert "ImportError" not in completed.stderr
