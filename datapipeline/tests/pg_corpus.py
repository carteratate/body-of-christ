"""A throwaway local PostgreSQL holding the production corpus schema, for tests that
run the publish path's real SQL (2.2w).

One cluster per test session. Its `corpus_template` database has the corpus tables as
production has them before 0037 (from services/api/tests/test_corpus_facts_migration.py,
without the unused pgvector columns), the user tables that reference passages and
documents, and migrations 0037, 0038, 0040, 0041, 0042 and 0043 applied. Each test gets
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
           "0042_corpus_facts_retirement_staging.sql", "0043_validate_corpus_facts.sql")

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
    -- docs/corpus-cleanup/P2-P3-schema-reader-policy.md). Every one cascades.
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
