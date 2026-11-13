"""The shared decision: is a passage's unit label worth showing a model?

Used by both rerankers and the explanation model. Getting it wrong in either
direction matters: suppressing a Summa dialectical role reintroduces the defect step 3
exists to fix, while emitting a redundant locator adds noise to the provenance field.
"""
from __future__ import annotations

from app.rag.steps.passage_role import any_rejected, display_role, rejected_note


def test_no_label_yields_nothing():
    assert display_role(None, "Summa Theologiae, I q1 a1") is None


def test_empty_label_yields_nothing():
    assert display_role("", "Summa Theologiae, I q1 a1") is None


def test_summa_dialectical_role_always_passes_through():
    """0 of 26,748 Summa references contain their dialectical part, because the
    reference names the article's QUESTION, never which side the passage argues."""
    assert display_role(
        "Objection 1",
        "Summa Theologiae, II-II, Question 64 - Of Murder, "
        "Article 6 - Whether it is lawful to kill the innocent?",
    ) == "Objection 1"


def test_label_already_in_the_reference_is_suppressed():
    assert display_role("Can. 33", "Code of Canon Law, Can. 33") is None


def test_bare_ordinal_not_in_the_reference_still_emits():
    """99 Bible chunks carry a bare ordinal the reference lacks. Harmless: both rerank
    prompts and the explain prompt carve locators out explicitly."""
    assert display_role("1", "Baruch 6") == "1"


def test_missing_reference_does_not_suppress():
    """A candidate with no reference must still get its role, not lose it to a
    None-vs-substring accident."""
    assert display_role("Objection 1", None) == "Objection 1"


# --- rejected_note (corpus cleanup 2.4d) ---

def test_rejected_note_for_a_rejected_passage():
    assert rejected_note("rejected", "Condemned proposition 10") == (
        "Rejected position (Condemned proposition 10): the document states this in order "
        "to reject it.")


def test_rejected_note_for_a_summa_objection():
    assert rejected_note("rejected", "Objection 2") == (
        "Rejected position (Objection 2): the document states this in order to reject it.")


def test_rejected_note_without_a_label_still_marks_the_passage():
    assert rejected_note("rejected", None) == (
        "Rejected position: the document states this in order to reject it.")


def test_no_rejected_note_otherwise():
    assert rejected_note(None, "Objection 1") is None
    assert rejected_note(None, None) is None
    # The two sed contras Aquinas grants keep their label and have no voice (1.7).
    assert rejected_note(None, "Objection 4") is None


def test_any_rejected():
    class _C:
        def __init__(self, voice):
            self.voice = voice

    assert not any_rejected([])
    assert not any_rejected([_C(None), _C(None)])
    assert any_rejected([_C(None), _C("rejected")])
