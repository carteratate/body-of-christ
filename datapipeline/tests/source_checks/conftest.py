"""One build and one report run shared by the 0.1a source checks (about three minutes
with all sources).

Under pytest-xdist (`-n`) the first worker to need either one computes it and pickles it
into the run's shared temporary directory; the other workers wait on the file lock and
load the pickle, so the collections are built once per run, not once per worker."""
import os
import pickle

import pytest
from filelock import FileLock

from checks import report
from checks.source_text import SOURCES

HAVE_SOURCES = all(os.path.isdir(os.path.join(SOURCES, c)) for c in report.COLLECTIONS)
needs_sources = pytest.mark.skipif(not HAVE_SOURCES,
                                   reason="needs the gitignored datapipeline/sources/")


def _once_per_run(tmp_path_factory, name: str, compute):
    """compute() in a serial run; under xdist, computed by one worker and shared."""
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        return compute()
    # Each worker's basetemp sits inside the directory every worker of this run shares.
    shared = tmp_path_factory.getbasetemp().parent
    path = shared / f"{name}.pickle"
    with FileLock(str(path) + ".lock"):
        if path.is_file():
            with open(path, "rb") as f:
                return pickle.load(f)
        value = compute()
        with open(path, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        return value


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> dict:
    """Every collection built once through SOURCE_BUILDS, shared by the checks run and
    the tests that read passages directly."""
    report.placeholder_credentials()
    return _once_per_run(tmp_path_factory, "built",
                         lambda: {c: report.SOURCE_BUILDS[c]() for c in report.COLLECTIONS})


@pytest.fixture(scope="session")
def checks_run(tmp_path_factory, built) -> report.RunResult:
    return _once_per_run(tmp_path_factory, "checks_run",
                         lambda: report.run(documents_by_collection=built))


@pytest.fixture(scope="session")
def failing(checks_run) -> dict[str, list[str]]:
    return report.failing_checks(checks_run)
