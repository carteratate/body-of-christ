"""One report run shared by the 0.1a source checks (about a minute with all sources)."""
import os

import pytest

from checks import report
from checks.source_text import SOURCES

HAVE_SOURCES = all(os.path.isdir(os.path.join(SOURCES, c)) for c in report.COLLECTIONS)
needs_sources = pytest.mark.skipif(not HAVE_SOURCES,
                                   reason="needs the gitignored datapipeline/sources/")


@pytest.fixture(scope="session")
def checks_run() -> report.RunResult:
    return report.run()


@pytest.fixture(scope="session")
def failing(checks_run) -> dict[str, list[str]]:
    return report.failing_checks(checks_run)
