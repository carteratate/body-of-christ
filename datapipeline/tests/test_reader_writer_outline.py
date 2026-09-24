"""write_document keeps the reader outline in step with the chunks it publishes.

Runs the real writer against a throwaway local PostgreSQL cluster with migrations
0037 and 0038 applied, then republishes documents the way a re-ingest does.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import asyncpg
import pytest

from model import Document, Passage
from writers import reader_writer

MIGRATIONS = Path(__file__).parents[2] / "supabase/migrations"
DOC_ID = "11111111-1111-1111-1111-111111111111"

# The corpus columns write_document and the outline touch, as production has them.
CORPUS_SCHEMA = """
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE authenticated NOLOGIN;
    CREATE TABLE documents (
        id uuid PRIMARY KEY, collection text NOT NULL, title text NOT NULL,
        author text, year int, translation text, metadata jsonb
    );
    CREATE TABLE chunks (
        id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        content text NOT NULL, position int NOT NULL, reference text, anchor text,
        chapter_key text, chapter_label text, unit_label text, metadata jsonb,
        UNIQUE (document_id, position)
    );
"""


def _run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture()
def socket_dir():
    if os.geteuid() == 0:
        pytest.skip("initdb cannot run as root")
    if not all(shutil.which(command) for command in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools are unavailable")
    # macOS limits Unix socket paths, so pytest's nested temp path is too long.
    short_tmp = "/private/tmp" if Path("/private/tmp").is_dir() else "/tmp"
    with tempfile.TemporaryDirectory(prefix="tc-writer-", dir=short_tmp) as directory:
        root = Path(directory)
        socket = root / "socket"
        socket.mkdir()
        _run(["initdb", "-D", str(root / "data"), "-U", "postgres", "-A", "trust",
              "--no-instructions"])
        _run(["pg_ctl", "-D", str(root / "data"), "-o",
              f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c fsync=off",
              "-l", str(root / "server.log"), "-w", "start"])
        try:
            yield socket
        finally:
            _run(["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"])


def _doc(*chapters):
    """A document whose passages are (anchor, chapter_key, chapter_label) triples."""
    return Document(
        id=DOC_ID, collection="summa", title="Summa", translation="",
        passages=[Passage(content=anchor, reference=None, anchor=anchor, chapter_key=key,
                          chapter_label=label, position=i, unit_label=None)
                  for i, (anchor, key, label) in enumerate(chapters)],
    )


async def _publish_and_read(socket, *builds):
    conn = await asyncpg.connect(host=str(socket), user="postgres", database="postgres")
    try:
        await conn.execute(CORPUS_SCHEMA)
        for name in ("0037_document_outline.sql", "0038_backfill_document_outline.sql"):
            await conn.execute((MIGRATIONS / name).read_text())
        outlines = []
        for build in builds:
            await reader_writer.write_document(conn, build)
            chapters = await conn.fetch(
                "SELECT ordinal, chapter_key, chapter_label FROM document_chapters "
                "WHERE document_id = $1 ORDER BY ordinal", DOC_ID)
            count = await conn.fetchval("SELECT chunk_count FROM documents WHERE id = $1", DOC_ID)
            outlines.append(([tuple(r) for r in chapters], count))
        return outlines
    finally:
        await conn.close()


def test_a_republish_rebuilds_the_outline_it_changes(socket_dir):
    first = _doc(("q1/a1", "q1", "Question 1"), ("q1/a2", "q1", "Question 1"),
                 ("q2/a1", "q2", "Question 2"), ("q3/a1", "q3", "Question 3"))
    # A re-ingest drops q1, renames q2's key, relabels q3 and adds q4.
    second = _doc(("q2b/a1", "q2b", "Question 2"), ("q3/a1", "q3", "Question Three"),
                  ("q4/a1", "q4", "Question 4"))

    published, republished = asyncio.run(_publish_and_read(socket_dir, first, second))

    assert published == ([(1, "q1", "Question 1"), (2, "q2", "Question 2"),
                          (3, "q3", "Question 3")], 4)
    assert republished == ([(1, "q2b", "Question 2"), (2, "q3", "Question Three"),
                            (3, "q4", "Question 4")], 3)


def test_a_failed_publish_leaves_the_previous_outline(socket_dir):
    """The refresh shares write_document's transaction, so it rolls back with it."""
    good = _doc(("q1/a1", "q1", "Question 1"))
    # Two passages at one position violate UNIQUE (document_id, position) mid-write.
    broken = _doc(("q9/a1", "q9", "Question 9"), ("q9/a2", "q9", "Question 9"))
    broken.passages[1].position = 0

    async def scenario():
        [(outline, count)] = await _publish_and_read(socket_dir, good)
        conn = await asyncpg.connect(host=str(socket_dir), user="postgres", database="postgres")
        try:
            with pytest.raises(asyncpg.UniqueViolationError):
                await reader_writer.write_document(conn, broken)
            after = await conn.fetch(
                "SELECT ordinal, chapter_key, chapter_label FROM document_chapters "
                "WHERE document_id = $1 ORDER BY ordinal", DOC_ID)
            after_count = await conn.fetchval(
                "SELECT chunk_count FROM documents WHERE id = $1", DOC_ID)
        finally:
            await conn.close()
        return (outline, count), ([tuple(r) for r in after], after_count)

    before, after = asyncio.run(scenario())

    assert before == after == ([(1, "q1", "Question 1")], 1)
