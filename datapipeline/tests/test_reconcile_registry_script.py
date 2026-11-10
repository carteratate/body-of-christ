"""`scripts/reconcile_registry.py`: reviewed reasons for low-scoring passages (1.10c)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from reconcile_registry import kept_entries  # noqa: E402

LOW = [{"passage_id": "a", "document_id": "d", "anchor": "x"},
       {"passage_id": "b", "document_id": "d", "anchor": "y"}]
PRIOR = [{"passage_id": "a", "document_id": "d", "anchor": "x", "reason": "earlier review",
          "added_by": "1.10b"}]


def test_one_reason_for_all():
    kept, problems = kept_entries(LOW, PRIOR, "1.10c", reason="why")
    assert [(e["passage_id"], e["reason"], e["added_by"]) for e in kept] == \
        [("a", "why", "1.10c"), ("b", "why", "1.10c")]
    assert problems == []


def test_reasons_per_passage_and_null_keeps_the_earlier_review():
    kept, problems = kept_entries(LOW, PRIOR, "1.10c", reasons={"a": None, "b": "its own"})
    assert kept == [PRIOR[0], {**LOW[1], "reason": "its own", "added_by": "1.10c"}]
    assert problems == []


def test_a_passage_the_reasons_file_leaves_out_is_a_problem():
    kept, problems = kept_entries(LOW, PRIOR, "1.10c", reasons={"a": None})
    assert [e["passage_id"] for e in kept] == ["a"]
    assert len(problems) == 1 and "(b)" in problems[0]


def test_null_without_an_earlier_entry_is_a_problem():
    kept, problems = kept_entries(LOW, PRIOR, "1.10c", reasons={"a": None, "b": None})
    assert [e["passage_id"] for e in kept] == ["a"]
    assert "no kept_text entry" in problems[0]


def test_a_passage_whose_text_was_replaced_is_not_held_to_its_live_text():
    # 1.3c: a new translation keeps its paragraph's ID and declares `text_replaced`, as the
    # release report's stability check reads it.
    from model import Document, Passage
    from reconcile_registry import lost_text, low_scores

    def doc(**metadata):
        p = Passage(content="An entirely different wording of the paragraph.", reference="r",
                    anchor="d/1", chapter_key="d/c", chapter_label="c", position=0,
                    metadata=metadata)
        return Document(id="d", collection="encyclicals", title="T", passages=[p])

    rows = [{"passage_id": "a", "document_id": "d", "anchor": "d/1", "status": "active"}]
    live = {"a": "The live text of this paragraph, in the old translation of it."}
    assert [e["passage_id"] for e in low_scores(rows, [doc()], live)] == ["a"]
    replaced = doc(text_replaced="vatican.va replaces papalencyclicals.net")
    assert low_scores(rows, [replaced], live) == []
    assert lost_text(live)("a", replaced.passages[0], replaced) is None
