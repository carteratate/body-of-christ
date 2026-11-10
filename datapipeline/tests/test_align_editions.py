"""`scripts/align_editions.py`: pairing two translations of a document by paragraph (1.3c)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from align_editions import Unit, align, outcomes  # noqa: E402

OLD = [
    Unit("d/1", "The Church has always guarded the Eucharist as a treasure of Christ."),
    Unit("d/2", "Saint Cyril of Jerusalem wrote this instruction for his neophytes:"),
    Unit("d/3", "After the spiritual sacrifice is completed, we pray for the dead, "
                "says Cyril, and Augustine testifies to the same custom in Africa."),
    Unit("d/4", "Transubstantiation is the word the Council of Trent chose for this change."),
]
NEW = [
    Unit("d/1", "The Mystery of Faith, the Eucharist, the Church received from Christ as "
                "a treasure, and has always guarded it."),
    Unit("d/2", "We will rest content with recalling the testimony of Saint Cyril of "
                "Jerusalem to his neophytes: after the spiritual sacrifice we pray for the "
                "dead. Augustine testifies that this custom was kept in Africa."),
    Unit("d/3", "The Council of Trent fittingly called this change transubstantiation."),
]


def test_two_units_one_edition_prints_as_one_pair_with_it():
    pairs = align(OLD, NEW)
    assert [(p.old, p.new) for p in pairs] == [
        (("d/1",), ("d/1",)), (("d/2", "d/3"), ("d/2",)), (("d/4",), ("d/3",))]


def test_only_what_differs_from_the_numbering_is_listed():
    rows = outcomes(align(OLD, NEW))
    assert [(r["kind"], r["old"], r["new"]) for r in rows] == [
        ("mismatch", ["d/2", "d/3"], ["d/2"]), ("mismatch", ["d/4"], ["d/3"])]


def test_a_unit_with_no_counterpart_is_unpaired():
    extra = OLD[:1] + [Unit("d/x", "Zebras quarrel over turnips in Zanzibar on Tuesdays.")]
    rows = outcomes(align(extra, NEW[:1]))
    assert [(r["kind"], r["old"]) for r in rows] == [("unpaired", ["d/x"])]
