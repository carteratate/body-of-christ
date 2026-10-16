import asyncio
import logging
from unittest.mock import patch

import asyncpg

from app.models.auth import AuthUser
from app.routes.documents import get_document_toc
from tests.fake_pool import FakePool

_DOC = "11111111-1111-1111-1111-111111111111"

_CHAPTERS = [
    {"chapter_key": "john/1", "chapter_label": "John 1"},
    {"chapter_key": "john/2", "chapter_label": "John 2"},
]


def _doc_row(outline_ready):
    return {"id": _DOC, "collection": "bible", "title": "John", "author": None,
            "year": None, "translation": "WEB-C", "metadata": None, "cnt": 2,
            "reader_access": "full", "outline_ready": outline_ready}


def _node(ordinal, parent, key, chapter, anchor=None, anchor_missing=False, kind="chapter"):
    return {"ordinal": ordinal, "parent_ordinal": parent, "node_key": key, "kind": kind,
            "label": key.title(), "short_label": key.title(), "chapter_key": chapter,
            "anchor": anchor, "range_label": None, "anchor_missing": anchor_missing}


def _toc(outline_ready=True, contents=()):
    """`contents` is the contents-tree rows, or an exception the query raises."""
    pool = FakePool()
    pool.conn.fetchrow.return_value = _doc_row(outline_ready)
    pool.conn.fetch.side_effect = [_CHAPTERS, contents if isinstance(contents, Exception)
                                   else list(contents)]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_toc(_DOC, user=AuthUser(user_id="u", email=None)))
    return resp, [call.args[0] for call in pool.conn.fetch.await_args_list]


def test_toc_returns_ordered_chapters():
    resp, _ = _toc()
    assert [c.chapter_label for c in resp.chapters] == ["John 1", "John 2"]
    assert resp.document.title == "John"
    assert resp.document.translation == "WEB-C"


def test_toc_reads_the_outline_when_it_is_built_and_chunks_otherwise():
    _, [outline_sql, _] = _toc(outline_ready=True)
    _, [legacy_sql, _] = _toc(outline_ready=False)
    assert "FROM document_chapters" in outline_sql
    assert "FROM chunks" in legacy_sql and "GROUP BY" in legacy_sql


def test_a_document_without_a_tree_has_no_contents():
    resp, [_, contents_sql] = _toc(contents=[])
    assert "FROM document_contents" in contents_sql
    assert resp.contents is None


def test_the_tree_is_nested_from_its_pre_order_rows():
    resp, _ = _toc(contents=[
        _node(1, None, "gospel", "john/1", kind="part"),
        _node(2, 1, "prologue", "john/1"),
        _node(3, 2, "word", "john/1", anchor="john/1/1", kind="heading"),
        _node(4, 1, "signs", "john/2"),
    ])

    [root] = resp.contents
    assert (root.key, root.kind, [c.key for c in root.children]) == (
        "gospel", "part", ["prologue", "signs"])
    [heading] = root.children[0].children
    assert (heading.anchor, heading.chapter_key, heading.children) == ("john/1/1", "john/1", [])
    assert resp.chapters[1].chapter_key == "john/2", "the flat list is unchanged"


def test_a_database_without_migration_0040_serves_chapters_only():
    resp, _ = _toc(contents=asyncpg.UndefinedTableError("relation does not exist"))
    assert resp.contents is None
    assert len(resp.chapters) == 2


def _stale(caplog, rows):
    with caplog.at_level(logging.WARNING, logger="app.routes.documents"):
        resp, _ = _toc(contents=rows)
    assert resp.contents is None
    assert len(resp.chapters) == 2, "the flat list still serves"
    return caplog.text


def test_a_tree_opening_a_missing_chapter_is_not_served(caplog):
    log = _stale(caplog, [_node(1, None, "a", "john/1"), _node(2, None, "b", "john/9")])
    assert "opens missing chapter 'john/9'" in log and _DOC in log


def test_a_tree_pointing_at_a_missing_anchor_is_not_served(caplog):
    log = _stale(caplog, [_node(1, None, "a", "john/1", anchor="gone", anchor_missing=True)])
    assert "missing anchor 'gone'" in log


def test_a_tree_out_of_reading_order_is_not_served(caplog):
    log = _stale(caplog, [_node(1, None, "b", "john/2"), _node(2, None, "a", "john/1")])
    assert "out of reading order" in log


def test_a_chapter_listed_twice_keeps_its_first_place_in_reading_order():
    """The chunks-derived list groups by (key, label), so a key can appear twice."""
    pool = FakePool()
    pool.conn.fetchrow.return_value = _doc_row(False)
    pool.conn.fetch.side_effect = [
        [{"chapter_key": "a", "chapter_label": "A"}, {"chapter_key": "b", "chapter_label": "B"},
         {"chapter_key": "a", "chapter_label": "A, continued"}],
        [_node(1, None, "a", "a"), _node(2, None, "b", "b")],
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_toc(_DOC, user=AuthUser(user_id="u", email=None)))
    assert [n.key for n in resp.contents] == ["a", "b"]

