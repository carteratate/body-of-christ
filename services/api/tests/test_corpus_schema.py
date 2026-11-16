"""corpus_schema: which 0042 objects exist, and today's SQL without them (2.2b, 2.4a)."""
import dataclasses
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from app import corpus_schema
from app.corpus_lifecycle import read_elsewhere_url
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)
from tests.test_document_form_migration import FORM_MIGRATION

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


CODE = {"url": "https://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html",
        "official_latin_urls": {"can/295": "https://www.vatican.va/la/295.html",
                                "can/700": "javascript:alert(1)"}}


@pytest.mark.parametrize("anchor,expected", [
    ("can/295", "https://www.vatican.va/la/295.html"),
    ("can/295#retired-p4", "https://www.vatican.va/la/295.html"),  # 2.2w's suffix
    ("can/296", None),        # not in the map: the Code's index page holds no canon
    ("can/700", None),        # not a web link
    (None, None),
])
def test_an_amended_canon_links_to_its_latin(anchor, expected):
    """2.4f: a canon-law passage removed for a translation in preparation links to its
    own Latin, from the Code's `official_latin_urls`, never the Code's index page."""
    assert read_elsewhere_url("translation-in-preparation", "canon-law", False, CODE,
                              anchor) == expected


def test_other_canon_law_removals_keep_the_general_rules():
    assert read_elsewhere_url("rule-a", "canon-law", False, CODE, "can/295") is None
    assert read_elsewhere_url("awaiting-permission", "canon-law", False, CODE,
                              "can/295") == CODE["url"]
    assert read_elsewhere_url("translation-in-preparation", "canon-law", True, CODE,
                              "can/295") == CODE["url"]
    assert read_elsewhere_url("translation-in-preparation", "councils", False,
                              {"url": "https://example.org/c"}, "can/295") == \
        "https://example.org/c"


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
    # 0044 adds documents.form (issue #330); everything else reads as before.
    cluster.migrate(FORM_MIGRATION.name)
    assert await _probe(cluster) == dataclasses.replace(ALL, form=True)
