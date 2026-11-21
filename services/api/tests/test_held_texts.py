"""Held texts in their place (corpus-cleanup 4.3, issue #394) against a real database
migrated through 0043.

The stage writes each document's held texts into `documents.metadata.held_texts`.
`/toc` returns them with their links resolved, after checking them against the
chapters as it checks a contents tree; `/documents/{id}` and `/sources` return only
`held_count`; no returned `metadata` carries the list. Acceptance checks:
docs/corpus-cleanup/P4-P5-republish-expand.md, item 4.3.
"""
import contextlib
import json
import logging
from unittest.mock import patch

import asyncpg
import pytest
from fastapi import HTTPException

from app.db import _init_connection
from app.models.auth import AuthUser
from app.routes import sources
from app.routes.documents import get_document, get_document_reader, get_document_toc
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

pytestmark = pytest.mark.real_corpus_schema

USER = "00000000-0000-0000-0000-0000000000aa"
COUNCIL = "00000000-0000-0000-0000-00000000e001"   # four held texts
PAPAL = "00000000-0000-0000-0000-00000000e002"     # no held_text_url: falls back to url
PLAIN = "00000000-0000-0000-0000-00000000e003"     # holds nothing
EXCERPT = "00000000-0000-0000-0000-00000000e004"   # excerpt-only, with a list
NOLINK = "00000000-0000-0000-0000-00000000e005"    # no link anywhere

HELD_URL = "https://www.papalencyclicals.net/councils/ecum16.htm"
COUNCIL_HELD = [
    {"key": "ht-0001", "label": "Session 1", "heading": "Decrees on the matters to be treated",
     "after_anchor": None, "after_chapter_key": None, "url": None},
    {"key": "ht-0002", "label": "Session 8", "heading": "Sentence against John Wyclif",
     "after_anchor": "s8/2", "after_chapter_key": "s8", "url": None},
    {"key": "ht-0003", "label": "Session 13", "heading": "Decree on communion",
     "after_anchor": "s13/1", "after_chapter_key": "s13", "url": None},
    {"key": "ht-0004", "label": "Session 15", "heading": "Sentence against Jan Hus",
     "after_anchor": "s13/1", "after_chapter_key": "s13", "url": "https://example.org/hus"},
]
PAPAL_HELD = [{"key": "ht-0005", "label": "Paragraphs 3–10",
               "heading": "Not in the public-domain printing", "after_anchor": "p/2",
               "after_chapter_key": "p", "url": None}]


def _meta(**fields) -> str:
    return json.dumps(fields).replace("'", "''")


SEED = f"""
    INSERT INTO documents (id, collection, title, author, year, translation, metadata)
    VALUES
      ('{COUNCIL}', 'councils', 'Council of Constance', NULL, 1414, '',
       '{_meta(url="https://archive.org/details/DisciplinaryCouncils", held_text_url=HELD_URL,
               council_number=16, held_texts=COUNCIL_HELD)}'),
      ('{PAPAL}', 'encyclicals', 'Levate', 'Pope Pius IX', 1867, '',
       '{_meta(url="https://www.papalencyclicals.net/pius09/p9levate.htm", held_texts=PAPAL_HELD)}'),
      ('{PLAIN}', 'councils', 'Council of Trent', NULL, 1545, '',
       '{_meta(url="https://example.org/trent", council_number=19)}'),
      ('{EXCERPT}', 'councils', 'Lumen Gentium', 'Second Vatican Council', 1964, '',
       '{_meta(url="https://www.vatican.va/lg.html", held_texts=PAPAL_HELD)}'),
      ('{NOLINK}', 'encyclicals', 'Unlinked', NULL, 1800, '', '{_meta(held_texts=PAPAL_HELD)}');
    UPDATE documents SET reader_access = 'excerpt' WHERE id = '{EXCERPT}';

    INSERT INTO chunks (document_id, position, anchor, chapter_key, chapter_label,
                        reference, content)
    VALUES
      ('{COUNCIL}', 0, 's8/1', 's8', 'Session 8', 'Session 8, 1', 'Wyclif articles one'),
      ('{COUNCIL}', 1, 's8/2', 's8', 'Session 8', 'Session 8, 2', 'Wyclif articles two'),
      ('{COUNCIL}', 2, 's13/1', 's13', 'Session 13', 'Session 13', 'Communion under one kind'),
      ('{COUNCIL}', 3, 's15/1', 's15', 'Session 15', 'Session 15', 'Hus articles'),
      ('{PAPAL}', 0, 'p/1', 'p', 'Levate', '1', 'one'),
      ('{PAPAL}', 1, 'p/2', 'p', 'Levate', '2', 'two'),
      ('{PLAIN}', 0, 't/1', 't', 'Session 1', '1', 'trent'),
      ('{EXCERPT}', 0, 'p/2', 'p', 'Lumen Gentium', '2', 'lg'),
      ('{NOLINK}', 0, 'p/2', 'p', 'Unlinked', '2', 'two');
    -- A retired passage: no held text may follow it.
    INSERT INTO chunks (document_id, position, anchor, chapter_key, chapter_label,
                        reference, content, retired_at)
    VALUES ('{COUNCIL}', -1000000, 's8/3', 's8', 'Session 8', 'Session 8, 3', 'gap', now());
    SELECT refresh_document_outline(id) FROM documents;
"""


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-held-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(SEED)
        yield running


@contextlib.asynccontextmanager
async def _pool_on(cluster):
    pool = await asyncpg.create_pool(
        host=str(cluster.socket), user="postgres", database="postgres",
        min_size=1, max_size=3, statement_cache_size=0, init=_init_connection,
    )
    try:
        with contextlib.ExitStack() as stack:
            for name in ("documents", "sources"):
                stack.enter_context(patch(f"app.routes.{name}.get_pool", return_value=pool))
            stack.enter_context(patch("app.corpus_schema.get_pool", return_value=pool))
            stack.enter_context(patch.object(sources, "_sources_cache", None))
            yield pool
    finally:
        await pool.close()


@pytest.fixture()
async def db(cluster):
    async with _pool_on(cluster) as pool:
        yield pool


@contextlib.contextmanager
def _held_list(cluster, document_id: str, entries: list[dict]):
    """The document's stored list replaced for one test."""
    [[before]] = cluster.sql(f"SELECT metadata::text FROM documents WHERE id = '{document_id}'")
    cluster.sql(f"UPDATE documents SET metadata = jsonb_set(metadata, '{{held_texts}}', "
                f"'{json.dumps(entries)}'::jsonb) WHERE id = '{document_id}'")
    try:
        yield
    finally:
        cluster.sql(f"UPDATE documents SET metadata = '{before}'::jsonb WHERE id = '{document_id}'")


def _user():
    return AuthUser(user_id=USER, email=None)


# --------------------------------------------------------------------------- /toc

async def test_toc_returns_held_texts_in_order_with_resolved_links(db):
    toc = await get_document_toc(COUNCIL, user=_user())
    assert [c.chapter_key for c in toc.chapters] == ["s8", "s13", "s15"]
    assert [h.model_dump() for h in toc.held_texts] == [
        {"key": "ht-0001", "label": "Session 1", "heading": "Decrees on the matters to be treated",
         "after_anchor": None, "after_chapter_key": None, "url": HELD_URL},
        {"key": "ht-0002", "label": "Session 8", "heading": "Sentence against John Wyclif",
         "after_anchor": "s8/2", "after_chapter_key": "s8", "url": HELD_URL},
        {"key": "ht-0003", "label": "Session 13", "heading": "Decree on communion",
         "after_anchor": "s13/1", "after_chapter_key": "s13", "url": HELD_URL},
        # An entry's own link wins.
        {"key": "ht-0004", "label": "Session 15", "heading": "Sentence against Jan Hus",
         "after_anchor": "s13/1", "after_chapter_key": "s13", "url": "https://example.org/hus"},
    ]
    # Never any text, and the list is sent once: not again inside metadata.
    assert "held_texts" not in toc.document.metadata
    assert toc.document.metadata["held_text_url"] == HELD_URL
    assert toc.document.held_count == 4


async def test_a_null_link_falls_back_to_the_documents_url(db):
    toc = await get_document_toc(PAPAL, user=_user())
    assert [h.url for h in toc.held_texts] == [
        "https://www.papalencyclicals.net/pius09/p9levate.htm"]


async def test_an_entry_with_no_link_is_left_out_and_logged(db, caplog):
    with caplog.at_level(logging.WARNING):
        toc = await get_document_toc(NOLINK, user=_user())
    assert toc.held_texts == []
    assert "ht-0005" in caplog.text and "no link" in caplog.text


@pytest.mark.parametrize("change, why", [
    ({1: {"after_chapter_key": "s9"}}, "missing chapter"),
    ({1: {"after_anchor": "s8/3"}}, "missing passage"),         # retired
    ({1: {"after_anchor": "s13/1"}}, "missing passage"),        # in another chapter
    ({3: {"after_anchor": "s8/2", "after_chapter_key": "s8"}}, "out of reading order"),
    ({0: {"after_chapter_key": "s8"}}, "names a chapter but no passage"),
    ({3: {"heading": ""}}, "lacks a key, label or heading"),
    ({1: {"after_anchor": ["s8/2"]}}, "malformed place"),
])
async def test_a_stale_list_is_dropped_whole_with_a_warning(db, cluster, caplog, change, why):
    entries = json.loads(json.dumps(COUNCIL_HELD))
    for index, fields in change.items():
        entries[index].update(fields)
    with _held_list(cluster, COUNCIL, entries), caplog.at_level(logging.WARNING):
        toc = await get_document_toc(COUNCIL, user=_user())
    assert toc.held_texts == []
    assert [c.chapter_key for c in toc.chapters] == ["s8", "s13", "s15"]
    assert "stale" in caplog.text and why in caplog.text


async def test_an_excerpt_only_document_still_answers_403(db):
    with pytest.raises(HTTPException) as caught:
        await get_document_toc(EXCERPT, user=_user())
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "reader_restricted"


async def test_a_document_without_the_key_serves_todays_toc(db):
    toc = await get_document_toc(PLAIN, user=_user())
    assert json.loads(toc.model_dump_json(exclude={"document": {"facts"}})) == {
        "document": {
            "id": PLAIN, "collection": "councils", "title": "Council of Trent", "author": None,
            "year": 1545, "translation": "",
            "metadata": {"url": "https://example.org/trent", "council_number": 19},
            "chunk_count": 1, "reader_access": "full", "source_url": None, "works": [],
            "status": "current", "held_count": 0,
        },
        "chapters": [{"chapter_key": "t", "chapter_label": "Session 1"}],
        "contents": None,
        "held_texts": [],
    }


# --------------------------------------------------------------------------- the others

async def test_documents_and_reader_send_the_count_not_the_list(db):
    document = await get_document(COUNCIL, user=_user())
    assert document.held_count == 4 and "held_texts" not in document.metadata
    chapter = await get_document_reader(COUNCIL, chapter="s8", anchor=None, user=_user())
    assert chapter.document.held_count == 4
    assert "held_texts" not in chapter.document.metadata
    assert (await get_document(PLAIN, user=_user())).held_count == 0


async def test_sources_carry_the_count_and_no_list(db):
    listed = {s.id: s for s in (await sources.get_sources(user=_user())).sources}
    assert listed[COUNCIL].held_count == 4
    assert listed[PAPAL].held_count == 1
    assert listed[PLAIN].held_count == 0
    assert all("held_texts" not in (s.metadata or {}) for s in listed.values())
    assert listed[COUNCIL].metadata["council_number"] == 16
