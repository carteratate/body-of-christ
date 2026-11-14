"""3.4's rejected-voice ranges on the master build: each range resolves to the passages
Carter approved, and `roles.rejected_voice` passes (it also runs, with the other review
checks, in test_review_sources.py)."""
import pytest

import registry
from checks import content
from registry import rejected_voice as rv
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

# (title, first anchor) → passages in the range, as approved (NEEDS-CARTER B, 3.4).
COUNTS = {
    ("The Acts of the Disputation with the Heresiarch Manes", "vii.iii.v"): 1,
    ("The Acts of the Disputation with the Heresiarch Manes", "vii.iii.vi/from-p5"): 6,
    ("The Acts of the Disputation with the Heresiarch Manes", "vii.iii.xii"): 2,
    ("The Acts of the Disputation with the Heresiarch Manes", "vii.iii.xiii/from-p1-2"): 1,
    ("The Acts of the Disputation with the Heresiarch Manes", "vii.iii.xlvi/from-p1-3"): 1,
    ("The Octavius of Minucius Felix", "iv.iii.v"): 10,
    ("Council of Ephesus", "council-of-ephesus/nestorius-second-letter"): 4,
    ("Council of Constance", "council-of-constance/session-8/wyclif-articles"): 2,
    ("Council of Constance", "council-of-constance/session-15/hus-articles"): 2,
    ("Syllabus of Errors", "syllabus-of-errors/1"): 14,
    ("Syllabus of Errors", "syllabus-of-errors/15"): 4,
    ("Syllabus of Errors", "syllabus-of-errors/19"): 56,
    ("Syllabus of Errors", "syllabus-of-errors/75"): 2,
    ("Syllabus of Errors", "syllabus-of-errors/77"): 4,
    ("Exsurge Domine", "exsurge-domine/1"): 41,
}


def test_each_range_holds_the_approved_passages(built):
    documents = {d.id: registry.drop_removed(d) for docs in built.values() for d in docs}
    got = {(r.title, r.first_anchor): len(rv.expand(documents[r.document_id], r))
           for r in rv.load_ranges()}
    assert got == COUNTS


def test_roles_rejected_voice_passes_on_every_collection(built):
    assert {c: content.rejected_voice(c, docs) for c, docs in built.items()
            if content.rejected_voice(c, docs)} == {}
