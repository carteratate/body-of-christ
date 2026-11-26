"""scripts/check_migrations.py: the CI check that migrations stay additive."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[3]
_spec = importlib.util.spec_from_file_location("check_migrations", REPO / "scripts/check_migrations.py")
check_migrations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_migrations)
non_additive, check = check_migrations.non_additive, check_migrations.check


@pytest.mark.parametrize("sql", [
    "CREATE TABLE notes (id uuid PRIMARY KEY, body text);",
    "ALTER TABLE documents ADD COLUMN genre text;",
    "CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks (document_id);",
    "DROP INDEX IF EXISTS chunks_old_idx;",
    "DROP TRIGGER IF EXISTS t ON chunks; CREATE TRIGGER t AFTER TRUNCATE ON chunks "
    "FOR EACH STATEMENT EXECUTE FUNCTION f();",
    "ALTER TABLE documents DROP CONSTRAINT documents_collection_check, "
    "ADD CONSTRAINT documents_collection_check CHECK (collection IN ('a', 'b'));",
    "UPDATE documents SET genre = 'encyclical' WHERE genre IS NULL;",
    "-- an earlier version used DROP COLUMN here\nALTER TABLE chunks ADD COLUMN note text;",
    "/* DROP TABLE chunks; */ SELECT 1;",
    "IF TG_OP = 'TRUNCATE' THEN RETURN NULL; END IF;",
    "DROP TABLE IF EXISTS staging.chunks, staging.documents CASCADE;",
    "ALTER TABLE staging.chunks DROP COLUMN search_vector;",
    "CREATE OR REPLACE FUNCTION drop_corpus_staging() RETURNS void LANGUAGE plpgsql AS $$\n"
    "BEGIN\n    DROP TABLE IF EXISTS staging.corpus_redirects, staging.corpus_tombstones;\n"
    "    TRUNCATE staging.chunks;\nEND $$;",
    "INSERT INTO corpus_genres (key) VALUES ('rename-me');",
])
def test_additive_sql_passes(sql):
    assert non_additive(sql) == []


@pytest.mark.parametrize("sql, expected", [
    ("DROP TABLE IF EXISTS chunk_feedback;", "DROP TABLE chunk_feedback"),
    ("DROP VIEW public.v_sources;", "DROP VIEW public.v_sources"),
    ("drop materialized view mv;", "DROP MATERIALIZED VIEW mv"),
    ("DROP FUNCTION refresh_document_outline(uuid);", "DROP FUNCTION refresh_document_outline"),
    ('DROP POLICY IF EXISTS "own rows" ON labels;', 'DROP POLICY "own rows"'),
    ("DROP TABLE staging.chunks, public.chunks;", "DROP TABLE staging.chunks, public.chunks"),
    ("ALTER TABLE chunks DROP COLUMN annotation;", "DROP COLUMN on chunks"),
    ("ALTER TABLE ONLY public.chunks\n    DROP COLUMN IF EXISTS annotation;", "DROP COLUMN on public.chunks"),
    ("ALTER TABLE documents RENAME COLUMN year TO issued;", "RENAME on documents"),
    ("ALTER TABLE documents RENAME TO works;", "RENAME on documents"),
    ("ALTER TABLE documents ALTER COLUMN year TYPE bigint;", "ALTER COLUMN ... TYPE on documents"),
    ("ALTER TABLE documents ALTER year SET DATA TYPE bigint;", "ALTER COLUMN ... TYPE on documents"),
    ("ALTER TABLE product_feedback ALTER COLUMN rate_limit_key SET NOT NULL;",
     "SET NOT NULL on product_feedback"),
    ("ALTER TABLE t ALTER COLUMN a SET DEFAULT 'x', ALTER COLUMN a SET NOT NULL;", "SET NOT NULL on t"),
    ("TRUNCATE chunks;", "TRUNCATE chunks"),
    ("DO $$ BEGIN\n  EXECUTE format('ALTER TABLE public.chunks DROP COLUMN search_vector, '\n"
     "    'ADD COLUMN search_vector tsvector'); END $$;", "DROP COLUMN on public.chunks"),
])
def test_non_additive_sql_is_named(sql, expected):
    found = non_additive(sql)
    assert len(found) == 1 and found[0].endswith(expected), found


def test_the_committed_migrations_flag_only_the_known_five():
    """The historical non-additive migrations, all applied before this check existed."""
    flagged = sorted(p.name for p in (REPO / "supabase/migrations").glob("*.sql")
                     if p.name < "0048" and non_additive(p.read_text()))
    assert flagged == [
        "0022_retrieval_labels.sql",
        "0024_harden_retrieval_labels_rls.sql",
        "0030_anonymous_product_feedback.sql",
        "0034_focused_quota_preferences.sql",
        "0045_search_vector_markers_and_reference.sql",
    ]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A repository whose base commit holds two applied migrations."""
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    migrations = tmp_path / "supabase/migrations"
    migrations.mkdir(parents=True)
    (migrations / "0001_init.sql").write_text("CREATE TABLE documents (id uuid PRIMARY KEY);\n")
    (migrations / "0002_genre.sql").write_text("ALTER TABLE documents ADD COLUMN genre text;\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _add(repo: Path, name: str, sql: str, commit: bool = True) -> None:
    (repo / "supabase/migrations" / name).write_text(sql)
    if commit:
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", name)


def test_an_additive_migration_passes(repo):
    _add(repo, "0003_notes.sql", "ALTER TABLE documents ADD COLUMN notes text;\n")
    assert check("master~1", repo) == []


def test_a_non_additive_migration_fails_until_it_says_why(repo):
    _add(repo, "0003_drop_genre.sql", "ALTER TABLE documents DROP COLUMN genre;\n")
    [problem] = check("master~1", repo)
    assert problem.startswith("0003_drop_genre.sql line 1: DROP COLUMN on documents: not additive")

    _add(repo, "0003_drop_genre.sql",
         "-- non-additive: the API stopped reading genre in #500; Carter approved 1 Dec\n"
         "ALTER TABLE documents DROP COLUMN genre;\n")
    assert check("master~2", repo) == []


def test_an_empty_reason_is_not_a_marker(repo):
    _add(repo, "0003_drop_genre.sql", "-- non-additive:\nALTER TABLE documents DROP COLUMN genre;\n")
    assert len(check("master~1", repo)) == 1


def test_a_migration_not_yet_committed_is_checked(repo):
    _add(repo, "0003_drop_genre.sql", "ALTER TABLE documents DROP COLUMN genre;\n", commit=False)
    assert len(check("master", repo)) == 1


def test_an_applied_migration_must_not_change(repo):
    _add(repo, "0002_genre.sql", "ALTER TABLE documents ADD COLUMN genre text NOT NULL;\n")
    [problem] = check("master~1", repo)
    assert problem.startswith("0002_genre.sql: changes or deletes a migration")

    _add(repo, "0002_genre.sql", "-- migration-edit-approved: never applied, see #501\n"
                                 "ALTER TABLE documents ADD COLUMN genre text NOT NULL;\n")
    assert check("master~2", repo) == []


def test_an_applied_migration_must_not_be_deleted_or_renamed(repo):
    _git(repo, "mv", "supabase/migrations/0002_genre.sql", "supabase/migrations/0003_genre.sql")
    _git(repo, "commit", "-q", "-m", "renumber")
    problems = check("master~1", repo)
    assert any(p.startswith("0002_genre.sql: changes or deletes") for p in problems)


def test_a_new_migration_cannot_reuse_a_number(repo):
    _add(repo, "0002_preferences.sql", "CREATE TABLE preferences (id uuid);\n")
    [problem] = check("master~1", repo)
    assert "number 0002 is already used by 0002_genre.sql" in problem


def test_two_new_migrations_cannot_share_a_number(repo):
    _add(repo, "0003_a.sql", "CREATE TABLE a (id uuid);\n")
    _add(repo, "0003_b.sql", "CREATE TABLE b (id uuid);\n")
    [problem] = check("master~2", repo)
    assert problem.startswith("0003_b.sql: number 0003 is already used by 0003_a.sql")


def test_a_badly_named_migration_fails(repo):
    _add(repo, "3_Notes.sql", "CREATE TABLE notes (id uuid);\n")
    assert check("master~1", repo) == ["3_Notes.sql: name it NNNN_lowercase_words.sql"]
