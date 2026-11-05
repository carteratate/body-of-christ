"""CORPUS_READ_SCHEMA: an in-process run reads a staged corpus, and nothing else can.

The pre-cutover checks (4.2) run the search pipeline in process with
`CORPUS_READ_SCHEMA=staging`. The tables in `staging` have the live names, so every
unqualified query reads the staged corpus and every user table still resolves to
`public`. A run that quietly read `public` would pass those checks against the wrong
corpus, so these tests run on a real server, and the pool refuses a connection the
override does not hold on.
"""
import pytest
from unittest.mock import AsyncMock, patch

import asyncpg

from app import db
from app.config import settings
from tests.pg_cluster import local_cluster

SCHEMA = """
    CREATE TABLE chunks (id int PRIMARY KEY, content text NOT NULL);
    CREATE TABLE bookmarks (id int PRIMARY KEY);
    INSERT INTO chunks VALUES (1, 'live text');
    INSERT INTO bookmarks VALUES (7);
    CREATE SCHEMA staging;
    CREATE TABLE staging.chunks (LIKE chunks INCLUDING ALL);
    INSERT INTO staging.chunks VALUES (1, 'staged text');
"""


@pytest.fixture()
def cluster(monkeypatch):
    with local_cluster("tc-read-override-") as running:
        running.sql(SCHEMA)
        monkeypatch.setattr(settings, "database_url",
                            f"postgresql://postgres@/postgres?host={running.socket}")
        yield running


@pytest.fixture()
async def staged_pool(cluster, monkeypatch):
    monkeypatch.setattr(settings, "corpus_read_schema", "staging")
    await db.init_pool()
    yield db.get_pool()
    await db.close_pool()


async def test_the_pool_reads_staging_first_and_public_after(staged_pool):
    assert await staged_pool.fetchval("SHOW search_path") == "staging, public"
    assert await staged_pool.fetchval("SELECT content FROM chunks") == "staged text"
    assert await staged_pool.fetchval("SELECT id FROM bookmarks") == 7


async def test_every_table_is_read_only(staged_pool):
    for statement in ("UPDATE chunks SET content = 'x'", "INSERT INTO bookmarks VALUES (8)"):
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            await staged_pool.execute(statement)


async def test_the_default_changes_nothing(cluster, monkeypatch):
    monkeypatch.setattr(settings, "corpus_read_schema", "public")
    await db.init_pool()
    try:
        pool = db.get_pool()
        assert await pool.fetchval("SELECT content FROM chunks") == "live text"
        await pool.execute("INSERT INTO bookmarks VALUES (9)")
    finally:
        await db.close_pool()


async def test_a_database_with_no_staged_corpus_refuses(cluster, monkeypatch):
    """After `publish.py cleanup`, `search_path` would fall through to live tables."""
    cluster.sql("DROP TABLE staging.chunks")
    monkeypatch.setattr(settings, "corpus_read_schema", "staging")
    with pytest.raises(RuntimeError, match="no staged corpus"):
        await db.init_pool()
    assert db.get_pool() is None


async def test_a_setting_that_does_not_hold_refuses(cluster, monkeypatch):
    """A transaction-mode pooler would lose a `SET`. Postgres reports `on` here, so the
    read-back cannot match, which is how such a connection would look."""
    monkeypatch.setattr(settings, "corpus_read_schema", "staging")
    monkeypatch.setitem(db._READ_OVERRIDE["staging"], "default_transaction_read_only", "yes")
    with pytest.raises(RuntimeError, match="did not hold"):
        await db.init_pool()
    assert db.get_pool() is None


async def test_read_only_survives_the_reset_on_release(staged_pool):
    """asyncpg runs `RESET ALL` when a connection returns to the pool, which clears a
    `SET`. Supabase's pooler drops startup settings, so `SET` is the only way in."""
    for _ in range(4):
        async with staged_pool.acquire() as conn:
            assert await conn.fetchval("SHOW default_transaction_read_only") == "on"
            assert await conn.fetchval("SHOW search_path") == "staging, public"
            with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
                await conn.execute("CREATE TEMP TABLE scratch (id int)")


async def test_an_unknown_schema_refuses(cluster, monkeypatch):
    monkeypatch.setattr(settings, "corpus_read_schema", "stagng")
    with pytest.raises(RuntimeError, match="CORPUS_READ_SCHEMA"):
        await db.init_pool()


@pytest.mark.parametrize("value", ["staging", "stagng", ""])
async def test_the_app_refuses_to_start(monkeypatch, value):
    from app.main import app, lifespan

    monkeypatch.setattr(settings, "corpus_read_schema", value)
    init_pool = AsyncMock()
    with patch("app.main.init_pool", new=init_pool):
        with pytest.raises(RuntimeError, match="CORPUS_READ_SCHEMA"):
            async with lifespan(app):
                pass
    init_pool.assert_not_awaited()
