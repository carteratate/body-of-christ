import os

import pytest

from ingest.catechism import build_document, _DEFAULT_SRC

pytestmark = [
    pytest.mark.sources,
    pytest.mark.skipif(not os.path.exists(_DEFAULT_SRC),
                       reason="catechism sources not vendored; run scripts/vendor_sources.py"),
]


def test_no_tiny_toc_fragments():
    doc = build_document(_DEFAULT_SRC)
    # The old pipeline emitted 9-char "Article 2" / "PART TWO:" passages; drop them.
    tiny = [p for p in doc.passages if len(p.content) < 30]
    assert tiny == [], tiny[:5]


def test_unit_label_is_ccc_number_and_text_clean():
    doc = build_document(_DEFAULT_SRC)
    numbered = [p for p in doc.passages if p.unit_label]
    assert numbered
    assert all(". . ." not in p.content for p in doc.passages)  # ellipses normalized


def test_anchors_unique_per_document():
    doc = build_document(_DEFAULT_SRC)
    anchors = [p.anchor for p in doc.passages]
    assert len(anchors) == len(set(anchors))


# 1.6 (#168), on the full source.

import json  # noqa: E402
import re  # noqa: E402

from tests.test_catechism import _MARKER, references_match_markers  # noqa: E402

_PAGES = os.path.join(os.path.dirname(__file__), "..", "..", "services", "api", "app",
                      "catechism_pages.json")


@pytest.fixture(scope="module")
def doc():
    return build_document(_DEFAULT_SRC)


def test_chapter_labels_are_headings(doc):
    keys = {p.chapter_key for p in doc.passages}
    assert len(keys) >= 60
    assert all(k.startswith(("ccc/part-", "ccc/prologue")) for k in keys)
    assert not any(re.match(r"^CCC §§", p.chapter_label) for p in doc.passages)
    # Each chapter is one run of passages, in reading order.
    runs = [p.chapter_key for i, p in enumerate(doc.passages)
            if i == 0 or doc.passages[i - 1].chapter_key != p.chapter_key]
    assert len(runs) == len(keys)


def test_heading_text_corrections(doc):
    labels = {p.chapter_label for p in doc.passages}
    assert "Part One, Section Two, The Profession of the Christian Faith" in labels
    assert any("Come Again to Judge" in label for label in labels)
    assert "Part Three, Section One, Man's Vocation: Life in the Spirit" in labels
    assert not any("AGAlN" in label or "Human Communion" in label for label in labels)


def test_every_paragraph_has_one_marker(doc):
    markers = [int(n) for p in doc.passages if p.superseded_by_anchor is None
               for n in _MARKER.findall(p.content)]
    assert markers == list(range(1, 2866))


def test_references_match_markers(doc):
    references_match_markers(doc.passages)
    assert not any(p.reference.endswith(" (part)") for p in doc.passages)


def test_ccc_2267_history(doc):
    [history] = [p for p in doc.passages if p.superseded_by_anchor]
    current = next(p for p in doc.passages if p.anchor == history.superseded_by_anchor)
    assert "Recourse to the death penalty" in current.content
    assert history.anchor == f"{current.anchor}/history-1997" and not history.searchable
    assert "practically non-existent" in history.content


def test_every_passage_finds_its_flipbook_page(doc):
    # The API links each passage to the USCCB flipbook page of its unit_label (§N).
    with open(_PAGES, encoding="utf-8") as f:
        pages = json.load(f)["flipbook_page"]
    assert all(re.fullmatch(r"§\d+", p.unit_label or "") and p.unit_label[1:] in pages
               for p in doc.passages)


# The contents tree (#253), on the full source.

def _range(node) -> tuple[int, int]:
    numbers = [int(n) for n in re.findall(r"\d+", node.range_label)]
    return numbers[0], numbers[-1]


def _nodes(doc):
    import contents
    return list(contents.walk(doc.contents))


def test_contents_tree_roots(doc):
    assert [n.short_label for n in doc.contents] == [
        "Prologue",
        "Part One · The Profession of Faith",
        "Part Two · The Celebration of the Christian Mystery",
        "Part Three · Life in Christ",
        "Part Four · Christian Prayer",
    ]


def test_contents_tree_passes_the_contract_and_reaches_every_chapter(doc):
    import contents
    assert contents.check(doc) == []


def test_contents_tree_labels_are_us_headings():
    from ingest.catechism import build
    assert build(_DEFAULT_SRC).unlabelled == []


def test_contents_tree_ranges_cover_every_paragraph_once(doc):
    # The places a node opens (the leaves), in order, run §1 to §2865 with no gap or
    # overlap, and every node spans exactly its children.
    leaves = [_range(n) for n, _, _ in _nodes(doc) if not n.children]
    assert leaves[0][0] == 1 and leaves[-1][1] == 2865
    for (_, last), (first, _) in zip(leaves, leaves[1:]):
        assert first == last + 1
    for node, _, _ in _nodes(doc):
        if node.children:
            assert _range(node) == (_range(node.children[0])[0], _range(node.children[-1])[1])


def test_contents_tree_penance_and_indulgences(doc):
    by_label = {n.short_label: n for n, _, _ in _nodes(doc)}
    penance = by_label["Article 4 · The Sacrament of Penance and Reconciliation"]
    assert penance.range_label == "§§1422–1498"
    holding = [c for c in penance.children if _range(c)[0] <= 1471 <= _range(c)[1]]
    assert [c.short_label for c in holding] == ["X. Indulgences"]
    assert holding[0].anchor == "ccc/1471"


def test_contents_tree_labels_match_the_text(doc):
    # A node opens the passage printing its heading, in the same words. The one
    # exception is the colon catechism_headings.TITLE_FIXES restores to toc-207's title
    # ("Man's Vocation: Life in the Spirit"), which the text prints without.
    by_anchor = {p.anchor: p for p in doc.passages}

    def fold(text):
        return " ".join(text.casefold().replace(":", "").split())
    for node, _, _ in _nodes(doc):
        if node.label != "Introduction":
            assert fold(node.label) in fold(by_anchor[node.anchor].content), node.key
    assert not any(n.short_label.upper() == n.short_label for n, _, _ in _nodes(doc))
