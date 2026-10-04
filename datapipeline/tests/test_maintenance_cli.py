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


def _remote_env():
    import os

    env = os.environ.copy()
    env.update(
        DATABASE_URL="postgresql://u:p@db.example.supabase.co:5432/postgres",
        QDRANT_URL="https://cluster.example.qdrant.io:6333",
        QDRANT_API_KEY="x",
        OPENAI_API_KEY="sk-test",
    )
    return env


def _refused(script, *extra):
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--collection", "medieval", "--apply", *extra],
        capture_output=True, text=True, check=False, env=_remote_env(), timeout=60,
    )
    assert completed.returncode == 2, completed.stderr
    assert "locked" in completed.stderr


def test_backfill_apply_is_refused_while_locked():
    _refused("backfill_missing_vectors.py")
    _refused("backfill_missing_vectors.py", "--release", "test-release-never-approved")


def test_reembed_apply_is_refused_while_locked():
    _refused("reembed_drifted_vectors.py")


def test_reconcile_apply_is_refused_while_locked():
    _refused("reconcile_qdrant_payloads.py")
