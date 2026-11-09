"""corpus_schema: which 0042 objects exist, and today's SQL without them (2.2b, 2.4a)."""
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from app import corpus_schema
from app.corpus_lifecycle import read_elsewhere_url
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

pytestmark = pytest.mark.real_corpus_schema

ALL = corpus_schema.CorpusSchema(True, True, True, True, True, True)


def test_visible_is_empty_without_0042():
    assert corpus_schema.LEGACY.visible("c") == ""
    assert ALL.visible("c") == " AND c.retired_at IS NULL"


async def test_a_failed_probe_reads_as_legacy_and_is_not_cached():
    pool = MagicMock(fetch=AsyncMock(side_effect=OSError("down")))
    assert await corpus_schema.current(pool) == corpus_schema.LEGACY
    assert corpus_schema._cached is None


async def test_the_probe_is_cached():
    pool = MagicMock(fetch=AsyncMock(return_value=[]))
    await corpus_schema.current(pool)
    await corpus_schema.current(pool)
    assert pool.fetch.await_count == 1


async def test_a_missing_object_invalidates_and_retries_as_legacy(monkeypatch):
    monkeypatch.setattr(corpus_schema, "_cached", ALL)
    monkeypatch.setattr(corpus_schema, "_cached_at", float("inf"))
    seen = []

    async def query(schema):
        seen.append(schema)
        if schema.retired:
            raise asyncpg.UndefinedColumnError("column c.retired_at does not exist")
        return "legacy rows"

    assert await corpus_schema.run_with_fallback(query) == "legacy rows"
    assert seen == [ALL, corpus_schema.LEGACY]
    assert corpus_schema._cached is None


@pytest.mark.parametrize("reason,collection,document_scope,expected", [
    ("awaiting-permission", "papal-documents", True, "held"),
    ("translation-in-preparation", "encyclicals", True, "held"),
    ("awaiting-permission", "papal-documents", False, "held"),
    ("translation-in-preparation", "councils", False, "held"),
    ("translation-in-preparation", "church-fathers", False, None),
    ("rule-a", "church-fathers", True, None),
    ("rolled-back", "councils", False, None),
])
def test_read_elsewhere_url_rules(reason, collection, document_scope, expected):
    metadata = {"held_text_url": "https://example.org/held", "url": "https://example.org/url"}
    url = read_elsewhere_url(reason, collection, document_scope, metadata)
    assert url == (None if expected is None else "https://example.org/held")


def test_read_elsewhere_url_falls_back_to_the_documents_url():
    assert read_elsewhere_url("awaiting-permission", "encyclicals", True,
                              {"url": "https://www.papalencyclicals.net/x"}) == \
        "https://www.papalencyclicals.net/x"
    assert read_elsewhere_url("awaiting-permission", "encyclicals", True,
                              {"url": "javascript:alert(1)"}) is None
    assert read_elsewhere_url("awaiting-permission", "encyclicals", True, None) is None


@pytest.fixture()
def cluster():
    with local_cluster("tc-schema-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER)
        yield running


async def _probe(cluster):
    conn = await asyncpg.connect(host=str(cluster.socket), user="postgres",
                                 database="postgres")
    try:
        return await corpus_schema.probe(conn)
    finally:
        await conn.close()


async def test_probe_against_a_database_before_and_after_0042(cluster):
    assert await _probe(cluster) == corpus_schema.LEGACY
    cluster.migrate(SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
    assert await _probe(cluster) == ALL
