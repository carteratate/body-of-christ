"""0.1a sequence checks. Every failure must be a known defect; a known defect that now
passes fails the suite (strict xfail) until its entry is deleted."""
import pytest

from checks import report
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

KNOWN = report.load_known()
KNOWN_SEQUENCE = sorted(k for k in KNOWN if k.startswith("sequence."))


@pytest.mark.parametrize("family", report.FAMILIES)
def test_no_unexpected_failures(failing, family):
    unexpected = sorted(k for k in failing
                        if k.startswith(f"sequence.{family}.") and k not in KNOWN)
    assert unexpected == []


@pytest.mark.parametrize("check_id", [
    pytest.param(k, marks=pytest.mark.xfail(strict=True, reason=f"fixed by {KNOWN[k]['fixed_by']}"))
    for k in KNOWN_SEQUENCE
])
def test_known_defect(failing, check_id):
    assert check_id not in failing, failing.get(check_id)
