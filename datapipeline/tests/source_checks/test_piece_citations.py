"""1.10c on the vendored build: every split piece cites exactly its own text."""
import re
from collections import Counter, defaultdict

import pytest

from checks import content, report
from identity import unit_anchor
from ingest.pieces import unit_reference
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

REPACKED = ("bible", "encyclicals", "apostolic-exhortations", "papal-documents", "councils",
            "church-fathers", "medieval")
KNOWN = report.load_known()


def _shared(documents) -> list[tuple[str, str, set[str]]]:
    """(document id, reference, the unit anchors citing it) for each reference two or
    more passages of one document share."""
    out = []
    for d in documents:
        by_ref: dict[str, set[str]] = defaultdict(set)
        count = Counter(p.reference for p in d.passages)
        for p in d.passages:
            by_ref[p.reference].add(unit_anchor(p.anchor))
        out += [(d.id, ref, by_ref[ref]) for ref, n in count.items() if n > 1]
    return out


def test_no_two_pieces_of_a_unit_share_a_reference(built):
    counts = {}
    for c in REPACKED:
        shared = _shared(built[c])
        counts[c] = sum(Counter(p.reference for d in built[c] for p in d.passages)[ref] - 1
                        for _, ref, _ in shared)
        assert [(ref, units) for _, ref, units in shared if len(units) == 1] == [], c
    print("\nduplicate (document_id, reference) pairs:", counts)


def test_papal_duplicates_are_only_known_duplicated_paragraphs(built):
    """Two units numbered alike (1.3a's `sequence.numbered_paragraphs.duplicated`) are
    the only papal passages that still share a reference; the Bible has none."""
    assert _shared(built["bible"]) == []
    for c in ("encyclicals", "apostolic-exhortations", "papal-documents"):
        for d in built[c]:
            numbers = {unit_reference(ref).rsplit("§", 1)[-1]
                       for _, ref, _ in _shared([d])}
            if not numbers:
                continue
            key = f"sequence.numbered_paragraphs.duplicated:{d.metadata['source_key']}.html"
            assert key in KNOWN and KNOWN[key]["fixed_by"] == "1.3a", key
            assert numbers <= set(KNOWN[key]["units"]), (key, numbers)


_RANGE = re.compile(r"^(?P<book>.+?) (?P<c1>\d+)(?::(?P<v1>\d+)(?:–(?:(?P<c2>\d+):)?"
                    r"(?P<v2>\d+))?)?$")
_MARKER = re.compile(r"\{\{v:(\d+)\}\}")


def test_bible_piece_ranges_match_their_verses(built):
    for d in built["bible"]:
        chapters = Counter(unit_anchor(p.anchor) for p in d.passages)
        for p in d.passages:
            m = _RANGE.match(unit_reference(p.reference))
            assert m and m["book"] == d.title, p.reference
            if m["v1"] is None:                 # a whole chapter, "Tobit 3": not split
                assert chapters[unit_anchor(p.anchor)] == 1, p.reference
                continue
            # A marker with no text after it is an empty source verse (Sirach 23:28).
            markers = [int(v[1]) for v in _MARKER.finditer(p.content)
                       if p.content[v.end():].split("{{v:", 1)[0].strip()]
            assert int(m["v1"]) == int(p.unit_label), (p.reference, p.unit_label)
            assert int(m["v2"] or m["v1"]) == (markers[-1] if markers else int(p.unit_label)), \
                p.reference
            assert not p.content.startswith("{{v:"), p.anchor


def test_thml_references_carry_no_author(built):
    for c in ("church-fathers", "medieval"):
        assert content.reference_author_consistent(c, built[c]) == {}
        for d in built[c]:
            assert [p.reference for p in d.passages if " — " in p.reference
                    and p.reference.startswith(f"{d.author} — ")] == [], d.title
            assert all(p.reference.startswith(f"{d.title}, ") for p in d.passages), d.title
