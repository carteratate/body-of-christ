"""CORPUS_READ_SCHEMA: an in-process run reads a staged corpus, and nothing else can.

The pre-cutover checks (4.2) run the search pipeline in process with
`CORPUS_READ_SCHEMA=staging`. The tables in `staging` have the live names, so every
unqualified query reads the staged corpus and every user table still resolves to
`public`. A run that quietly read `public` would pass those checks against the wrong
corpus, so these tests run on a real server, and the pool refuses a connection the
override did not reach.
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


async def test_a_connection_the_override_did_not_reach_refuses(cluster, monkeypatch):
    """A pooler may drop startup settings without saying so."""
    monkeypatch.setattr(settings, "corpus_read_schema", "staging")
    real_create_pool = asyncpg.create_pool

    def pool_without_startup_settings(*args, server_settings, **kwargs):
        return real_create_pool(*args, **kwargs)

    monkeypatch.setattr(db.asyncpg, "create_pool", pool_without_startup_settings)
    with pytest.raises(RuntimeError, match="did not reach the connection"):
        await db.init_pool()
    assert db.get_pool() is None


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
