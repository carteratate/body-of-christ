"""The shared decision: is a passage's unit label worth showing a model?

Used by both rerankers and the explanation model. Getting it wrong in either
direction matters: suppressing a Summa dialectical role reintroduces the defect step 3
exists to fix, while emitting a redundant locator adds noise to the provenance field.
"""
from __future__ import annotations

from app.rag.steps.passage_role import display_role


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
