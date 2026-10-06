"""0.1a sentinels: minimum sizes, as numbers, for units the 28 Sep audits named."""
import pytest

from checks import report
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

KNOWN = report.load_known()


def _param(sentinel: report.Sentinel):
    key = f"sentinel.{sentinel.name}"
    marks = [pytest.mark.xfail(strict=True, reason=f"fixed by {KNOWN[key]['fixed_by']}")] \
        if key in KNOWN else []
    return pytest.param(sentinel, id=sentinel.name, marks=marks)


@pytest.mark.parametrize("sentinel", [_param(s) for s in report.SENTINELS])
def test_sentinel(checks_run, sentinel):
    assert checks_run.sentinels[sentinel.name] >= sentinel.minimum
