"""A throwaway local PostgreSQL holding the production corpus schema, for tests that
run the publish path's real SQL (2.2w).

One cluster per test session. Its `corpus_template` database has the corpus tables as
production has them before 0037 (from services/api/tests/test_corpus_facts_migration.py,
without the unused pgvector columns), the user tables that reference passages and
documents, and migrations 0037, 0038, 0040, 0041, 0042, 0043 and 0044 applied. Each test gets
its own copy (`CREATE DATABASE ... TEMPLATE`). Skips when initdb, pg_ctl or psql is
missing, or when running as root.
"""
from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import asyncpg
import pytest

MIGRATIONS = Path(__file__).parents[2] / "supabase/migrations"
APPLIED = ("0037_document_outline.sql", "0038_backfill_document_outline.sql",
           "0040_document_contents.sql", "0041_document_reader_access.sql",
           "0042_corpus_facts_retirement_staging.sql", "0043_validate_corpus_facts.sql",
           "0044_document_form.sql")

PRODUCTION_SCHEMA = """
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE authenticated NOLOGIN;
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
    CREATE INDEX chunks_document_id_idx ON chunks (document_id);
    CREATE UNIQUE INDEX chunks_document_anchor_uniq ON chunks (document_id, anchor)
        WHERE anchor IS NOT NULL;

    -- The user tables that point at the corpus, reduced to their keys (D3 table in
    -- docs/corpus-cleanup/P2-P3-schema-reader-policy.md). Every one cascades except
    -- product_feedback, which sets NULL.
    CREATE TABLE retrievals (
        id bigserial PRIMARY KEY, search_id uuid NOT NULL,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE);
    CREATE TABLE bookmarks (
        id bigserial PRIMARY KEY, user_id uuid NOT NULL,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
        UNIQUE (user_id, chunk_id));
    CREATE TABLE retrieval_labels (
        id bigserial PRIMARY KEY, user_id uuid NOT NULL, search_id uuid NOT NULL,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE);
    CREATE TABLE guest_trial_retrievals (
        id bigserial PRIMARY KEY, guest_trial_id uuid NOT NULL,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE);
    CREATE TABLE reading_progress (
        user_id uuid NOT NULL,
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chapter_key text NOT NULL, anchor text,
        PRIMARY KEY (user_id, document_id));
    CREATE TABLE product_feedback (
        id bigserial PRIMARY KEY,
        chunk_id uuid REFERENCES chunks(id) ON DELETE SET NULL,
        document_id uuid REFERENCES documents(id) ON DELETE SET NULL);
"""
USER_TABLES = ("retrievals", "bookmarks", "retrieval_labels", "guest_trial_retrievals",
               "reading_progress")


def _run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60, **kwargs)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


class CorpusCluster:
    def __init__(self, socket: Path):
        self.socket = socket
        self._names = itertools.count()

    def psql(self, database: str, source: str, *, single: bool = False) -> None:
        _run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
              "-h", str(self.socket), "-d", database, *(["--single-transaction"] * single)],
             input=source)

    def new_database(self) -> str:
        name = f"t{next(self._names)}"
        self.psql("postgres", f"CREATE DATABASE {name} TEMPLATE corpus_template")
        return name

    async def connect(self, database: str) -> asyncpg.Connection:
        return await asyncpg.connect(host=str(self.socket), user="postgres", database=database)


def start() -> tuple[CorpusCluster, callable]:
    if os.geteuid() == 0:
        pytest.skip("initdb cannot run as root")
    if not all(shutil.which(command) for command in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools are unavailable")
    short_tmp = "/private/tmp" if Path("/private/tmp").is_dir() else "/tmp"
    directory = tempfile.mkdtemp(prefix="tc-stage-", dir=short_tmp)
    root = Path(directory)
    socket = root / "socket"
    socket.mkdir()
    _run(["initdb", "-D", str(root / "data"), "-U", "postgres", "-A", "trust",
          "--no-instructions"])
    _run(["pg_ctl", "-D", str(root / "data"), "-o",
          f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c fsync=off "
          "-c log_statement=all",
          "-l", str(root / "server.log"), "-w", "start"])
    cluster = CorpusCluster(socket)
    cluster.log = root / "server.log"
    cluster.psql("postgres", "CREATE DATABASE corpus_template")
    cluster.psql("corpus_template", PRODUCTION_SCHEMA)
    for name in APPLIED:
        cluster.psql("corpus_template", (MIGRATIONS / name).read_text(), single=True)

    def stop():
        _run(["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"])
        shutil.rmtree(directory, ignore_errors=True)
    return cluster, stop


# The user tables as production has them (0005, 0006, 0016, 0022, 0023, 0026, 0027,
# 0028, 0030), with auth.users cut to its key, for tests of 4.1a's remap.
PRODUCTION_USER_TABLES = """
    DROP TABLE retrievals, bookmarks, retrieval_labels, guest_trial_retrievals,
        reading_progress, product_feedback;
    CREATE SCHEMA auth;
    CREATE TABLE auth.users (id uuid PRIMARY KEY);
    CREATE TABLE searches (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        query text NOT NULL DEFAULT 'q', filters jsonb, result_count int,
        created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE retrievals (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        search_id uuid NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
        rank int NOT NULL, reranker_score float, explanation text,
        created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE bookmarks (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        note text CHECK (char_length(note) <= 3000),
        UNIQUE (user_id, chunk_id));
    CREATE TABLE retrieval_labels (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
        search_id uuid NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
        label text NOT NULL CHECK (label IN ('up', 'down')),
        rank int NOT NULL CHECK (rank >= 1),
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (user_id, chunk_id, search_id));
    CREATE TABLE guest_trials (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        ip_hash text NOT NULL DEFAULT 'h',
        created_at timestamptz NOT NULL DEFAULT now(),
        claimed_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
        claimed_at timestamptz);
    CREATE TABLE guest_trial_retrievals (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        guest_trial_id uuid NOT NULL REFERENCES guest_trials(id) ON DELETE CASCADE,
        chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
        rank integer NOT NULL, reranker_score double precision, explanation text,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (guest_trial_id, chunk_id));
    CREATE TABLE reading_progress (
        user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chapter_key text NOT NULL CHECK (char_length(chapter_key) BETWEEN 1 AND 500),
        anchor text CHECK (anchor IS NULL OR char_length(anchor) BETWEEN 1 AND 500),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, document_id));
    CREATE TABLE product_feedback (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
        message text NOT NULL DEFAULT 'feedback text',
        search_id uuid REFERENCES searches(id) ON DELETE SET NULL,
        chunk_id uuid REFERENCES chunks(id) ON DELETE SET NULL,
        document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
        created_at timestamptz NOT NULL DEFAULT now());
"""


def use_production_user_tables(cluster: CorpusCluster, database: str) -> None:
    """Replace a test database's key-only user tables with production's shapes."""
    cluster.psql(database, PRODUCTION_USER_TABLES, single=True)
