import os
from config import settings
from ingest.common import DISPLAY_PASSAGE_MAX_OVERSHOOT
from ingest.summa import build_document

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "summa", "summa.xml")


def test_summa_builds_one_document_with_clean_refs():
    doc = build_document(_SRC)
    assert doc.collection == "summa"
    assert doc.title.startswith("Summa")
    # A nearby sentence may exceed the target slightly rather than be severed.
    limit = settings.MAX_PASSAGE_CHARS + DISPLAY_PASSAGE_MAX_OVERSHOOT
    assert all(len(p.content) <= limit for p in doc.passages)
    # Apparatus expanded in references (no Q[..]/A[..] bracket scheme).
    sample = doc.passages[0].reference
    assert "Q[" not in sample and "A[" not in sample


def test_summa_unit_labels_mark_article_parts():
    doc = build_document(_SRC)
    labels = {p.unit_label for p in doc.passages if p.unit_label}
    assert any(l and l.startswith("Objection") for l in labels) or "I answer that" in labels


# ---------------------------------------------------------------------------
# _split_article — dialectical splitting.
#
# These exercise the splitter directly with inline text, so they run without the
# gitignored `sources/` XML that the build_document tests above depend on.
# ---------------------------------------------------------------------------

from ingest.summa import _split_article  # noqa: E402


def _labels(text):
    return [label for label, _ in _split_article(text)]


def test_splits_the_comma_form_unchanged():
    """The punctuation every existing split was produced by — must not regress."""
    article = (
        "Objection 1: It would seem that...\n\n"
        "On the contrary, Augustine says...\n\n"
        "I answer that, The will of God...\n\n"
        "Reply to Objection 1: The argument fails..."
    )
    assert _labels(article) == [
        "Objection 1", "On the contrary", "I answer that", "Reply to Objection 1",
    ]


def test_splits_the_comma_less_form_at_a_line_start():
    """12 respondeo and 21 sed contra markers in the live corpus are comma-less.

    Before this, the determination stayed glued to the preceding sed contra piece and
    the article looked — to search, to the reranker, to the explanation model — as
    though Aquinas never answered.
    """
    article = (
        "Objection 1: It would seem that...\n\n"
        "On the contrary Augustine says...\n\n"
        "I answer that Each thing receives its species..."
    )
    assert _labels(article) == ["Objection 1", "On the contrary", "I answer that"]


def test_comma_less_marker_mid_line_is_not_a_split_point():
    """One article cites "(Arg. On the contrary)." inside its respondeo. An
    unanchored comma-less alternative would cut that article at the citation."""
    article = (
        "I answer that, As stated above (Arg. On the contrary), the soul turns to God."
    )
    parts = _split_article(article)
    assert _labels(article) == ["I answer that"]
    assert "Arg. On the contrary" in parts[0][1]


def test_comma_less_and_comma_forms_produce_the_same_label():
    """Downstream joins on the label, so the two punctuations must not fork it."""
    assert _labels("I answer that, X") == _labels("start\n\nI answer that X")[1:]
