"""0.1b block rules on the master build. Every block violation must be a known defect (the
publish gate refuses anything else); a known defect that now passes fails the suite (strict
xfail) until its entry is deleted, after which the rule blocks that passage again."""
import pytest

from checks import report
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

KNOWN = report.load_known()
KNOWN_HEALTH = sorted(k for k in KNOWN if k.startswith("health."))


def test_no_unexpected_block_violations(failing):
    unexpected = sorted(k for k in failing if k.startswith("health.") and k not in KNOWN)
    assert unexpected == []


@pytest.mark.parametrize("check_id", [
    pytest.param(k, marks=pytest.mark.xfail(strict=True, reason=f"fixed by {KNOWN[k]['fixed_by']}"))
    for k in KNOWN_HEALTH
])
def test_known_block_defect(failing, check_id):
    assert check_id not in failing, failing.get(check_id)
