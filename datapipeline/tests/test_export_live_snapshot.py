"""export_live_snapshot.py reads production, so it must be unable to change it: the session
is read only before the first query, the transaction is read only, and every statement it
sends is a SELECT. Then the files it writes, against a fake and a throwaway PostgreSQL."""
import asyncio
import gzip
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from checks.health import load_snapshot
from scripts import export_live_snapshot as E

DOC = "11111111-1111-1111-1111-111111111111"
P1 = "22222222-2222-2222-2222-222222222222"
P2 = "33333333-3333-3333-3333-333333333333"


class FakeConnection:
    """Records every statement; answers the exporter's queries with tiny rows."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.transactions: list[dict] = []
        self.in_transaction = False

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql))

    @asynccontextmanager
    async def transaction(self, **kwargs):
        self.transactions.append(kwargs)
        self.calls.append(("transaction", repr(sorted(kwargs.items()))))
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql))
        if sql == E.READ_ONLY_CHECK_SQL:
            return "on" if self.in_transaction else "off"
        if sql == E.TABLE_EXISTS_SQL:
            return args[0] != "public.retrieval_labels"     # one table absent
        return 7

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql))
        if sql == E.PASSAGES_SQL:
            return [dict(id=P1, document_id=DOC, collection="summa", title="T", author="A",
                         anchor="q1/0", chapter_key="q1", chapter_label="Q 1",
                         reference="R", unit_label="Objection 1", position=0,
                         content="Text one."),
                    dict(id=P2, document_id=DOC, collection="summa", title="T", author="A",
                         anchor="q1/1", chapter_key="q1", chapter_label="Q 1",
                         reference="R", unit_label="Objection 1", position=1,
                         content="Text two.")]
        if sql == E.DOCUMENT_COLUMNS_SQL:
            return [{"column_name": c} for c in E.DOCUMENT_FIELDS if c != "chunk_count"]
        if sql.startswith("SELECT id::text AS id"):
            return [dict(id=DOC, collection="summa", title="T", author="A", year=None,
                         translation="", chunk_count=None, metadata='{"k": 1}')]
        if "FROM public.retrievals" in sql:
            return [{"chunk_id": P1, "n": 3}]
        if "FROM public.bookmarks" in sql:
            return [{"chunk_id": P2, "n": 1}]
        if "FROM public.guest_trial_retrievals" in sql:
            return [{"chunk_id": P1, "n": 2}]
        if sql == E.READING_PROGRESS_SQL:
            return [{"document_id": DOC, "chapter_key": "q1", "anchor": None, "n": 1},
                    {"document_id": DOC, "chapter_key": "q1", "anchor": "q1/1", "n": 2}]
        raise AssertionError(f"unexpected query {sql}")


def _statements(conn: FakeConnection) -> list[str]:
    return [" ".join(sql.split()) for kind, sql in conn.calls if kind != "transaction"]


def test_session_is_read_only_before_the_first_query_and_every_query_is_select():
    conn = FakeConnection()
    asyncio.run(E.read_live(conn))
    assert conn.calls[0] == ("execute", E.READ_ONLY)
    assert conn.calls[1][0] == "transaction"
    assert conn.transactions == [{"isolation": "repeatable_read", "readonly": True}]
    statements = _statements(conn)[1:]
    assert statements, "no queries recorded"
    for sql in statements:
        assert sql.upper().startswith("SELECT "), sql
        # A SELECT cannot hide a write behind a data-modifying CTE or a locking clause.
        for word in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE", "ALTER ", "CREATE ",
                     "DROP ", "GRANT ", " FOR UPDATE", " FOR SHARE", "NEXTVAL", "SETVAL"):
            assert word not in sql.upper(), sql
    # The read-only check is the first statement inside the transaction.
    assert statements[0] == E.READ_ONLY_CHECK_SQL


def test_refuses_when_the_transaction_is_not_read_only():
    conn = FakeConnection()

    async def off(sql, *args):
        return "off"
    conn.fetchval = off
    with pytest.raises(RuntimeError, match="not read only"):
        asyncio.run(E.read_live(conn))
    assert not [c for c in conn.calls if c[0] == "fetch"]


def test_snapshot_files_hold_counts_only_and_load_with_the_health_reader(tmp_path):
    data = asyncio.run(E.read_live(FakeConnection()))
    index = tmp_path / "snapshots.json"
    out = E.write_snapshot(data, str(tmp_path / "snapshots"), "2026-10-05",
                           "2026-10-05T12:00:00Z", str(index))

    with gzip.open(os.path.join(out, E.PASSAGES_FILE), "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    assert [tuple(r) for r in rows] == [E.PASSAGE_FIELDS] * 2
    docs = [json.loads(line) for line in open(os.path.join(out, E.DOCUMENTS_FILE))]
    assert docs[0]["metadata"] == {"k": 1} and docs[0]["chunk_count"] is None

    refs = json.load(open(os.path.join(out, E.REFERENCES_FILE)))
    assert refs["passages"] == {
        P1: {"retrievals": 3, "bookmarks": 0, "guest_trial_retrievals": 2, "retrieval_labels": 0},
        P2: {"retrievals": 0, "bookmarks": 1, "guest_trial_retrievals": 0, "retrieval_labels": 0}}
    assert refs["documents"] == {DOC: {"reading_progress": 3, "positions": [
        {"chapter_key": "q1", "anchor": None, "rows": 1},
        {"chapter_key": "q1", "anchor": "q1/1", "rows": 2}]}}
    text = json.dumps(refs)
    assert "user_id" not in text and "query" not in text

    meta = json.load(open(os.path.join(out, E.SNAPSHOT_FILE)))
    assert meta["tables"]["retrieval_labels"] is None      # absent table
    for name, digest in meta["files"].items():
        assert E._sha256(os.path.join(out, name)) == digest
    entry = json.load(open(index))["snapshots"][0]
    assert entry["files"] == meta["files"] and "passages" not in json.dumps(entry["tables"])

    docs_by_collection = load_snapshot(out)
    [doc] = docs_by_collection["summa"]
    assert [p.metadata["passage_id"] for p in doc.passages] == [P1, P2]
    assert doc.passages[0].unit_label == "Objection 1"


def test_snapshot_is_never_overwritten_and_index_keeps_other_dates(tmp_path):
    data = asyncio.run(E.read_live(FakeConnection()))
    root, index = str(tmp_path / "s"), str(tmp_path / "snapshots.json")
    first = E.write_snapshot(data, root, "2026-10-05", "t1", index)
    E.write_snapshot(data, root, "2026-10-06", "t2", index)
    with pytest.raises(FileExistsError):
        E.write_snapshot(data, root, "2026-10-05", "t3", index)
    assert sorted(os.listdir(root)) == ["2026-10-05", "2026-10-06"]    # no temp left
    assert [e["date"] for e in json.load(open(index))["snapshots"]] == ["2026-10-05",
                                                                       "2026-10-06"]
    # Equal content gives equal hashes (the gzip header carries no time).
    second = json.load(open(os.path.join(root, "2026-10-06", E.SNAPSHOT_FILE)))["files"]
    assert json.load(open(os.path.join(first, E.SNAPSHOT_FILE)))["files"] == second


# --------------------------------------------------------------------------- real database

SCHEMA = f"""
    CREATE TABLE documents (id uuid PRIMARY KEY, collection text NOT NULL, title text NOT NULL,
        author text, year int, translation text, metadata jsonb, chunk_count int);
    CREATE TABLE chunks (id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id),
        content text NOT NULL, position int NOT NULL, reference text, anchor text,
        chapter_key text, chapter_label text, unit_label text);
    CREATE TABLE retrievals (id serial, chunk_id uuid REFERENCES chunks(id), user_id uuid);
    CREATE TABLE bookmarks (id serial, chunk_id uuid REFERENCES chunks(id), user_id uuid);
    CREATE TABLE reading_progress (user_id uuid, document_id uuid, chapter_key text, anchor text);
    INSERT INTO documents VALUES ('{DOC}', 'summa', 'T', 'A', NULL, '', '{{"k": 1}}', 1);
    INSERT INTO chunks VALUES ('{P1}', '{DOC}', 'Text one.', 0, 'R', 'q1/0', 'q1', 'Q 1', NULL);
    INSERT INTO retrievals (chunk_id, user_id) VALUES ('{P1}', gen_random_uuid()),
                                                      ('{P1}', gen_random_uuid());
    INSERT INTO reading_progress VALUES (gen_random_uuid(), '{DOC}', 'q1', 'q1/0');
"""


def _run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture()
def database():
    if os.geteuid() == 0:
        pytest.skip("initdb cannot run as root")
    if not all(shutil.which(c) for c in ("initdb", "pg_ctl")):
        pytest.skip("local PostgreSQL tools are unavailable")
    short_tmp = "/private/tmp" if Path("/private/tmp").is_dir() else "/tmp"
    with tempfile.TemporaryDirectory(prefix="tc-export-", dir=short_tmp) as directory:
        root = Path(directory)
        (root / "socket").mkdir()
        _run(["initdb", "-D", str(root / "data"), "-U", "postgres", "-A", "trust",
              "--no-instructions"])
        _run(["pg_ctl", "-D", str(root / "data"), "-o",
              f"-c listen_addresses='' -c unix_socket_directories='{root / 'socket'}' "
              "-c fsync=off", "-l", str(root / "server.log"), "-w", "start"])
        try:
            yield str(root / "socket")
        finally:
            _run(["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"])


def test_export_against_postgres_reads_everything_and_cannot_write(database, tmp_path):
    import asyncpg

    async def scenario():
        setup = await asyncpg.connect(host=database, user="postgres", database="postgres")
        await setup.execute(SCHEMA)
        await setup.close()
        conn = await asyncpg.connect(host=database, user="postgres", database="postgres")
        try:
            data = await E.read_live(conn)
            # The session stays read only after the export's transaction ends.
            with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
                await conn.execute("DELETE FROM chunks")
        finally:
            await conn.close()
        return data

    data = asyncio.run(scenario())
    assert [p["id"] for p in data["passages"]] == [P1]
    assert data["tables"] == {"chunks": 1, "documents": 1, "retrievals": 2, "bookmarks": 0,
                              "guest_trial_retrievals": None, "retrieval_labels": None,
                              "reading_progress": 1}
    assert data["references"]["passages"][P1]["retrievals"] == 2
    assert data["documents"][0]["metadata"] == {"k": 1}
    out = E.write_snapshot(data, str(tmp_path / "s"), "2026-10-05", "t", str(tmp_path / "i.json"))
    assert load_snapshot(out)["summa"][0].passages[0].metadata["passage_id"] == P1
