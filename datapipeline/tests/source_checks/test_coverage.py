"""0.1a coverage: no source file loses coverage against the baseline, the baseline
keeps up with fixes, and every file under the threshold is a known defect."""
import json

import pytest

from checks import report
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

with open(report.DEFAULT_BASELINE, encoding="utf-8") as f:
    BASELINE = json.load(f)
KNOWN = report.load_known()
KNOWN_COVERAGE = sorted(k for k in KNOWN if k.startswith("coverage."))


def _only(checks_run, collection) -> report.RunResult:
    return report.RunResult([collection], {collection: checks_run.coverage[collection]})


@pytest.mark.parametrize("collection", report.COLLECTIONS)
def test_coverage_not_below_baseline(checks_run, collection):
    # Each file may fall at most COVERAGE_TOLERANCE points below its baseline, unless
    # its known_defects.json entry says "expected_direction": "down" (rule G removals).
    assert report.coverage_regressions(_only(checks_run, collection), BASELINE, KNOWN) == []


@pytest.mark.parametrize("collection", report.COLLECTIONS)
def test_baseline_is_current(checks_run, collection):
    # A fix that raises a file's coverage rewrites the baseline in the same PR
    # (python3 -m checks.report --write-baseline), so the next PR cannot lose it again.
    assert report.stale_baseline(_only(checks_run, collection), BASELINE) == []


@pytest.mark.parametrize("collection", report.COLLECTIONS)
def test_every_baseline_file_is_still_measured(checks_run, collection):
    measured = {f"{collection}/{name}" for name in checks_run.coverage[collection].files}
    expected = {k for k in BASELINE["files"] if k.split("/", 1)[0] == collection}
    assert sorted(expected - measured) == []


@pytest.mark.parametrize("collection", report.COLLECTIONS)
def test_no_unexpected_coverage_failures(checks_run, collection):
    # Every file under COVERAGE_ENTRY_BELOW has a known_defects.json entry.
    failing = report.coverage_failing(_only(checks_run, collection))
    assert sorted(failing - set(KNOWN)) == []


@pytest.mark.parametrize("check_id", [
    pytest.param(k, marks=pytest.mark.xfail(strict=True, reason=f"fixed by {KNOWN[k]['fixed_by']}"))
    for k in KNOWN_COVERAGE
])
def test_known_coverage_defect(checks_run, check_id):
    # Strict xfail: once the file reaches COVERAGE_ENTRY_BELOW, delete its entry.
    assert check_id not in report.coverage_failing(checks_run)
