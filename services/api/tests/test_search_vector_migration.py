"""Exercise corpus cleanup 2.2c's migration (the search_vector rebuild, C-16) against an
isolated local PostgreSQL cluster.

The acceptance checks are docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.2c:
`fts.no_marker_tokens`, `fts.reference_lookup`, and the recreated staging table carrying
the new expression. The migration changes the expression in place on PostgreSQL 17 and
drops and re-adds the column on 12 to 16; these tests run whichever path the local
server takes and check the result is the same.
"""

import subprocess

import pytest

from tests.pg_cluster import MIGRATIONS, local_cluster
from tests.test_corpus_facts_migration import EARLIER, PRODUCTION_SCHEMA, STAGED_TABLES

MIGRATION = MIGRATIONS / "0045_search_vector_markers_and_reference.sql"
BEFORE = (*EARLIER, "0042_corpus_facts_retirement_staging.sql",
          "0043_validate_corpus_facts.sql", "0044_document_form.sql")

# The query retrieve_fts.py runs, without its collection filter and limit.
SEARCH = """
    SELECT c.anchor FROM chunks c
    WHERE c.search_vector @@ plainto_tsquery('english', $q${q}$q$)
    ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $q${q}$q$)) DESC, c.anchor
"""

CANON = "00000000-0000-0000-0000-0000000000c1"
CCC = "00000000-0000-0000-0000-0000000000c2"
BIBLE = "00000000-0000-0000-0000-0000000000c3"
FATHERS = "00000000-0000-0000-0000-0000000000c4"

# References as the live corpus writes them (snapshot 2026-10-31).
SEED = f"""
    INSERT INTO documents (id, collection, title) VALUES
        ('{CANON}', 'canon-law', 'Code of Canon Law'),
        ('{CCC}', 'catechism', 'Catechism of the Catholic Church'),
        ('{BIBLE}', 'bible', 'John'),
        ('{FATHERS}', 'church-fathers', 'On Nature and Grace');
    INSERT INTO chunks (document_id, position, anchor, reference, content) VALUES
        ('{CANON}', 0, 'can/1055', 'Code of Canon Law, Can. 1055',
         '§1. The matrimonial covenant, by which a man and a woman establish between
          themselves a partnership of the whole of life'),
        ('{CANON}', 1, 'can/1056', 'Code of Canon Law, Can. 1056',
         'The essential properties of marriage are unity and indissolubility'),
        ('{CCC}', 0, 'ccc/2263', 'CCC §2263–2267 (part)',
         'The legitimate defense of persons and societies is not an exception'),
        ('{CCC}', 1, 'ccc/2268', 'CCC §2268–2269',
         'The fifth commandment forbids direct and intentional killing'),
        ('{BIBLE}', 0, 'john/3/1', 'John 3:1–21',
         'Now there was a man of the Pharisees named Nicodemus. {{{{v:16}}}} For God so
          loved the world'),
        ('{BIBLE}', 1, 'psalms/23/1', 'Psalms 23:1–6',
         'The LORD is my shepherd; I shall lack nothing. {{{{v:2}}}} He makes me lie down'),
        -- 1 Maccabees 2 names John and carries the markers 3 and 16, so before the
        -- rebuild it answered "John 3:16" (C-16).
        ('{BIBLE}', 2, '1-maccabees/2/1', '1 Maccabees 2:1–14',
         'In those days Mattathias arose {{{{v:2}}}} He had five sons, John {{{{v:3}}}}
          Simon {{{{v:16}}}} and many of Israel came'),
        -- "grace" in the text of one passage, and only in the citation of another.
        ('{FATHERS}', 0, 'grace/text', 'Augustine — Letters, 1.',
         'Grace is not given according to our merits'),
        ('{FATHERS}', 1, 'grace/citation', 'Augustine — On Nature and Grace, 2.',
         'The sins of the will are not of nature');
"""

NEW_EXPRESSION_PARTS = ("regexp_replace", "setweight", "'A'", "'B'", "reference")


@pytest.fixture()
def postgres():
    with local_cluster("tc-fts-") as cluster:
        cluster.sql(PRODUCTION_SCHEMA)
        cluster.sql(SEED)
        cluster.migrate(*BEFORE)
        yield cluster


@pytest.fixture()
def migrated(postgres):
    """After the migration and the staging recreate that 4.0's window runs with it."""
    postgres.migrate(MIGRATION.name)
    postgres("SELECT drop_corpus_staging(); SELECT create_corpus_staging();")
    return postgres


def _search(cluster, query: str) -> list[str]:
    return [row[0] for row in cluster(SEARCH.format(q=query))]


def _expression(cluster, schema: str) -> str:
    """The column's generation expression. Read without Cluster.sql, which splits rows
    on the "|" the expression's || contains."""
    result = subprocess.run(
        [*cluster.psql_args(), "-A", "-t"],
        input=f"""SELECT generation_expression FROM information_schema.columns
                  WHERE table_schema = '{schema}' AND table_name = 'chunks'
                    AND column_name = 'search_vector'""",
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _server_version(cluster) -> int:
    return int(cluster("SHOW server_version_num")[0][0])


# --- before: the defect ------------------------------------------------------------------

def test_before_the_rebuild_markers_are_words_and_references_are_not(postgres):
    assert "1-maccabees/2/1" in _search(postgres, "john 3 16")
    assert _search(postgres, "canon 1055") == []
    assert _search(postgres, "ccc 2267") == []


# --- fts.no_marker_tokens -----------------------------------------------------------------

def test_no_marker_tokens(migrated):
    assert migrated("""
        SELECT count(*) FROM chunks, unnest(search_vector) AS t
        WHERE t.lexeme = 'v'
    """) == [["0"]]
    # 16 is only ever a marker in John 3 (its reference is 3:1–21).
    assert migrated("""
        SELECT array_agg(t.lexeme ORDER BY t.lexeme) FROM chunks, unnest(search_vector) AS t
        WHERE anchor = 'john/3/1' AND t.lexeme ~ '^[0-9]+$'
    """) == [["{1,21,3}"]]
    assert "1-maccabees/2/1" not in _search(migrated, "john 3 16")


def test_content_keeps_weight_a_and_the_reference_weight_b(migrated):
    assert migrated("""
        SELECT array_agg(DISTINCT w ORDER BY w) FROM chunks, unnest(search_vector) AS t,
            unnest(t.weights) AS w
        WHERE anchor = 'can/1055' AND t.lexeme = 'woman'
    """) == [["{A}"]]
    assert migrated("""
        SELECT array_agg(DISTINCT w ORDER BY w) FROM chunks, unnest(search_vector) AS t,
            unnest(t.weights) AS w
        WHERE anchor = 'can/1055' AND t.lexeme = '1055'
    """) == [["{B}"]]


# --- fts.reference_lookup -----------------------------------------------------------------

def test_reference_lookup(migrated):
    assert _search(migrated, "canon 1055") == ["can/1055"]
    assert _search(migrated, "ccc 2267") == ["ccc/2263"]
    assert _search(migrated, "CCC 2269") == ["ccc/2268"]
    assert _search(migrated, "john 3") == ["john/3/1"]
    assert _search(migrated, "psalm 23") == ["psalms/23/1"]


def test_a_content_match_ranks_above_a_reference_only_match(migrated):
    assert _search(migrated, "grace") == ["grace/text", "grace/citation"]


def test_a_row_written_after_the_rebuild_gets_the_new_vector(migrated):
    migrated(f"""
        INSERT INTO chunks (document_id, position, anchor, reference, content)
        VALUES ('{CANON}', 2, 'can/1057', 'Code of Canon Law, Can. 1057',
                'Consent {{{{v:9}}}} makes marriage')
    """)
    assert _search(migrated, "canon 1057") == ["can/1057"]
    assert _search(migrated, "v 9") == []


# --- shape ----------------------------------------------------------------------------

def test_the_column_and_its_index_are_rebuilt(postgres):
    def position():
        return postgres("""
            SELECT ordinal_position FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'chunks'
              AND column_name = 'search_vector'
        """)[0][0]

    before = position()
    postgres.migrate(MIGRATION.name)

    expression = _expression(postgres, "public")
    assert all(part in expression for part in NEW_EXPRESSION_PARTS), expression
    assert postgres("""
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'chunks' AND indexdef LIKE '%search_vector%'
    """) == [["CREATE INDEX chunks_search_vector_idx ON public.chunks "
              "USING gin (search_vector)"]]
    if _server_version(postgres) >= 170000:
        assert position() == before  # SET EXPRESSION keeps the column in place
    else:
        assert int(position()) > int(before)  # dropped and added at the end
    assert postgres("SELECT count(*) FROM chunks WHERE search_vector IS NULL") == [["0"]]


def test_no_other_column_or_index_changes(postgres):
    def shape():
        columns = postgres("""
            SELECT column_name, data_type, is_nullable, coalesce(column_default, ''),
                   coalesce(generation_expression, '')
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'chunks'
              AND column_name <> 'search_vector' ORDER BY column_name
        """)
        indexes = postgres("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                           "AND tablename = 'chunks' ORDER BY 1")
        constraints = postgres("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                               "WHERE conrelid = 'public.chunks'::regclass ORDER BY 1")
        return columns, indexes, constraints

    before = shape()
    content = postgres("SELECT md5(string_agg(id::text || content || coalesce(reference, ''), "
                       "'|' ORDER BY id)) FROM chunks")
    postgres.migrate(MIGRATION.name)
    assert shape() == before
    assert postgres("SELECT md5(string_agg(id::text || content || coalesce(reference, ''), "
                    "'|' ORDER BY id)) FROM chunks") == content


def test_the_outline_is_left_alone(postgres):
    postgres("SELECT refresh_document_outline(id) FROM documents")
    counts = postgres("SELECT id, chunk_count FROM documents ORDER BY id")
    postgres.migrate(MIGRATION.name)
    assert postgres("SELECT id, chunk_count FROM documents ORDER BY id") == counts


def test_the_timeouts_end_with_the_migration(postgres):
    result = subprocess.run(
        postgres.psql_args() + ["-A", "-t"],
        input=f"BEGIN;\n{MIGRATION.read_text()}\nCOMMIT;\n"
              "SHOW lock_timeout; SHOW statement_timeout;",
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[-2:] == ["0", "0"]


# --- staging ---------------------------------------------------------------------------

def test_staging_made_before_the_migration_keeps_the_old_expression(postgres):
    """Why 4.0's window recreates staging: 0043 made it, and nothing here touches it."""
    postgres.migrate(MIGRATION.name)
    assert "regexp_replace" not in _expression(postgres, "staging")


def test_recreated_staging_carries_the_new_expression(migrated):
    assert _expression(migrated, "staging") == _expression(migrated, "public")
    for table in STAGED_TABLES:
        assert migrated(f"""
            SELECT column_name, data_type, is_generated, coalesce(generation_expression, '')
            FROM information_schema.columns
            WHERE table_schema = 'staging' AND table_name = '{table}' ORDER BY ordinal_position
        """) == migrated(f"""
            SELECT column_name, data_type, is_generated, coalesce(generation_expression, '')
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = '{table}' ORDER BY ordinal_position
        """), table
    migrated(f"""
        INSERT INTO staging.chunks (document_id, position, anchor, reference, content)
        VALUES ('{CANON}', 0, 'can/1055', 'Code of Canon Law, Can. 1055', 'covenant')
    """)
    assert migrated("SELECT anchor FROM staging.chunks "
                    "WHERE search_vector @@ plainto_tsquery('english', 'canon 1055')"
                    ) == [["can/1055"]]
    assert migrated("SELECT indexdef FROM pg_indexes WHERE schemaname = 'staging' "
                    "AND tablename = 'chunks' AND indexdef LIKE '%search_vector%'"
                    ) == [["CREATE INDEX chunks_search_vector_idx ON staging.chunks "
                           "USING gin (search_vector)"]]


def test_the_post_cutover_check_finds_no_stale_row(migrated):
    """4.2's check: every row's vector equals the new expression computed afresh."""
    expression = _expression(migrated, "public")
    assert migrated(f"SELECT count(*) FROM chunks WHERE search_vector IS DISTINCT FROM "
                    f"({expression})") == [["0"]]
