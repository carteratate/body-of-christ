"""0.1d's checks for the 6 Oct 2026 corpus reviews on the master build: the structure,
role, editorial, attribution, label, registry and text checks, the unit coverage checks,
the new sentinels' namespace and the tracked health report rules. Every failure must be a
known defect; a known defect that now passes fails the suite (strict xfail) until its
entry is deleted; and an entry that lists units must not gain one."""
import pytest

from checks import report
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

KNOWN = report.load_known()
PREFIXES = tuple(f"{n}." for n in report.REVIEW_NAMESPACES) + report.UNIT_COVERAGE_IDS
TRACKED = tuple(f"health.{r}:" for r in report.health.TRACKED_REPORT_RULES)
KNOWN_REVIEW = sorted(k for k in KNOWN if k.startswith(PREFIXES + TRACKED))


def _mine(check_id: str) -> bool:
    return check_id.startswith(PREFIXES + TRACKED)


def test_no_unexpected_review_failures(failing):
    assert sorted(k for k in failing if _mine(k) and k not in KNOWN) == []


def test_review_defects_do_not_grow(failing):
    grown = {k: v for k, v in report.grown_defects(failing, KNOWN).items() if _mine(k)}
    assert grown == {}


def test_every_review_check_id_has_a_collection():
    assert [k for k in KNOWN_REVIEW if report.check_scope(k) not in report.COLLECTIONS] == []


@pytest.mark.parametrize("check_id", [
    pytest.param(k, marks=pytest.mark.xfail(strict=True, reason=f"fixed by {KNOWN[k]['fixed_by']}"))
    for k in KNOWN_REVIEW
])
def test_known_review_defect(failing, check_id):
    assert check_id not in failing, failing.get(check_id)
