"""Exercise the document outline migrations (0037 schema, 0038 backfill) against an
isolated local PostgreSQL cluster.

The outline replaces three per-request derivations in routes/documents.py, so these
tests hold it to exactly what those queries returned: the TOC's grouped chapter list,
the reader's ordered chapter keys, and the passage count.
"""

import subprocess
import time

import pytest

from tests.pg_cluster import CORPUS_SCHEMA, MIGRATIONS, local_cluster

SCHEMA_MIGRATION = MIGRATIONS / "0037_document_outline.sql"
BACKFILL_MIGRATION = MIGRATIONS / "0038_backfill_document_outline.sql"

# The pre-outline derivations, verbatim from routes/documents.py.
LEGACY_TOC = """
    SELECT chapter_key, chapter_label
    FROM chunks WHERE document_id = '{doc}' AND chapter_key IS NOT NULL
    GROUP BY chapter_key, chapter_label
    ORDER BY min(position)
"""
LEGACY_COUNT = "SELECT count(*) FROM chunks WHERE document_id = '{doc}'"

DOC_A = "00000000-0000-0000-0000-00000000000a"
DOC_B = "00000000-0000-0000-0000-00000000000b"
DOC_EMPTY = "00000000-0000-0000-0000-0000000000ee"
DOC_UNCHAPTERED = "00000000-0000-0000-0000-0000000000cc"


# DOC_A: chapter "c2" is split around "c3" (non-contiguous, as 31 production keys are),
# and one passage has no chapter. DOC_B: a single chapter. DOC_EMPTY: no passages.
SEED = f"""
    INSERT INTO documents (id, collection, title) VALUES
        ('{DOC_A}', 'summa', 'A'), ('{DOC_B}', 'bible', 'B'), ('{DOC_EMPTY}', 'bible', 'E');
    INSERT INTO chunks (document_id, position, chapter_key, chapter_label) VALUES
        ('{DOC_A}', 0, 'c1', 'Chapter 1'),
        ('{DOC_A}', 1, 'c1', 'Chapter 1'),
        ('{DOC_A}', 2, 'c2', 'Chapter 2'),
        ('{DOC_A}', 3, 'c3', 'Chapter 3'),
        ('{DOC_A}', 4, 'c2', 'Chapter 2'),
        ('{DOC_A}', 5, NULL, NULL),
        ('{DOC_B}', 0, 'b1', 'Book 1');
"""


@pytest.fixture()
def postgres():
    with local_cluster("tc-outline-") as cluster:
        cluster.sql(CORPUS_SCHEMA)
        yield cluster


def _migrate(sql):
    sql(SCHEMA_MIGRATION.read_text())
    sql(BACKFILL_MIGRATION.read_text())


def _outline(sql, doc):
    return sql(f"""
        SELECT chapter_key, coalesce(chapter_label, '<null>') FROM document_chapters
        WHERE document_id = '{doc}' ORDER BY ordinal
    """)


def _legacy_toc(sql, doc):
    return [[key, label or "<null>"] for key, label in sql(LEGACY_TOC.format(doc=doc))]


def _chunk_count(sql, doc):
    return sql(f"SELECT coalesce(chunk_count::text, '<null>') FROM documents WHERE id = '{doc}'")[0][0]


def test_backfill_reproduces_the_legacy_toc_and_count(postgres):
    postgres(SEED)
    _migrate(postgres)

    for doc in (DOC_A, DOC_B, DOC_EMPTY):
        assert _outline(postgres, doc) == _legacy_toc(postgres, doc)
        assert _chunk_count(postgres, doc) == postgres(LEGACY_COUNT.format(doc=doc))[0][0]

    # Spelled out for the non-contiguous case: c2 is ordered by its first passage.
    assert _outline(postgres, DOC_A) == [
        ["c1", "Chapter 1"], ["c2", "Chapter 2"], ["c3", "Chapter 3"],
    ]
    # The unchaptered passage counts toward chunk_count but is not a chapter.
    assert _chunk_count(postgres, DOC_A) == "6"
    assert _chunk_count(postgres, DOC_EMPTY) == "0"


def test_the_schema_migration_alone_leaves_every_document_to_the_fallback(postgres):
    postgres(SEED)
    postgres(SCHEMA_MIGRATION.read_text())

    for doc in (DOC_A, DOC_B, DOC_EMPTY):
        assert _chunk_count(postgres, doc) == "<null>"
        assert _outline(postgres, doc) == []

    postgres(BACKFILL_MIGRATION.read_text())
    postgres(BACKFILL_MIGRATION.read_text())  # idempotent

    for doc in (DOC_A, DOC_B, DOC_EMPTY):
        assert _outline(postgres, doc) == _legacy_toc(postgres, doc)
    assert _chunk_count(postgres, DOC_A) == "6"


def test_passages_without_chapters_count_but_list_no_chapters(postgres):
    postgres(f"""
        INSERT INTO documents (id, collection, title) VALUES ('{DOC_UNCHAPTERED}', 'medieval', 'U');
        INSERT INTO chunks (document_id, position) VALUES
            ('{DOC_UNCHAPTERED}', 0), ('{DOC_UNCHAPTERED}', 1);
    """)
    _migrate(postgres)

    assert _chunk_count(postgres, DOC_UNCHAPTERED) == "2"
    assert _outline(postgres, DOC_UNCHAPTERED) == []


def test_ordinals_are_dense_and_one_based(postgres):
    postgres(SEED)
    _migrate(postgres)

    ordinals = postgres(f"""
        SELECT ordinal FROM document_chapters WHERE document_id = '{DOC_A}' ORDER BY ordinal
    """)
    assert ordinals == [["1"], ["2"], ["3"]]


def test_a_document_is_null_until_refreshed(postgres):
    _migrate(postgres)
    postgres(SEED)

    # Written after the backfill and not yet refreshed: the API's fallback signal.
    assert _chunk_count(postgres, DOC_A) == "<null>"
    assert _outline(postgres, DOC_A) == []

    postgres(f"SELECT refresh_document_outline('{DOC_A}')")
    assert _outline(postgres, DOC_A) == _legacy_toc(postgres, DOC_A)
    assert _chunk_count(postgres, DOC_A) == "6"


def test_refresh_replaces_the_previous_outline(postgres):
    postgres(SEED)
    _migrate(postgres)

    # A republication renumbers and relabels: c3 moves to the front, c1 disappears.
    postgres(f"""
        DELETE FROM chunks WHERE document_id = '{DOC_A}' AND chapter_key = 'c1';
        UPDATE chunks SET position = -1, chapter_label = 'Third'
            WHERE document_id = '{DOC_A}' AND chapter_key = 'c3';
        SELECT refresh_document_outline('{DOC_A}');
        SELECT refresh_document_outline('{DOC_A}');
    """)

    assert _outline(postgres, DOC_A) == [["c3", "Third"], ["c2", "Chapter 2"]]
    assert _outline(postgres, DOC_A) == _legacy_toc(postgres, DOC_A)
    assert _chunk_count(postgres, DOC_A) == "4"
    # The other document's outline is untouched.
    assert _outline(postgres, DOC_B) == [["b1", "Book 1"]]


def test_the_first_passage_label_names_the_chapter(postgres):
    postgres(f"""
        INSERT INTO documents (id, collection, title) VALUES ('{DOC_A}', 'summa', 'A');
        INSERT INTO chunks (document_id, position, chapter_key, chapter_label) VALUES
            ('{DOC_A}', 1, 'c1', 'Later label'),
            ('{DOC_A}', 0, 'c1', 'First label');
    """)
    _migrate(postgres)

    assert _outline(postgres, DOC_A) == [["c1", "First label"]]


def test_deleting_a_document_removes_its_outline(postgres):
    postgres(SEED)
    _migrate(postgres)

    postgres(f"DELETE FROM documents WHERE id = '{DOC_A}'")

    assert postgres(f"SELECT count(*) FROM document_chapters WHERE document_id = '{DOC_A}'") == [["0"]]
    assert _outline(postgres, DOC_B) == [["b1", "Book 1"]]


def test_outline_is_closed_to_the_data_api(postgres):
    _migrate(postgres)

    rows = postgres("""
        SELECT r.rolname,
               has_table_privilege(r.rolname, 'document_chapters', 'SELECT'),
               has_function_privilege(r.rolname, 'refresh_document_outline(uuid)', 'EXECUTE')
        FROM pg_roles r WHERE r.rolname IN ('anon', 'authenticated') ORDER BY r.rolname
    """)
    assert rows == [["anon", "f", "f"], ["authenticated", "f", "f"]]
    assert postgres(
        "SELECT relrowsecurity FROM pg_class WHERE relname = 'document_chapters'"
    ) == [["t"]]


def test_a_publish_and_the_backfill_do_not_deadlock(postgres):
    """write_document locks the document row, then refreshes; the backfill must agree.

    Session 1 plays write_document: it holds DOC_A's row (its upsert) while it writes
    chunks, then refreshes. Session 2 runs the backfill meanwhile and reaches DOC_A
    first. Refreshing chapters before locking the document row deadlocks the two.
    """
    postgres(SEED)
    postgres(SCHEMA_MIGRATION.read_text())

    def session(source):
        process = subprocess.Popen(
            postgres.psql_args(),
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        process.stdin.write(source)
        process.stdin.close()
        return process

    publish = session(f"""
        BEGIN;
        UPDATE documents SET title = title WHERE id = '{DOC_A}';
        SELECT pg_sleep(1.5);
        SELECT refresh_document_outline('{DOC_A}');
        COMMIT;
    """)
    # Start the backfill only once the publish holds DOC_A's row and is "writing
    # chunks" (its pg_sleep); otherwise the test would not exercise the contention.
    deadline = time.monotonic() + 10
    while postgres("""
        SELECT count(*) FROM pg_stat_activity
        WHERE state = 'active' AND query LIKE '%pg_sleep(1.5)%' AND pid <> pg_backend_pid()
    """) != [["1"]]:
        assert time.monotonic() < deadline, "publish session never reached its hold"
        time.sleep(0.05)
    backfill = session(BACKFILL_MIGRATION.read_text())

    for process in (publish, backfill):
        process.wait(timeout=30)
        assert process.returncode == 0, process.stderr.read()
    assert _outline(postgres, DOC_A) == _legacy_toc(postgres, DOC_A)
