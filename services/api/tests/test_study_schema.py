"""Exercise the Study migration against an isolated local PostgreSQL cluster."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


MIGRATION = Path(__file__).parents[3] / "supabase/migrations/0035_studies.sql"


def run_postgres_command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def postgres():
    if os.geteuid() == 0:
        pytest.skip("initdb cannot run as root")
    if not all(shutil.which(command) for command in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools are unavailable")

    # macOS limits Unix socket paths, so pytest's nested temp path is too long.
    short_tmp = "/private/tmp" if Path("/private/tmp").is_dir() else "/tmp"
    with tempfile.TemporaryDirectory(prefix="tc-study-", dir=short_tmp) as directory:
        root = Path(directory)
        data = root / "data"
        socket = root / "socket"
        socket.mkdir()

        run_postgres_command(
            ["initdb", "-D", str(data), "-U", "postgres", "-A", "trust", "--no-instructions"]
        )
        run_postgres_command(
            ["pg_ctl", "-D", str(data), "-o",
             f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c fsync=off",
             "-l", str(root / "server.log"), "-w", "start"]
        )

        def sql(source: str) -> str:
            result = subprocess.run(
                ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                 "-h", str(socket), "-d", "postgres"],
                input=source, capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, result.stderr
            return result.stdout

        try:
            yield sql
        finally:
            run_postgres_command(
                ["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"]
            )


def test_study_ownership_order_and_source_deletion(postgres):
    postgres("""
        CREATE SCHEMA auth;
        CREATE TABLE auth.users (id uuid PRIMARY KEY);
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
        $$;
        CREATE TABLE documents (
            id uuid PRIMARY KEY, title text, collection text,
            author text, translation text
        );
        CREATE TABLE chunks (
            id uuid PRIMARY KEY, document_id uuid REFERENCES documents(id),
            content text, reference text, unit_label text
        );
        CREATE FUNCTION public.update_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END;
        $$;
        CREATE ROLE anon NOLOGIN;
        CREATE ROLE authenticated NOLOGIN;
        CREATE ROLE study_app NOLOGIN;
        INSERT INTO auth.users VALUES
            ('00000000-0000-0000-0000-000000000001'),
            ('00000000-0000-0000-0000-000000000002');
        INSERT INTO documents VALUES (
            '00000000-0000-0000-0000-000000000020',
            'Summa Theologica', 'summa', 'Thomas Aquinas', 'English'
        );
        INSERT INTO chunks VALUES (
            '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000020',
            'It seems that merit is impossible.', 'ST I-II q.114 a.1', 'Objection 1'
        );
    """)
    postgres(MIGRATION.read_text())
    postgres("""
        GRANT USAGE ON SCHEMA auth, public TO study_app;
        GRANT SELECT ON auth.users, documents, chunks TO study_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON studies, study_blocks TO study_app;
        DO $$ BEGIN
            IF has_table_privilege('authenticated', 'studies', 'INSERT')
                OR has_table_privilege('authenticated', 'study_blocks', 'SELECT')
                OR has_table_privilege('anon', 'studies', 'SELECT') THEN
                RAISE EXCEPTION 'Study tables are exposed through the Data API';
            END IF;
        END $$;
    """)

    postgres("""
        SET ROLE study_app;
        SELECT set_config('request.jwt.claim.sub',
            '00000000-0000-0000-0000-000000000001', false);
        INSERT INTO studies (id, user_id, title) VALUES
            ('00000000-0000-0000-0000-000000000100',
             '00000000-0000-0000-0000-000000000001', 'First Study'),
            ('00000000-0000-0000-0000-000000000101',
             '00000000-0000-0000-0000-000000000001', 'Second Study');
        INSERT INTO study_blocks
            (study_id, user_id, position, kind, writing)
        VALUES
            ('00000000-0000-0000-0000-000000000100',
             '00000000-0000-0000-0000-000000000001', 0, 'writing', 'My introduction');
        INSERT INTO study_blocks
            (study_id, user_id, position, kind, source_passage_id,
             source_content, source_reference, source_unit_label,
             source_document_title, source_collection,
             heading, commentary)
        VALUES
            ('00000000-0000-0000-0000-000000000100',
             '00000000-0000-0000-0000-000000000001', 1, 'passage',
             '00000000-0000-0000-0000-000000000010',
             'Forged text', 'Forged citation', 'Forged role', 'Forged title', 'bible',
             'Opening', 'My note'),
            ('00000000-0000-0000-0000-000000000100',
             '00000000-0000-0000-0000-000000000001', 2, 'passage',
             '00000000-0000-0000-0000-000000000010',
             NULL, NULL, NULL, NULL, NULL,
             'Again', NULL),
            ('00000000-0000-0000-0000-000000000101',
             '00000000-0000-0000-0000-000000000001', 0, 'passage',
             '00000000-0000-0000-0000-000000000010',
             NULL, NULL, NULL, NULL, NULL,
             NULL, NULL);
        DO $$ BEGIN
            IF (SELECT count(*) FROM study_blocks WHERE kind = 'passage') <> 3 THEN
                RAISE EXCEPTION 'Passage repetition was lost';
            END IF;
            IF (SELECT count(*) FROM study_blocks
                WHERE kind = 'passage'
                AND source_content = 'It seems that merit is impossible.'
                AND source_reference = 'ST I-II q.114 a.1'
                AND source_unit_label = 'Objection 1'
                AND source_document_title = 'Summa Theologica'
                AND source_collection = 'summa'
                AND source_author = 'Thomas Aquinas'
                AND source_translation = 'English') <> 3 THEN
                RAISE EXCEPTION 'Source snapshot was not copied from canonical Passage';
            END IF;
        END $$;
        DO $$ DECLARE rejected boolean := false; BEGIN
            BEGIN
                INSERT INTO study_blocks
                    (study_id, user_id, position, kind, source_passage_id)
                VALUES ('00000000-0000-0000-0000-000000000100',
                    '00000000-0000-0000-0000-000000000001', 3, 'passage',
                    '00000000-0000-0000-0000-000000000099');
            EXCEPTION WHEN foreign_key_violation THEN rejected := true;
            END;
            IF NOT rejected THEN RAISE EXCEPTION 'Nonexistent Passage was accepted'; END IF;
        END $$;
        BEGIN;
        UPDATE study_blocks SET position = CASE position
            WHEN 1 THEN 2 WHEN 2 THEN 1 ELSE position END
        WHERE study_id = '00000000-0000-0000-0000-000000000100';
        COMMIT;
        DO $$ BEGIN
            IF (SELECT array_agg(heading ORDER BY position)
                FROM study_blocks WHERE study_id =
                '00000000-0000-0000-0000-000000000100' AND kind = 'passage')
                <> ARRAY['Again', 'Opening'] THEN
                RAISE EXCEPTION 'Passage order was not updated';
            END IF;
        END $$;
        RESET ROLE;
    """)

    postgres("""
        SET ROLE study_app;
        SELECT set_config('request.jwt.claim.sub',
            '00000000-0000-0000-0000-000000000002', false);
        INSERT INTO studies (id, user_id, title) VALUES
            ('00000000-0000-0000-0000-000000000200',
             '00000000-0000-0000-0000-000000000002', 'Other Study');
        DO $$ DECLARE denied boolean := false; mismatched boolean := false; BEGIN
            IF (SELECT count(*) FROM studies) <> 1 THEN
                RAISE EXCEPTION 'Owner cannot read own Study';
            END IF;
            IF (SELECT count(*) FROM studies WHERE id =
                '00000000-0000-0000-0000-000000000100') <> 0 THEN
                RAISE EXCEPTION 'Other owner can read a private Study';
            END IF;
            IF (SELECT count(*) FROM study_blocks) <> 0 THEN
                RAISE EXCEPTION 'Other owner can read private Study blocks';
            END IF;
            UPDATE studies SET title = 'Stolen' WHERE id =
                '00000000-0000-0000-0000-000000000100';
            DELETE FROM study_blocks;
            BEGIN
                INSERT INTO study_blocks (study_id, user_id, position, kind, writing)
                VALUES ('00000000-0000-0000-0000-000000000100',
                    '00000000-0000-0000-0000-000000000001', 3, 'writing', 'Intrusion');
            EXCEPTION WHEN insufficient_privilege THEN denied := true;
            END;
            IF NOT denied THEN RAISE EXCEPTION 'Cross-owner block insert succeeded'; END IF;
            BEGIN
                INSERT INTO study_blocks (study_id, user_id, position, kind, writing)
                VALUES ('00000000-0000-0000-0000-000000000100',
                    '00000000-0000-0000-0000-000000000002', 3, 'writing', 'Intrusion');
            EXCEPTION WHEN foreign_key_violation THEN mismatched := true;
            END;
            IF NOT mismatched THEN
                RAISE EXCEPTION 'Block can be attached to another owner Study';
            END IF;
        END $$;
        RESET ROLE;
        DO $$ BEGIN
            IF (SELECT title FROM studies WHERE id =
                '00000000-0000-0000-0000-000000000100') <> 'First Study'
                OR (SELECT count(*) FROM study_blocks) <> 4 THEN
                RAISE EXCEPTION 'Other owner changed private Study data';
            END IF;
        END $$;
    """)

    postgres("""
        DELETE FROM chunks WHERE id = '00000000-0000-0000-0000-000000000010';
        SET ROLE study_app;
        SELECT set_config('request.jwt.claim.sub',
            '00000000-0000-0000-0000-000000000001', false);
        UPDATE study_blocks SET source_content = 'Changed by owner'
            WHERE kind = 'passage';
        DO $$ BEGIN
            IF (SELECT count(*) FROM study_blocks
                WHERE kind = 'passage'
                AND source_passage_id = '00000000-0000-0000-0000-000000000010'
                AND source_content = 'It seems that merit is impossible.'
                AND source_reference = 'ST I-II q.114 a.1'
                AND source_unit_label = 'Objection 1') <> 3 THEN
                RAISE EXCEPTION 'Corpus prune erased a Study Passage snapshot';
            END IF;
            IF (SELECT count(*) FROM study_blocks b
                JOIN chunks c ON c.id = b.source_passage_id) <> 0 THEN
                RAISE EXCEPTION 'Pruned source still appears available';
            END IF;
            IF (SELECT count(*) FROM study_blocks WHERE kind = 'writing'
                AND writing = 'My introduction') <> 1 THEN
                RAISE EXCEPTION 'Corpus prune erased authored writing';
            END IF;
        END $$;
        RESET ROLE;
        DELETE FROM auth.users WHERE id = '00000000-0000-0000-0000-000000000001';
        DO $$ BEGIN
            IF (SELECT count(*) FROM studies) <> 1
                OR (SELECT title FROM studies) <> 'Other Study'
                OR (SELECT count(*) FROM study_blocks) <> 0 THEN
                RAISE EXCEPTION 'Account deletion failed to cascade only its Study data';
            END IF;
        END $$;
    """)
