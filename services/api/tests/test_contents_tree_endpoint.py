"""Migration 0040 (document_contents) and the contents tree /toc serves from it.

Runs the real /toc route against a throwaway PostgreSQL cluster with 0037 and 0040
applied. The tree is written the way the datapipeline writes it: pre-order rows,
replaced whole with the document's chunks.
"""

import subprocess

import pytest

from app.routes.documents import get_document_toc
from tests.pg_cluster import CORPUS_SCHEMA, local_cluster
from tests.test_reader_outline_endpoints import DOC, SEED, USER, _routes_on

# Over SEED's chapters q1..q4 (q2 is split around q3): Part I holds q1 and q2, with a
# heading inside q1; Part II holds q3 and q4.
TREE = f"""
    INSERT INTO document_contents
        (document_id, ordinal, parent_ordinal, depth, node_key, kind, label, short_label,
         chapter_key, anchor, range_label)
    VALUES
        ('{DOC}', 1, NULL, 0, 'I', 'part', 'First Part', 'I · First Part', 'q1', NULL, 'Qq. 1–2'),
        ('{DOC}', 2, 1, 1, 'I/q1', 'question', 'Question 1', 'Q. 1', 'q1', NULL, '2 articles'),
        ('{DOC}', 3, 2, 2, 'I/q1/a2', 'heading', 'Article 2', 'Art. 2', 'q1', 'q1/a2', NULL),
        ('{DOC}', 4, 1, 1, 'I/q2', 'question', 'Question 2', 'Q. 2', 'q2', NULL, NULL),
        ('{DOC}', 5, NULL, 0, 'II', 'part', 'Second Part', 'II · Second Part', 'q3', NULL, NULL),
        ('{DOC}', 6, 5, 1, 'II/q3', 'question', 'Question 3', 'Q. 3', 'q3', NULL, NULL),
        ('{DOC}', 7, 5, 1, 'II/q4', 'question', 'Question 4', 'Q. 4', 'q4', NULL, NULL);
"""


@pytest.fixture()
async def db():
    with local_cluster("tc-contents-") as cluster:
        cluster.sql(CORPUS_SCHEMA)
        cluster.sql("CREATE UNIQUE INDEX ON chunks (document_id, anchor) WHERE anchor IS NOT NULL")
        cluster.migrate("0037_document_outline.sql", "0040_document_contents.sql")
        cluster.sql(SEED)
        cluster.sql(f"SELECT refresh_document_outline('{DOC}')")
        async with _routes_on(cluster):
            yield cluster


def _shape(nodes):
    return [(n.key, n.chapter_key, n.anchor, _shape(n.children)) for n in nodes]


async def test_toc_serves_the_tree_beside_the_chapters(db):
    db.sql(TREE)

    toc = await get_document_toc(DOC, user=USER)

    assert [c.chapter_key for c in toc.chapters] == ["q1", "q2", "q3", "q4"]
    assert _shape(toc.contents) == [
        ("I", "q1", None, [("I/q1", "q1", None, [("I/q1/a2", "q1", "q1/a2", [])]),
                           ("I/q2", "q2", None, [])]),
        ("II", "q3", None, [("II/q3", "q3", None, []), ("II/q4", "q4", None, [])]),
    ]
    [first, _] = toc.contents
    assert (first.kind, first.short_label, first.range_label) == ("part", "I · First Part",
                                                                 "Qq. 1–2")


async def test_a_document_with_no_rows_has_no_tree(db):
    assert (await get_document_toc(DOC, user=USER)).contents is None


async def test_rewriting_chunks_without_the_tree_withdraws_it(db):
    """A writer that renames a chapter and leaves the tree behind (an older pipeline, a
    manual fix) must not send readers to the old chapter."""
    db.sql(TREE)
    db.sql(f"UPDATE chunks SET chapter_key = 'q4b' WHERE document_id = '{DOC}' AND chapter_key = 'q4'")

    toc = await get_document_toc(DOC, user=USER)

    assert toc.contents is None
    assert [c.chapter_key for c in toc.chapters] == ["q1", "q2", "q3", "q4b"]


async def test_a_heading_whose_passage_moved_chapters_withdraws_the_tree(db):
    db.sql(TREE)
    db.sql(f"UPDATE chunks SET anchor = 'q1/a2-old' WHERE document_id = '{DOC}' AND anchor = 'q1/a2'")
    assert (await get_document_toc(DOC, user=USER)).contents is None


def _rejects(db, values: str) -> bool:
    result = subprocess.run(
        [*db.psql_args()], capture_output=True, text=True, timeout=30,
        input=f"""INSERT INTO document_contents (document_id, ordinal, parent_ordinal, depth,
                  node_key, kind, label, short_label, chapter_key) VALUES {values};""")
    return result.returncode != 0


async def test_the_table_enforces_a_pre_ordered_tree(db):
    row = "('{doc}', {o}, {p}, {d}, '{k}', 'part', 'L', 'L', 'q1')"
    db.sql("INSERT INTO document_contents (document_id, ordinal, parent_ordinal, depth, "
           "node_key, kind, label, short_label, chapter_key) VALUES "
           + row.format(doc=DOC, o=1, p="NULL", d=0, k="root"))
    assert _rejects(db, row.format(doc=DOC, o=2, p=3, d=1, k="child-before-parent"))
    assert _rejects(db, row.format(doc=DOC, o=2, p=9, d=0, k="parent-missing"))
    assert _rejects(db, row.format(doc=DOC, o=2, p="NULL", d=1, k="root-with-depth"))
    assert _rejects(db, row.format(doc=DOC, o=2, p=1, d=0, k="child-without-depth"))
    assert _rejects(db, row.format(doc=DOC, o=2, p="NULL", d=0, k="root"))  # duplicate key
    assert not _rejects(db, row.format(doc=DOC, o=2, p=1, d=1, k="child"))


async def test_deleting_the_document_removes_its_tree(db):
    db.sql(TREE)
    db.sql(f"DELETE FROM documents WHERE id = '{DOC}'")
    assert db.sql("SELECT count(*) FROM document_contents") == [["0"]]


async def test_the_table_is_closed_to_the_data_api(db):
    assert db.sql("SELECT relrowsecurity FROM pg_class WHERE relname = 'document_contents'") == [["t"]]
    assert db.sql("""
        SELECT bool_or(has_table_privilege(r.rolname, 'document_contents',
                                           'SELECT,INSERT,UPDATE,DELETE'))
        FROM pg_roles r WHERE r.rolname IN ('anon', 'authenticated')
    """) == [["f"]]
