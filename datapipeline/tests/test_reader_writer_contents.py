"""write_document writes a document's contents tree (migration 0040) with its chunks.

Runs the real writer against a throwaway local PostgreSQL cluster, as
test_reader_writer_outline does.
"""

import asyncio

import asyncpg
import pytest

import contents
from model import ContentsNode, Document, Passage
from tests.test_reader_writer_outline import CORPUS_SCHEMA, DOC_ID, MIGRATIONS, socket_dir  # noqa: F401
from writers import reader_writer

ROWS_SQL = """
    SELECT ordinal, parent_ordinal, depth, node_key, kind, short_label, chapter_key, anchor,
           range_label
    FROM document_contents WHERE document_id = $1 ORDER BY ordinal
"""


def _doc(tree):
    chapters = [("q1/a1/0", "q1/a1"), ("q1/a1/1", "q1/a1"), ("q1/a2/0", "q1/a2")]
    return Document(
        id=DOC_ID, collection="summa", title="Summa", translation="",
        passages=[Passage(content=anchor, reference=None, anchor=anchor, chapter_key=key,
                          chapter_label=key, position=i)
                  for i, (anchor, key) in enumerate(chapters)],
        contents=tree,
    )


def _tree():
    return [ContentsNode(
        key="FP_Q1", kind="question", label="The Nature of Sacred Doctrine",
        short_label="Q. 1 · The Nature of Sacred Doctrine", chapter_key="q1/a1",
        range_label="2 articles",
        children=[
            ContentsNode(key="FP_Q1_A1", kind="article", label="Whether",
                         short_label="Art. 1 · Whether", chapter_key="q1/a1",
                         children=[ContentsNode(key="FP_Q1_A1/h", kind="heading",
                                                label="I answer that",
                                                short_label="I answer that",
                                                chapter_key="q1/a1", anchor="q1/a1/1")]),
            ContentsNode(key="FP_Q1_A2", kind="article", label="Whether again",
                         short_label="Art. 2 · Whether again", chapter_key="q1/a2"),
        ],
    )]


async def _connect(socket, migrations=("0037_document_outline.sql",
                                       "0038_backfill_document_outline.sql",
                                       "0040_document_contents.sql")):
    conn = await asyncpg.connect(host=str(socket), user="postgres", database="postgres")
    await conn.execute(CORPUS_SCHEMA)
    for name in migrations:
        await conn.execute((MIGRATIONS / name).read_text())
    return conn


def test_a_tree_is_written_in_pre_order_and_replaced_on_republish(socket_dir):
    async def scenario():
        conn = await _connect(socket_dir)
        try:
            await reader_writer.write_document(conn, _doc(_tree()))
            first = [tuple(r) for r in await conn.fetch(ROWS_SQL, DOC_ID)]
            smaller = _tree()
            smaller[0].children.pop()
            smaller[0].range_label = "1 article"
            await reader_writer.write_document(conn, _doc(smaller))
            second = [tuple(r) for r in await conn.fetch(ROWS_SQL, DOC_ID)]
            await reader_writer.write_document(conn, _doc(None))
            third = await conn.fetchval(
                "SELECT count(*) FROM document_contents WHERE document_id = $1", DOC_ID)
            return first, second, third
        finally:
            await conn.close()

    first, second, third = asyncio.run(scenario())

    assert first == [
        (1, None, 0, "FP_Q1", "question", "Q. 1 · The Nature of Sacred Doctrine", "q1/a1",
         None, "2 articles"),
        (2, 1, 1, "FP_Q1_A1", "article", "Art. 1 · Whether", "q1/a1", None, None),
        (3, 2, 2, "FP_Q1_A1/h", "heading", "I answer that", "q1/a1", "q1/a1/1", None),
        (4, 1, 1, "FP_Q1_A2", "article", "Art. 2 · Whether again", "q1/a2", None, None),
    ]
    assert [r[3] for r in second] == ["FP_Q1", "FP_Q1_A1", "FP_Q1_A1/h"]
    assert second[0][-1] == "1 article"
    assert third == 0, "a document whose adapter stops emitting a tree keeps no stale rows"


def test_a_broken_tree_writes_nothing(socket_dir):
    async def scenario():
        conn = await _connect(socket_dir)
        try:
            await reader_writer.write_document(conn, _doc(_tree()))
            broken = _tree()
            broken[0].children[1].chapter_key = "q9/a9"
            renamed = _doc(broken)
            renamed.title = "Renamed"
            with pytest.raises(contents.ContentsError):
                await reader_writer.write_document(conn, renamed)
            title = await conn.fetchval("SELECT title FROM documents WHERE id = $1", DOC_ID)
            rows = await conn.fetchval(
                "SELECT count(*) FROM document_contents WHERE document_id = $1", DOC_ID)
            return title, rows
        finally:
            await conn.close()

    assert asyncio.run(scenario()) == ("Summa", 4)


def test_without_migration_0040_a_tree_is_refused_and_no_tree_writes(socket_dir):
    async def scenario():
        conn = await _connect(socket_dir, migrations=("0037_document_outline.sql",
                                                      "0038_backfill_document_outline.sql"))
        try:
            await reader_writer.write_document(conn, _doc(None))
            with pytest.raises(RuntimeError, match="apply migration 0040"):
                await reader_writer.write_document(conn, _doc(_tree()))
            return await conn.fetchval("SELECT count(*) FROM chunks")
        finally:
            await conn.close()

    assert asyncio.run(scenario()) == 3, "the refused write rolled back; the first stands"


def test_deleting_a_document_removes_its_tree(socket_dir):
    async def scenario():
        conn = await _connect(socket_dir)
        try:
            await reader_writer.write_document(conn, _doc(_tree()))
            await conn.execute("DELETE FROM documents WHERE id = $1", DOC_ID)
            return await conn.fetchval("SELECT count(*) FROM document_contents")
        finally:
            await conn.close()

    assert asyncio.run(scenario()) == 0
