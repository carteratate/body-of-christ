"""One report run shared by the 0.1a source checks (about a minute with all sources)."""
import os

import pytest

from checks import report
from checks.source_text import SOURCES

HAVE_SOURCES = all(os.path.isdir(os.path.join(SOURCES, c)) for c in report.COLLECTIONS)
needs_sources = pytest.mark.skipif(not HAVE_SOURCES,
                                   reason="needs the gitignored datapipeline/sources/")


@pytest.fixture(scope="session")
def built() -> dict:
    """Every collection built once through SOURCE_ADAPTERS, shared by the checks run and
    the tests that read passages directly."""
    report.placeholder_credentials()
    return {c: report.SOURCE_ADAPTERS[c]() for c in report.COLLECTIONS}


@pytest.fixture(scope="session")
def checks_run(built) -> report.RunResult:
    return report.run(documents_by_collection=built)


@pytest.fixture(scope="session")
def failing(checks_run) -> dict[str, list[str]]:
    return report.failing_checks(checks_run)
