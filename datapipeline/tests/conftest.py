import sys
import os
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    """Set stub environment variables before any test module imports config.

    config.settings is built once, at first import, so a test module that sets
    a variable after another module has imported config has no effect. Setting
    them here, before collection, makes the suite independent of test order and
    of whether datapipeline/.env exists. setdefault never overwrites a variable
    already exported in the shell.
    """
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("QDRANT_URL", "http://localhost")
    os.environ.setdefault("QDRANT_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")


# A worker running the full suite with the source checks peaks near WORKER_MB; RESERVE_MB
# stays free for whatever else the machine runs.
WORKER_MB = 1500
RESERVE_MB = 4000


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config):
    """`-n auto` sized by free memory, not CPU count: one worker per WORKER_MB of
    MemAvailable beyond RESERVE_MB, at most one per CPU. Where /proc/meminfo is missing
    (macOS), or PYTEST_XDIST_AUTO_NUM_WORKERS is set, xdist's own count applies."""
    if os.environ.get("PYTEST_XDIST_AUTO_NUM_WORKERS"):
        return None
    try:
        with open("/proc/meminfo") as f:
            available_kb = next(int(line.split()[1]) for line in f
                                if line.startswith("MemAvailable:"))
    except (OSError, StopIteration):
        return None
    cpus = len(os.sched_getaffinity(0))
    return max(1, min(cpus, (available_kb // 1024 - RESERVE_MB) // WORKER_MB))


HYGIENE = ("tests/source_checks/test_text_hygiene.py"
           "::test_broken_word_is_in_its_sources_and_mended")


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_make_scheduler(config, log):
    """`--dist loadscope`, with test_text_hygiene's broken-word cases split in two.

    loadscope keeps each module on one worker, so module-scoped fixtures (whole
    collection builds) are built once. The broken-word cases are the one module too slow
    for a single worker, and each case caches whole collections of raw source text
    (encyclicals about 0.9 GB, councils 0.4 GB), so they become two scopes: the cases
    that read encyclicals, and the rest. Other --dist modes are xdist's own."""
    if config.getvalue("dist") != "loadscope":
        return None
    import json

    from xdist.scheduler import LoadScopeScheduling

    from normalize.text import BROKEN_WORDS_PATH

    with open(BROKEN_WORDS_PATH, encoding="utf-8") as f:
        encyclicals = {e["broken"] for e in json.load(f)
                       if "encyclicals" in e["collections"]}

    class Scheduling(LoadScopeScheduling):
        def _split_scope(self, nodeid):
            if nodeid.startswith(HYGIENE + "["):
                broken = nodeid[len(HYGIENE) + 1:-1]
                return f"{HYGIENE}[{'encyclicals' if broken in encyclicals else 'other'}]"
            return super()._split_scope(nodeid)

    return Scheduling(config, log)


@pytest.fixture()
def write_collection(monkeypatch):
    """Name QDRANT_WRITE_COLLECTION for a test; returns the name."""
    import writers.qdrant as qd

    monkeypatch.setattr(qd, "settings", replace(qd.settings, QDRANT_WRITE_COLLECTION="chunks-test"))
    return "chunks-test"
