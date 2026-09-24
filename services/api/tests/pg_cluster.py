"""A throwaway local PostgreSQL cluster for tests that must run real SQL.

Skips the calling test when initdb/pg_ctl/psql are unavailable or when running as
root, so the suite still passes on machines without a local PostgreSQL install.
"""

import contextlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).parents[3] / "supabase/migrations"

# The corpus tables as production has them, reduced to the columns the reader and the
# outline migrations touch (0004, 0008, 0013), plus the Supabase roles the migrations
# revoke from. `content` defaults to '' only so structural fixtures can omit it.
CORPUS_SCHEMA = """
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE authenticated NOLOGIN;
    CREATE TABLE documents (
        id uuid PRIMARY KEY,
        collection text NOT NULL,
        title text NOT NULL,
        author text,
        year int,
        translation text,
        metadata jsonb
    );
    CREATE TABLE chunks (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        content text NOT NULL DEFAULT '',
        position int NOT NULL,
        reference text,
        anchor text,
        chapter_key text,
        chapter_label text,
        unit_label text,
        UNIQUE (document_id, position)
    );
"""


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@dataclass(frozen=True)
class Cluster:
    socket: Path

    def psql_args(self) -> list[str]:
        return ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-h", str(self.socket), "-d", "postgres"]

    def sql(self, source: str) -> list[list[str]]:
        """Run SQL; return the last statement's rows as lists of strings."""
        result = subprocess.run(
            [*self.psql_args(), "-A", "-t", "-F", "|"],
            input=source, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return [line.split("|") for line in result.stdout.splitlines() if line]

    __call__ = sql

    def migrate(self, *names: str) -> None:
        for name in names:
            self.sql((MIGRATIONS / name).read_text())


@contextlib.contextmanager
def local_cluster(prefix: str) -> Iterator[Cluster]:
    if os.geteuid() == 0:
        pytest.skip("initdb cannot run as root")
    if not all(shutil.which(command) for command in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools are unavailable")

    # macOS limits Unix socket paths, so pytest's nested temp path is too long.
    short_tmp = "/private/tmp" if Path("/private/tmp").is_dir() else "/tmp"
    with tempfile.TemporaryDirectory(prefix=prefix, dir=short_tmp) as directory:
        root = Path(directory)
        data = root / "data"
        socket = root / "socket"
        socket.mkdir()
        _run(["initdb", "-D", str(data), "-U", "postgres", "-A", "trust", "--no-instructions"])
        _run(["pg_ctl", "-D", str(data), "-o",
              f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c fsync=off",
              "-l", str(root / "server.log"), "-w", "start"])
        try:
            yield Cluster(socket=socket)
        finally:
            _run(["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"])
