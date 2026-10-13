"""Contents trees (#250): the contract a source adapter's tree must meet."""

import pytest

import contents
from model import ContentsNode, Document, Passage
from publication import CollectionPublicationRunner, PublicationRequest, PublicationTarget


def _doc(*passages, tree=None):
    """Passages are (anchor, chapter_key) pairs, in reading order."""
    return Document(
        id="11111111-1111-1111-1111-111111111111", collection="summa", title="Summa",
        passages=[Passage(content="text " + anchor, reference="ref", anchor=anchor,
                          chapter_key=key, chapter_label=key, position=i)
                  for i, (anchor, key) in enumerate(passages)],
        contents=tree,
    )


def _node(key, chapter, *children, kind="article", anchor=None):
    return ContentsNode(key=key, kind=kind, label=key.title(), short_label=key.title(),
                        chapter_key=chapter, anchor=anchor, children=list(children))


PASSAGES = (("q1/a1/0", "q1/a1"), ("q1/a1/1", "q1/a1"), ("q1/a2/0", "q1/a2"),
            ("q2/a1/0", "q2/a1"))


def _tree():
    return [
        _node("part-1", "q1/a1",
              _node("q1", "q1/a1",
                    _node("q1/a1", "q1/a1",
                          _node("q1/a1/h", "q1/a1", kind="heading", anchor="q1/a1/1")),
                    _node("q1/a2", "q1/a2"), kind="question"),
              _node("q2", "q2/a1", _node("q2/a1", "q2/a1"), kind="question"),
              kind="part"),
    ]


def test_a_valid_tree_passes_and_reaches_every_chapter():
    assert contents.check(_doc(*PASSAGES, tree=_tree())) == []


def test_a_document_without_a_tree_passes():
    assert contents.check(_doc(*PASSAGES)) == []


def test_flatten_is_pre_order_with_parents_and_depths():
    rows = contents.flatten(_tree())
    assert [(r.ordinal, r.parent_ordinal, r.depth, r.node_key) for r in rows] == [
        (1, None, 0, "part-1"),
        (2, 1, 1, "q1"),
        (3, 2, 2, "q1/a1"),
        (4, 3, 3, "q1/a1/h"),
        (5, 2, 2, "q1/a2"),
        (6, 1, 1, "q2"),
        (7, 6, 2, "q2/a1"),
    ]
    assert rows[3].anchor == "q1/a1/1" and rows[3].kind == "heading"


def test_an_unknown_chapter_fails():
    tree = _tree()
    tree[0].children[1].children[0].chapter_key = "q9/a1"
    with pytest.raises(contents.ContentsError, match="'q9/a1' is not in the document"):
        contents.check(_doc(*PASSAGES, tree=tree))


def test_an_anchor_outside_its_chapter_fails():
    tree = _tree()
    tree[0].children[0].children[0].children[0].anchor = "q1/a2/0"
    with pytest.raises(contents.ContentsError, match="anchor 'q1/a2/0' is not a passage"):
        contents.check(_doc(*PASSAGES, tree=tree))


def test_an_unknown_anchor_fails():
    tree = _tree()
    tree[0].children[0].children[0].children[0].anchor = "nowhere"
    with pytest.raises(contents.ContentsError, match="anchor 'nowhere'"):
        contents.check(_doc(*PASSAGES, tree=tree))


def test_a_duplicate_key_fails():
    tree = _tree()
    tree[0].children[1].key = "q1"
    with pytest.raises(contents.ContentsError, match="'q1': duplicate key"):
        contents.check(_doc(*PASSAGES, tree=tree))


def test_chapters_out_of_reading_order_fail():
    tree = _tree()
    question = tree[0].children[0]
    question.children.reverse()        # a2 before a1
    with pytest.raises(contents.ContentsError, match="comes before chapter 'q1/a2'"):
        contents.check(_doc(*PASSAGES, tree=tree))


def test_an_unknown_kind_and_an_empty_label_fail():
    tree = _tree()
    tree[0].kind = "volume"
    tree[0].children[1].short_label = "  "
    with pytest.raises(contents.ContentsError) as caught:
        contents.check(_doc(*PASSAGES, tree=tree))
    assert "unknown kind 'volume'" in str(caught.value)
    assert "empty label or short_label" in str(caught.value)


def test_unreached_chapters_warn_in_reading_order_without_failing():
    tree = [_node("q1", "q1/a1", kind="question")]
    assert contents.check(_doc(*PASSAGES, tree=tree)) == ["q1/a2", "q2/a1"]


def test_a_chapter_split_around_another_orders_by_its_first_passage():
    """31 production chapter keys are split around another chapter."""
    tree = [_node("a", "a", _node("a-h", "a", kind="heading", anchor="a/1")),
            _node("b", "b")]
    assert contents.check(_doc(("a/0", "a"), ("b/0", "b"), ("a/1", "a"), tree=tree)) == []


def test_the_build_refuses_a_broken_tree_before_opening_any_store():
    tree = _tree()
    tree[0].chapter_key = "missing"
    runner = CollectionPublicationRunner(
        source_adapters={"summa": lambda: [_doc(*PASSAGES, tree=tree)]},
        acquire_reader_store=None, acquire_search_index=None,
    )
    request = PublicationRequest(collection="summa", target=PublicationTarget("reader"))
    with pytest.raises(ValueError, match="contents tree"):
        runner.build(request)
