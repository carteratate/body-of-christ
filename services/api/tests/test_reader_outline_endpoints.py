"""The reader endpoints return the same answers from the outline as from chunks.

Runs the real routes against a throwaway PostgreSQL cluster with migration 0037
applied, first before a document is outlined (the fallback path) and then after
refresh_document_outline (the outline path), and requires identical responses.
"""

from unittest.mock import patch

import asyncpg
import pytest
from fastapi import HTTPException

from app.db import _init_connection
from app.models.auth import AuthUser
from app.routes import sources
from app.routes.documents import get_document, get_document_reader, get_document_toc
from app.routes.sources import get_sources
from tests.pg_cluster import CORPUS_SCHEMA, local_cluster

DOC = "00000000-0000-0000-0000-00000000000a"
USER = AuthUser(user_id="u", email=None)


# Four chapters; q2 is split around q3, as 31 production keys are.
SEED = f"""
    INSERT INTO documents (id, collection, title, translation, metadata)
    VALUES ('{DOC}', 'summa', 'Summa', '', '{{"part": "I"}}');
    INSERT INTO chunks (document_id, position, content, anchor, chapter_key, chapter_label, unit_label)
    VALUES
        ('{DOC}', 0, 'a', 'q1/a1', 'q1', 'Question 1', 'Article 1'),
        ('{DOC}', 1, 'b', 'q1/a2', 'q1', 'Question 1', 'Article 2'),
        ('{DOC}', 2, 'c', 'q2/a1', 'q2', 'Question 2', 'Article 1'),
        ('{DOC}', 3, 'd', 'q3/a1', 'q3', 'Question 3', 'Article 1'),
        ('{DOC}', 4, 'e', 'q2/a2', 'q2', 'Question 2', 'Article 2'),
        ('{DOC}', 5, 'f', 'q4/a1', 'q4', 'Question 4', 'Article 1');
"""
CHAPTERS = ["q1", "q2", "q3", "q4"]


@pytest.fixture()
async def db():
    """The cluster, with the routes' pool pointed at it."""
    with local_cluster("tc-reader-") as cluster:
        cluster.sql(CORPUS_SCHEMA)
        cluster.migrate("0037_document_outline.sql")
        cluster.sql(SEED)
        db_pool = await asyncpg.create_pool(
            host=str(cluster.socket), user="postgres", database="postgres",
            min_size=1, max_size=2, statement_cache_size=0, init=_init_connection,
        )
        try:
            with patch("app.routes.documents.get_pool", return_value=db_pool), \
                 patch("app.routes.sources.get_pool", return_value=db_pool):
                yield cluster
        finally:
            await db_pool.close()


async def _reader_snapshot():
    """Everything the reader shows about DOC's structure, via the real routes."""
    toc = await get_document_toc(DOC, user=USER)
    first = await get_document_reader(DOC, anchor=None, chapter=None, user=USER)
    by_anchor = await get_document_reader(DOC, anchor="q3/a1", chapter=None, user=USER)
    chapters = {
        key: await get_document_reader(DOC, anchor=None, chapter=key, user=USER)
        for key in CHAPTERS
    }
    with patch.object(sources, "_sources_cache", None):
        listed = await get_sources(user=USER)
    return {
        "toc": [(c.chapter_key, c.chapter_label) for c in toc.chapters],
        "document": (await get_document(DOC, user=USER)).model_dump(),
        "first": first.chapter_key,
        "by_anchor": (by_anchor.chapter_key, by_anchor.prev_chapter_key, by_anchor.next_chapter_key),
        "neighbors": {k: (c.prev_chapter_key, c.next_chapter_key) for k, c in chapters.items()},
        "passages": {k: [p.anchor for p in c.passages] for k, c in chapters.items()},
        "source_count": [s.chunk_count for s in listed.sources],
    }


async def test_outline_and_fallback_serve_identical_reader_responses(db):
    assert db.sql(f"SELECT chunk_count IS NULL FROM documents WHERE id = '{DOC}'") == [["t"]]
    fallback = await _reader_snapshot()

    db.sql(f"SELECT refresh_document_outline('{DOC}')")
    outlined = await _reader_snapshot()

    assert outlined == fallback
    # And both are right, not merely equal.
    assert outlined["toc"] == [("q1", "Question 1"), ("q2", "Question 2"),
                               ("q3", "Question 3"), ("q4", "Question 4")]
    assert outlined["first"] == "q1"
    assert outlined["neighbors"] == {
        "q1": (None, "q2"), "q2": ("q1", "q3"), "q3": ("q2", "q4"), "q4": ("q3", None),
    }
    assert outlined["passages"]["q2"] == ["q2/a1", "q2/a2"]
    assert outlined["by_anchor"] == ("q3", "q2", "q4")
    assert outlined["document"]["chunk_count"] == 6
    assert outlined["document"]["metadata"] == {"part": "I"}
    assert outlined["source_count"] == [6]


async def test_an_outlined_document_takes_its_structure_from_the_outline(db):
    """Once outlined, chunks are read only for the requested chapter's passages.

    Proven by changing structure in chunks with the invalidation triggers disabled, so
    the outline stays current by its own flag: a route still deriving the TOC or
    neighbors from chunks would answer differently.
    """
    db.sql(f"""
        SELECT refresh_document_outline('{DOC}');
        ALTER TABLE chunks DISABLE TRIGGER USER;
        UPDATE chunks SET chapter_label = 'stale' WHERE document_id = '{DOC}';
        UPDATE chunks SET chapter_key = 'renamed' WHERE document_id = '{DOC}' AND chapter_key = 'q3';
        ALTER TABLE chunks ENABLE TRIGGER USER;
    """)

    toc = await get_document_toc(DOC, user=USER)
    chapter = await get_document_reader(DOC, anchor=None, chapter="q2", user=USER)

    assert [c.chapter_label for c in toc.chapters] == ["Question 1", "Question 2",
                                                       "Question 3", "Question 4"]
    assert (chapter.prev_chapter_key, chapter.next_chapter_key) == ("q1", "q3")


async def test_a_writer_that_skips_the_refresh_cannot_leave_a_stale_outline(db):
    """An older datapipeline or a manual fix changes chunks without refreshing: the
    triggers clear the outline's flag and the reader serves the new structure."""
    db.sql(f"""
        SELECT refresh_document_outline('{DOC}');
        UPDATE chunks SET chapter_key = 'renamed', chapter_label = 'Renamed'
            WHERE document_id = '{DOC}' AND chapter_key = 'q3';
    """)

    toc = await get_document_toc(DOC, user=USER)
    chapter = await get_document_reader(DOC, anchor=None, chapter="q2", user=USER)

    assert [c.chapter_key for c in toc.chapters] == ["q1", "q2", "renamed", "q4"]
    assert (chapter.prev_chapter_key, chapter.next_chapter_key) == ("q1", "renamed")


async def test_a_chapter_missing_from_the_outline_falls_back_to_chunks(db):
    """If the outline is flagged current but lacks a chapter (only possible with the
    triggers bypassed), the reader derives neighbors instead of guessing."""
    db.sql(f"""
        SELECT refresh_document_outline('{DOC}');
        ALTER TABLE chunks DISABLE TRIGGER USER;
        INSERT INTO chunks (document_id, position, content, anchor, chapter_key, chapter_label)
        VALUES ('{DOC}', 6, 'g', 'q5/a1', 'q5', 'Question 5');
        ALTER TABLE chunks ENABLE TRIGGER USER;
    """)

    chapter = await get_document_reader(DOC, anchor=None, chapter="q5", user=USER)

    assert (chapter.prev_chapter_key, chapter.next_chapter_key) == ("q4", None)


@pytest.mark.parametrize("outlined", [False, True])
async def test_not_found_answers_match_on_both_paths(db, outlined):
    missing_doc = "00000000-0000-0000-0000-0000000000ff"
    empty_doc = "00000000-0000-0000-0000-0000000000ee"
    db.sql(f"INSERT INTO documents (id, collection, title) VALUES ('{empty_doc}', 'bible', 'E')")
    if outlined:
        db.sql(f"SELECT refresh_document_outline('{DOC}'); SELECT refresh_document_outline('{empty_doc}')")

    async def status(call):
        with pytest.raises(HTTPException) as caught:
            await call
        return caught.value.status_code, caught.value.detail

    assert await status(get_document_toc(missing_doc, user=USER)) == (404, "Document not found")
    assert await status(get_document_reader(DOC, anchor=None, chapter="nope", user=USER)) == (
        404, "Chapter not found")
    assert await status(get_document_reader(empty_doc, anchor=None, chapter=None, user=USER)) == (
        404, "Document has no readable passages")
    toc = await get_document_toc(empty_doc, user=USER)
    assert (toc.chapters, toc.document.chunk_count) == ([], 0)
