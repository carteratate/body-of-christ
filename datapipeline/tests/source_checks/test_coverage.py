"""0.1a coverage: no source file loses coverage against the master baseline."""
import json

import pytest

from checks import report
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

with open(report.DEFAULT_BASELINE, encoding="utf-8") as f:
    BASELINE = json.load(f)
KNOWN = report.load_known()


@pytest.mark.parametrize("collection", report.COLLECTIONS)
def test_coverage_not_below_baseline(checks_run, collection):
    # Each file may fall at most COVERAGE_TOLERANCE points below its baseline, unless
    # its known_defects.json entry says "expected_direction": "down" (rule G removals).
    sub = report.RunResult([collection], {collection: checks_run.coverage[collection]})
    assert report.coverage_regressions(sub, BASELINE, KNOWN) == []


@pytest.mark.parametrize("collection", report.COLLECTIONS)
def test_every_baseline_file_is_still_measured(checks_run, collection):
    measured = {f"{collection}/{name}" for name in checks_run.coverage[collection].files}
    expected = {k for k in BASELINE["files"] if k.split("/", 1)[0] == collection}
    assert sorted(expected - measured) == []
