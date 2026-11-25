"""Exercise corpus cleanup 2.2a's migrations (0042 schema, 0043 validation and staging)
against an isolated local PostgreSQL cluster.

The acceptance checks are docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.2a,
plus the staging coverage of 0040 (document_contents) and 0041 (reader_access).
"""

import ast
import re
import runpy
import subprocess
from pathlib import Path

import pytest

from tests.pg_cluster import MIGRATIONS, local_cluster

SCHEMA_MIGRATION = MIGRATIONS / "0042_corpus_facts_retirement_staging.sql"
VALIDATE_MIGRATION = MIGRATIONS / "0043_validate_corpus_facts.sql"
EARLIER = ("0037_document_outline.sql", "0038_backfill_document_outline.sql",
           "0040_document_contents.sql", "0041_document_reader_access.sql")
REGISTRY = Path(__file__).parents[3] / "datapipeline/registry"

# The corpus tables as production has them (information_schema and pg_indexes, read
# 2 Nov 2026), before 0037: every column except the two pgvector columns, which are
# unused and need an extension the local cluster lacks, and every index on them. Plus
# Supabase's roles and the default privileges that hand new tables and functions to
# them, so the access test proves the migrations' revokes rather than an empty grant.
PRODUCTION_SCHEMA = """
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE authenticated NOLOGIN;
    GRANT USAGE ON SCHEMA public TO anon, authenticated;
    ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO anon, authenticated;
    ALTER DEFAULT PRIVILEGES GRANT ALL ON FUNCTIONS TO anon, authenticated;
    ALTER DEFAULT PRIVILEGES GRANT ALL ON SCHEMAS TO anon, authenticated;

    CREATE TABLE documents (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        collection text NOT NULL CHECK (collection = ANY (ARRAY['bible', 'catechism',
            'church-fathers', 'encyclicals', 'apostolic-exhortations', 'papal-documents',
            'canon-law', 'summa', 'medieval', 'councils'])),
        title text NOT NULL,
        author text,
        year integer,
        metadata jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        translation text NOT NULL DEFAULT '',
        UNIQUE (collection, title, translation, author)
    );
    CREATE INDEX documents_collection_idx ON documents (collection);
    CREATE TABLE chunks (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        content text NOT NULL DEFAULT '',
        position integer NOT NULL,
        reference text,
        search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
        annotation jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        metadata jsonb,
        anchor text,
        chapter_key text,
        chapter_label text,
        unit_label text,
        annotation_vector tsvector,
        UNIQUE (document_id, position)
    );
    CREATE INDEX chunks_search_vector_idx ON chunks USING gin (search_vector);
    CREATE INDEX chunks_annotation_vector_idx ON chunks USING gin (annotation_vector);
    CREATE INDEX chunks_document_id_idx ON chunks (document_id);
    CREATE INDEX chunks_document_chapter_pos_idx ON chunks (document_id, chapter_key, position);
    CREATE UNIQUE INDEX chunks_document_anchor_uniq ON chunks (document_id, anchor)
        WHERE anchor IS NOT NULL;
"""

DOC_A = "00000000-0000-0000-0000-00000000000a"
DOC_B = "00000000-0000-0000-0000-00000000000b"
CHUNK_1 = "00000000-0000-0000-0000-000000000001"
CHUNK_2 = "00000000-0000-0000-0000-000000000002"
CHUNK_3 = "00000000-0000-0000-0000-000000000003"

# DOC_A has three passages in two chapters; DOC_B one.
SEED = f"""
    INSERT INTO documents (id, collection, title) VALUES
        ('{DOC_A}', 'church-fathers', 'A'), ('{DOC_B}', 'bible', 'B');
    INSERT INTO chunks (id, document_id, position, chapter_key, chapter_label, content) VALUES
        ('{CHUNK_1}', '{DOC_A}', 0, 'c1', 'Chapter 1', 'grace and nature'),
        ('{CHUNK_2}', '{DOC_A}', 1, 'c1', 'Chapter 1', 'faith'),
        ('{CHUNK_3}', '{DOC_A}', 2, 'c2', 'Chapter 2', 'hope'),
        (gen_random_uuid(), '{DOC_B}', 0, 'b1', 'Book 1', 'charity');
"""

# The constraints 0042 adds NOT VALID to existing tables and 0043 validates.
DEFERRED_CONSTRAINTS = sorted([
    "documents_genre_fk", "documents_certainty_check", "documents_issuer_slug_check",
    "documents_superseded_by_fk", "chunks_language_check", "chunks_voice_check",
    "chunks_retired_position_range", "chunks_work_fk", "chunks_superseded_by_fk",
    "chunks_history_not_searchable",
])
STAGED_TABLES = ("documents", "chunks", "document_chapters", "document_contents",
                 "document_works", "corpus_tombstones", "corpus_redirects")
NEW_TABLES = ("corpus_genres", "document_works", "corpus_publishes", "corpus_tombstones",
              "corpus_redirects")


@pytest.fixture()
def postgres():
    with local_cluster("tc-facts-") as cluster:
        cluster.sql(PRODUCTION_SCHEMA)
        yield cluster


@pytest.fixture()
def migrated(postgres):
    postgres(SEED)
    postgres.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
    return postgres


def _fails(cluster, source: str) -> str:
    """Run SQL that must fail; return its error."""
    result = subprocess.run(cluster.psql_args(), input=source, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode != 0, f"expected failure: {source}"
    return result.stderr


def _publish(cluster, release="r-test"):
    cluster(f"INSERT INTO corpus_publishes (id, collections, qdrant_collection) "
            f"VALUES ('{release}', ARRAY['church-fathers'], 'chunks-{release}')")


def _tombstone(reason, removal_key, chunk_id=CHUNK_1):
    key = "NULL" if removal_key is None else f"'{removal_key}'"
    return f"""
        INSERT INTO corpus_tombstones (entity, id, document_id, retired_at, publish_id,
            removal_key, rule, reason_code, public_reason, snapshot)
        VALUES ('passage', '{chunk_id}', '{DOC_A}', now(), 'r-test', {key}, 'other',
            '{reason}', 'Removed.', '{{}}');
    """


def _chunk_count(sql, doc):
    return sql(f"SELECT coalesce(chunk_count::text, '<null>') FROM documents WHERE id = '{doc}'")[0][0]


def _registry_tuple(name: str) -> tuple[str, ...]:
    """A tuple constant from registry/__init__.py, read as text, not imported."""
    tree = ast.parse((REGISTRY / "__init__.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = ast.literal_eval(node.value)
            return value if isinstance(value, tuple) else (value,)
    raise AssertionError(f"{name} not found in registry/__init__.py")


def _all_genres() -> tuple[str, ...]:
    # genres.py imports nothing but __future__; running it as a file keeps the API
    # suite free of datapipeline imports.
    return runpy.run_path(str(REGISTRY / "genres.py"))["ALL_GENRES"]


# --- existing rows -----------------------------------------------------------------------

def test_existing_rows_are_live_and_searchable(migrated):
    assert migrated("""
        SELECT count(*), count(*) FILTER (WHERE retired_at IS NULL AND searchable),
               count(*) FILTER (WHERE voice IS NULL AND language IS NULL AND work_key IS NULL
                                AND superseded_by IS NULL)
        FROM chunks
    """) == [["4", "4", "4"]]
    assert migrated("SELECT count(*) FILTER (WHERE retired_at IS NULL), count(*) FROM documents"
                    ) == [["2", "2"]]


def test_reader_access_is_untouched(migrated):
    assert migrated("SELECT DISTINCT reader_access FROM documents") == [["full"]]


def test_the_outline_is_unchanged_while_nothing_is_retired(postgres):
    postgres(SEED)
    postgres.migrate(*EARLIER)
    before = postgres("SELECT document_id, ordinal, chapter_key, chapter_label "
                      "FROM document_chapters ORDER BY 1, 2")
    counts = postgres("SELECT id, chunk_count FROM documents ORDER BY 1")

    postgres.migrate(SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
    for doc in (DOC_A, DOC_B):
        postgres(f"SELECT refresh_document_outline('{doc}')")

    assert postgres("SELECT document_id, ordinal, chapter_key, chapter_label "
                    "FROM document_chapters ORDER BY 1, 2") == before
    assert postgres("SELECT id, chunk_count FROM documents ORDER BY 1") == counts


# --- passage fields ----------------------------------------------------------------------

def test_voice_accepts_only_rejected(migrated):
    migrated(f"UPDATE chunks SET voice = 'rejected' WHERE id = '{CHUNK_1}'")
    assert "chunks_voice_check" in _fails(
        migrated, f"UPDATE chunks SET voice = 'heretic' WHERE id = '{CHUNK_2}'")


def test_language_is_an_iso_code(migrated):
    migrated(f"UPDATE chunks SET language = 'la' WHERE id = '{CHUNK_1}'")
    migrated(f"UPDATE chunks SET language = 'grc' WHERE id = '{CHUNK_2}'")
    assert "chunks_language_check" in _fails(
        migrated, f"UPDATE chunks SET language = 'Latin' WHERE id = '{CHUNK_3}'")


def test_history_passage_links_and_is_not_searchable(migrated):
    assert "chunks_history_not_searchable" in _fails(
        migrated, f"UPDATE chunks SET superseded_by = '{CHUNK_1}' WHERE id = '{CHUNK_2}'")
    migrated(f"UPDATE chunks SET superseded_by = '{CHUNK_1}', searchable = false "
             f"WHERE id = '{CHUNK_2}'")


def test_deleting_the_current_passage_clears_the_history_link(migrated):
    migrated(f"UPDATE chunks SET superseded_by = '{CHUNK_1}', searchable = false "
             f"WHERE id = '{CHUNK_2}'")
    migrated(f"DELETE FROM chunks WHERE id = '{CHUNK_1}'")
    assert migrated(f"SELECT superseded_by IS NULL FROM chunks WHERE id = '{CHUNK_2}'") == [["t"]]


def test_the_history_link_is_indexed_for_deletes(migrated):
    # ON DELETE SET NULL looks up `superseded_by = $1` for every deleted chunk.
    migrated("SET enable_seqscan = off")
    plan = migrated("""
        SET enable_seqscan = off;
        EXPLAIN SELECT 1 FROM chunks WHERE superseded_by = gen_random_uuid();
    """)
    assert "chunks_superseded_by_idx" in " ".join(row[0] for row in plan)


def test_work_key_must_name_a_work_of_the_document(migrated):
    assert "chunks_work_fk" in _fails(
        migrated, f"UPDATE chunks SET work_key = 'sectional-confession' WHERE id = '{CHUNK_1}'")
    migrated(f"""
        INSERT INTO document_works (document_id, work_key, ordinal, title, certainty, genre)
        VALUES ('{DOC_A}', 'sectional-confession', 1, 'A Sectional Confession of Faith',
                'pseudonymous', 'treatise');
        UPDATE chunks SET work_key = 'sectional-confession' WHERE id = '{CHUNK_1}';
    """)
    # A work of one document cannot hold another document's passage.
    assert "chunks_work_fk" in _fails(
        migrated, f"UPDATE chunks SET work_key = 'sectional-confession' "
                  f"WHERE document_id = '{DOC_B}'")


# --- document facts ----------------------------------------------------------------------

def test_genre_accepts_only_the_d5_vocabulary(migrated):
    for genre in _all_genres():
        migrated(f"UPDATE documents SET genre = '{genre}' WHERE id = '{DOC_A}'")
    for bad in ("apostolic exhortation", "essay"):
        assert "documents_genre_fk" in _fails(
            migrated, f"UPDATE documents SET genre = '{bad}' WHERE id = '{DOC_A}'")


def test_genre_seed_matches_registry_module(migrated):
    # 0042's seed, less the genres a later migration deleted (0044 moved `bull` to
    # corpus_forms), is the module's list in order.
    text = SCHEMA_MIGRATION.read_text()
    values = text.split("INSERT INTO corpus_genres (key) VALUES", 1)[1].split(";", 1)[0]
    deleted = set(re.findall(r"DELETE FROM corpus_genres WHERE key = '([a-z-]+)'",
                             (MIGRATIONS / "0044_document_form.sql").read_text()))
    seeded = tuple(g for g in re.findall(r"\('([a-z-]+)'\)", values) if g not in deleted)
    assert seeded == _all_genres()
    migrated.migrate("0044_document_form.sql")
    assert [r[0] for r in migrated("SELECT key FROM corpus_genres ORDER BY key")] == sorted(
        _all_genres())


def test_issuer_is_a_slug_and_label_is_free_text(migrated):
    migrated(f"UPDATE documents SET issuer = 'pope-leo-xiii', issuer_label = 'Pope Leo XIII' "
             f"WHERE id = '{DOC_A}'")
    assert "documents_issuer_slug_check" in _fails(
        migrated, f"UPDATE documents SET issuer = 'Pope Leo XIII' WHERE id = '{DOC_A}'")


def test_certainty_uses_the_registry_list(migrated):
    for certainty in _registry_tuple("CERTAINTIES"):
        migrated(f"UPDATE documents SET certainty = '{certainty}' WHERE id = '{DOC_A}'")
    assert "documents_certainty_check" in _fails(
        migrated, f"UPDATE documents SET certainty = 'spurious' WHERE id = '{DOC_A}'")


def test_superseded_document_link(migrated):
    migrated(f"UPDATE documents SET superseded_by = '{DOC_B}', "
             f"superseded_note = 'Superseded.' WHERE id = '{DOC_A}'")
    assert "documents_superseded_by_fk" in _fails(
        migrated, f"UPDATE documents SET superseded_by = gen_random_uuid() WHERE id = '{DOC_B}'")


# --- retirement and the outline ----------------------------------------------------------

def test_outline_excludes_retired_rows(migrated):
    migrated(f"""
        UPDATE chunks SET retired_at = now(), position = -1000000 WHERE id = '{CHUNK_3}';
        SELECT refresh_document_outline('{DOC_A}');
    """)
    assert _chunk_count(migrated, DOC_A) == "2"
    assert migrated(f"SELECT chapter_key FROM document_chapters WHERE document_id = '{DOC_A}' "
                    f"ORDER BY ordinal") == [["c1"]]


def test_retiring_a_row_invalidates_the_outline(migrated):
    assert _chunk_count(migrated, DOC_A) == "3"
    migrated(f"UPDATE chunks SET retired_at = now(), position = -1000000 WHERE id = '{CHUNK_3}'")
    assert _chunk_count(migrated, DOC_A) == "<null>"
    assert _chunk_count(migrated, DOC_B) == "1"


def test_unretiring_a_row_invalidates_the_outline(migrated):
    migrated(f"""
        UPDATE chunks SET retired_at = now(), position = -1000000 WHERE id = '{CHUNK_3}';
        SELECT refresh_document_outline('{DOC_A}');
    """)
    migrated(f"UPDATE chunks SET retired_at = NULL, position = 2 WHERE id = '{CHUNK_3}'")
    assert _chunk_count(migrated, DOC_A) == "<null>"


def test_non_structural_updates_still_leave_the_outline_alone(migrated):
    migrated(f"UPDATE chunks SET searchable = false, note = 'n', voice = 'rejected' "
             f"WHERE document_id = '{DOC_A}'")
    assert _chunk_count(migrated, DOC_A) == "3"


def test_retired_row_must_leave_the_live_position_range(migrated):
    assert "chunks_retired_position_range" in _fails(
        migrated, f"UPDATE chunks SET retired_at = now() WHERE id = '{CHUNK_3}'")
    # Temporary positions (-position - 1) are still live positions.
    assert "chunks_retired_position_range" in _fails(
        migrated, f"UPDATE chunks SET retired_at = now(), position = -999999 WHERE id = '{CHUNK_3}'")


# --- tombstones, redirects and publishes -------------------------------------------------

def test_tombstone_reason_uses_registry_list(migrated):
    _publish(migrated)
    reasons = _registry_tuple("REMOVAL_REASONS")
    rolled_back = _registry_tuple("ROLLED_BACK")
    for i, reason in enumerate(reasons):
        migrated(_tombstone(reason, f"entry-{i}", f"00000000-0000-0000-0001-{i:012d}"))
    migrated(_tombstone(rolled_back[0], None))

    assert "check" in _fails(migrated, _tombstone("condemned_by_name", "entry-x", CHUNK_2))
    # rolled-back requires a NULL removal_key, and every other reason requires one.
    assert "check" in _fails(migrated, _tombstone("rolled-back", "entry-x", CHUNK_2))
    assert "check" in _fails(migrated, _tombstone("rule-a", None, CHUNK_2))


def test_tombstone_check_lists_exactly_the_registry_reasons(migrated):
    definition = migrated("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid = 'corpus_tombstones'::regclass AND conname = 'corpus_tombstones_reason_code_check'
    """)[0][0]
    listed = tuple(re.findall(r"'([a-z-]+)'::text", definition))
    assert listed == _registry_tuple("REMOVAL_REASONS") + _registry_tuple("ROLLED_BACK")


def test_tombstones_outlive_their_rows(migrated):
    _publish(migrated)
    migrated(_tombstone("rule-a", "entry-1"))
    migrated(f"DELETE FROM documents WHERE id = '{DOC_A}'")
    assert migrated("SELECT count(*) FROM corpus_tombstones") == [["1"]]


def test_redirect_kind_uses_remap_vocabulary(migrated):
    _publish(migrated)
    insert = ("INSERT INTO corpus_redirects (entity, old_id, old_document_id, new_id, "
              "new_document_id, kind, publish_id) VALUES ('passage', gen_random_uuid(), "
              f"'{DOC_A}', '{CHUNK_1}', '{DOC_A}', '{{kind}}', 'r-test')")
    assert _registry_tuple("REDIRECT_KINDS") == ("moved", "split", "merged", "renumbered")
    for kind in _registry_tuple("REDIRECT_KINDS"):
        migrated(insert.format(kind=kind))
    for bad in ("same", "removed", "rewritten"):
        assert "check" in _fails(migrated, insert.format(kind=bad))


def test_redirect_anchor_and_chapter_rows_have_no_old_id(migrated):
    _publish(migrated)
    for entity in ("anchor", "chapter"):
        migrated(f"""
            INSERT INTO corpus_redirects (entity, old_document_id, old_anchor, new_document_id,
                new_anchor, kind, publish_id)
            VALUES ('{entity}', '{DOC_A}', 'old', '{DOC_A}', 'new', 'moved', 'r-test')
        """)
        assert "check" in _fails(migrated, f"""
            INSERT INTO corpus_redirects (entity, old_id, old_document_id, old_anchor,
                new_document_id, new_anchor, kind, publish_id)
            VALUES ('{entity}', gen_random_uuid(), '{DOC_A}', 'x', '{DOC_A}', 'y', 'moved', 'r-test')
        """)
    # Passage and document rows need one, and an old identity redirects once.
    assert "check" in _fails(migrated, f"""
        INSERT INTO corpus_redirects (entity, old_document_id, new_id, new_document_id, kind,
            publish_id)
        VALUES ('passage', '{DOC_A}', '{CHUNK_1}', '{DOC_A}', 'moved', 'r-test')
    """)
    migrated(f"""
        INSERT INTO corpus_redirects (entity, old_id, old_document_id, new_id, new_document_id,
            kind, publish_id)
        VALUES ('passage', '{CHUNK_2}', '{DOC_A}', '{CHUNK_1}', '{DOC_A}', 'merged', 'r-test')
    """)
    assert "corpus_redirects_id_uniq" in _fails(migrated, f"""
        INSERT INTO corpus_redirects (entity, old_id, old_document_id, new_id, new_document_id,
            kind, publish_id)
        VALUES ('passage', '{CHUNK_2}', '{DOC_A}', '{CHUNK_3}', '{DOC_A}', 'moved', 'r-test')
    """)


def test_publish_records_embedding_model_snapshot_and_cleanup(migrated):
    migrated("""
        INSERT INTO corpus_publishes (id, collections, qdrant_collection, embed_model,
            embed_dimensions, snapshot_sha256, cleaned_up_at, discarded_at)
        VALUES ('p4-republish', ARRAY['bible'], 'chunks-p4-republish',
            'text-embedding-3-large', 1536, '{"chunks.jsonl": "ab12"}', now(), NULL)
    """)
    assert "check" in _fails(migrated, """
        INSERT INTO corpus_publishes (id, collections, qdrant_collection, snapshot_sha256)
        VALUES ('bad-snapshot', ARRAY['bible'], 'chunks-x', '["not", "an", "object"]')
    """)
    assert "check" in _fails(migrated, """
        INSERT INTO corpus_publishes (id, collections, qdrant_collection)
        VALUES ('Not A Release', ARRAY['bible'], 'chunks-x')
    """)


# --- staging -----------------------------------------------------------------------------

def _shape(cluster, schema, table):
    """Columns, generated expressions, CHECK and other constraints, and indexes, written
    without the schema name so the two schemas can be compared."""
    columns = cluster(f"""
        SELECT column_name, data_type, is_nullable, coalesce(column_default, ''),
               is_generated, coalesce(generation_expression, ''), is_identity
        FROM information_schema.columns
        WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position
    """)
    constraints = cluster(f"""
        SELECT contype, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = '{schema}' AND r.relname = '{table}' AND contype <> 'f'
        ORDER BY 1, 2
    """)
    indexes = cluster(f"""
        SELECT regexp_replace(regexp_replace(indexdef, '^CREATE (UNIQUE )?INDEX \\S+ ', '\\1'),
                              '{schema}\\.', '', 'g')
        FROM pg_indexes WHERE schemaname = '{schema}' AND tablename = '{table}' ORDER BY 1
    """)
    return columns, constraints, indexes


def test_staging_mirrors_live_tables(migrated):
    for table in STAGED_TABLES:
        assert _shape(migrated, "staging", table) == _shape(migrated, "public", table), table
    assert migrated("""
        SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'staging' AND c.contype = 'f'
    """) == [["0"]]


def test_staging_covers_the_contents_tree_and_reader_access(migrated):
    assert migrated("""
        SELECT column_name, column_default FROM information_schema.columns
        WHERE table_schema = 'staging' AND table_name = 'documents' AND column_name = 'reader_access'
    """) == [["reader_access", "'full'::text"]]
    assert "reader_access_check" in _fails(migrated, f"""
        INSERT INTO staging.documents (id, collection, title, reader_access)
        VALUES ('{DOC_A}', 'bible', 'A', 'hidden')
    """)
    migrated(f"""
        INSERT INTO staging.document_contents (document_id, ordinal, depth, node_key, kind,
            label, short_label, chapter_key)
        VALUES ('{DOC_A}', 1, 0, 'part-1', 'part', 'Part 1', 'I', 'c1')
    """)


def test_staging_has_the_full_text_index_and_generated_column(migrated):
    migrated(f"""
        INSERT INTO staging.documents (id, collection, title) VALUES ('{DOC_A}', 'bible', 'A');
        INSERT INTO staging.chunks (document_id, position, content)
            VALUES ('{DOC_A}', 0, 'the grace of God');
    """)
    assert migrated("SELECT count(*) FROM staging.chunks "
                    "WHERE search_vector @@ plainto_tsquery('english', 'grace')") == [["1"]]


def test_staging_writes_reach_no_user_table(migrated):
    # No foreign keys: a staged chunk of a document only staging holds is fine, and
    # deleting staged rows cascades nowhere.
    migrated("""
        INSERT INTO staging.chunks (document_id, position) VALUES (gen_random_uuid(), 0);
        DELETE FROM staging.chunks;
    """)
    assert migrated("SELECT count(*) FROM public.chunks") == [["4"]]


def test_staging_can_be_dropped_and_recreated(migrated):
    shapes = {t: _shape(migrated, "staging", t) for t in STAGED_TABLES}
    public_before = migrated("SELECT count(*), sum(hashtext(id::text)) FROM public.chunks")

    migrated("SELECT drop_corpus_staging()")
    assert migrated("SELECT count(*) FROM pg_tables WHERE schemaname = 'staging'") == [["0"]]
    migrated("SELECT create_corpus_staging()")
    migrated("SELECT create_corpus_staging()")  # idempotent

    assert {t: _shape(migrated, "staging", t) for t in STAGED_TABLES} == shapes
    assert migrated("SELECT count(*), sum(hashtext(id::text)) FROM public.chunks") == public_before
    for table in STAGED_TABLES:
        assert _shape(migrated, "public", table) == _shape(migrated, "staging", table)


def test_staging_outline_reads_staging(migrated):
    public_before = migrated("SELECT * FROM public.document_chapters ORDER BY 1, 2")
    migrated(f"""
        INSERT INTO staging.documents (id, collection, title) VALUES ('{DOC_A}', 'bible', 'A');
        INSERT INTO staging.chunks (document_id, position, chapter_key, chapter_label) VALUES
            ('{DOC_A}', 0, 's1', 'Staged 1'), ('{DOC_A}', 1, 's2', 'Staged 2'),
            ('{DOC_A}', 2, 's2', 'Staged 2');
        SELECT staging.refresh_document_outline('{DOC_A}');
    """)
    assert migrated(f"SELECT chapter_key FROM staging.document_chapters "
                    f"WHERE document_id = '{DOC_A}' ORDER BY ordinal") == [["s1"], ["s2"]]
    assert migrated(f"SELECT chunk_count FROM staging.documents WHERE id = '{DOC_A}'") == [["3"]]
    assert migrated("SELECT * FROM public.document_chapters ORDER BY 1, 2") == public_before
    assert _chunk_count(migrated, DOC_A) == "3"


def test_the_two_outline_functions_have_the_same_body(migrated):
    # Comments and whitespace aside; compared in SQL because the bodies span lines.
    assert migrated(r"""
        SELECT count(*), count(DISTINCT regexp_replace(
                   regexp_replace(prosrc, '--[^\n]*', '', 'g'), '\s+', ' ', 'g'))
        FROM pg_proc WHERE proname = 'refresh_document_outline'
    """) == [["2", "1"]]


# --- what must not change ----------------------------------------------------------------

def test_no_unique_key_dropped(migrated):
    assert migrated("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname IN ('chunks_document_id_position_key', 'chunks_document_anchor_uniq')
        ORDER BY 1
    """) == [["chunks_document_anchor_uniq"], ["chunks_document_id_position_key"]]


def test_no_column_or_index_of_an_existing_table_changes(postgres):
    postgres(SEED)
    postgres.migrate(*EARLIER)
    before = {t: _shape(postgres, "public", t)
              for t in ("documents", "chunks", "document_chapters", "document_contents")}

    postgres.migrate(SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)

    for table, (columns, constraints, indexes) in before.items():
        after_columns, after_constraints, after_indexes = _shape(postgres, "public", table)
        assert after_columns[:len(columns)] == columns, table
        assert set(map(tuple, constraints)) <= set(map(tuple, after_constraints)), table
        assert set(map(tuple, indexes)) <= set(map(tuple, after_indexes)), table


def test_new_objects_are_closed_to_client_roles(migrated):
    for role in ("anon", "authenticated"):
        for table in NEW_TABLES:
            assert migrated(f"SELECT has_table_privilege('{role}', 'public.{table}', 'SELECT')"
                            ) == [["f"]], (role, table)
        for table in STAGED_TABLES:
            assert migrated(f"SELECT has_table_privilege('{role}', 'staging.{table}', 'SELECT')"
                            ) == [["f"]], (role, table)
        assert migrated(f"SELECT has_schema_privilege('{role}', 'staging', 'USAGE')") == [["f"]]
        for function in ("public.create_corpus_staging()", "public.drop_corpus_staging()",
                         "public.refresh_document_outline(uuid)",
                         "staging.refresh_document_outline(uuid)"):
            assert migrated(f"SELECT has_function_privilege('{role}', '{function}', 'EXECUTE')"
                            ) == [["f"]], (role, function)
        assert "permission denied" in _fails(
            migrated, f"SET ROLE {role}; SELECT * FROM staging.chunks;")
        assert "permission denied" in _fails(
            migrated, f"SET ROLE {role}; SELECT * FROM public.corpus_tombstones;")

    rls = migrated("""
        SELECT n.nspname || '.' || c.relname, c.relrowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND (n.nspname = 'staging' OR c.relname IN
            ('corpus_genres', 'document_works', 'corpus_publishes', 'corpus_tombstones',
             'corpus_redirects'))
    """)
    assert len(rls) == len(NEW_TABLES) + len(STAGED_TABLES)
    assert all(on == "t" for _, on in rls)
    assert migrated("SELECT count(*) FROM pg_policies WHERE tablename IN "
                    "('corpus_genres', 'document_works', 'corpus_publishes', "
                    "'corpus_tombstones', 'corpus_redirects')") == [["0"]]


# --- locking -----------------------------------------------------------------------------

def test_the_schema_migration_validates_nothing(postgres):
    """0042 must not scan documents or chunks under its ACCESS EXCLUSIVE locks."""
    postgres(SEED)
    postgres.migrate(*EARLIER, SCHEMA_MIGRATION.name)
    names = ", ".join(f"'{n}'" for n in DEFERRED_CONSTRAINTS)

    assert postgres(f"SELECT conname, convalidated FROM pg_constraint "
                    f"WHERE conname IN ({names}) AND connamespace = 'public'::regnamespace ORDER BY 1"
                    ) == [[n, "f"] for n in DEFERRED_CONSTRAINTS]
    assert postgres("SELECT count(*) FROM pg_tables WHERE schemaname = 'staging'") == [["0"]]

    postgres.migrate(VALIDATE_MIGRATION.name)

    assert postgres(f"SELECT conname, convalidated FROM pg_constraint "
                    f"WHERE conname IN ({names}) AND connamespace = 'public'::regnamespace ORDER BY 1"
                    ) == [[n, "t"] for n in DEFERRED_CONSTRAINTS]


def test_validation_takes_no_lock_that_blocks_reads(postgres):
    postgres(SEED)
    postgres.migrate(*EARLIER, SCHEMA_MIGRATION.name)

    locks = postgres(f"""
        BEGIN;
        {VALIDATE_MIGRATION.read_text()}
        SELECT DISTINCT c.relname, l.mode FROM pg_locks l JOIN pg_class c ON c.oid = l.relation
        WHERE l.pid = pg_backend_pid()
          AND l.relation IN ('public.documents'::regclass, 'public.chunks'::regclass)
        ORDER BY 1, 2;
        COMMIT;
    """)
    modes = {(table, mode) for table, mode in locks}
    assert not any(mode in ("AccessExclusiveLock", "ExclusiveLock") for _, mode in modes), modes


def test_the_lock_timeout_ends_with_each_migration(postgres):
    postgres(SEED)
    postgres.migrate(*EARLIER)
    result = subprocess.run(
        postgres.psql_args() + ["-A", "-t"],
        input=f"BEGIN;\n{SCHEMA_MIGRATION.read_text()}\nCOMMIT;\n"
              f"BEGIN;\n{VALIDATE_MIGRATION.read_text()}\nCOMMIT;\nSHOW lock_timeout;",
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[-1] == "0"
