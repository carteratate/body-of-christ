"""The production start command lets uvicorn receive Railway's SIGTERM."""
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_uvicorn_is_execed_so_it_receives_sigterm():
    # Under `sh -c` without exec, sh is PID 1 and never forwards SIGTERM to uvicorn, so
    # every deploy killed in-flight searches and skipped the lifespan teardown.
    cmd = [ln for ln in DOCKERFILE.read_text().splitlines() if ln.startswith("CMD ")]
    assert len(cmd) == 1
    assert "exec uvicorn " in cmd[0]
