"""Corpus cleanup 2.4f against a real database migrated through 0043.

Three keys of a passage's `metadata` reach the reader, saved searches and bookmarks:
`text_source` (1.2f's scanned-text label), `text_status` and `official_latin_url`
(1.5b's unofficial-English canons). A canon amended with no English, retired as 1.5b's
removal entries say, links to its Latin through the Code's `official_latin_urls`.

The acceptance checks are docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.4f.
"""
import pytest

from app.corpus_lifecycle import CorpusLifecycleError
from app.routes.bookmarks import list_bookmarks
from app.routes.documents import get_document_reader
from app.routes.search import get_search_results
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)
from tests.test_corpus_lifecycle import USER, USER_TABLES, _pool_on, _user

pytestmark = pytest.mark.real_corpus_schema

SEARCH = "00000000-0000-0000-0000-0000000000bb"
CODE = "00000000-0000-0000-0000-00000000e001"     # canon-law
FATHERS = "00000000-0000-0000-0000-00000000e002"  # church-fathers, one scanned passage

P_PLAIN = "00000000-0000-0000-0000-0000000000f1"     # can/1, no labels
P_UNOFFICIAL = "00000000-0000-0000-0000-0000000000f2"  # can/1108, ORE English
P_RETIRED = "00000000-0000-0000-0000-0000000000f3"   # can/295, amended, no English
P_SUFFIXED = "00000000-0000-0000-0000-0000000000f4"  # can/579#retired-rel-4
P_SCANNED = "00000000-0000-0000-0000-0000000000f5"   # OCR text

LATIN_1108 = "https://www.vatican.va/la/de-concordia.html"
LATIN_295 = "https://www.vatican.va/it/le-prelature-personali.html"
LATIN_579 = "https://www.vatican.va/la/authenticum-charismatis.html"
INDEX = "https://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html"

SEED = f"""
    INSERT INTO corpus_publishes (id, collections, qdrant_collection)
    VALUES ('rel-4', ARRAY['canon-law'], 'chunks-rel-4');

    INSERT INTO documents (id, collection, title, author, year, translation, metadata)
    VALUES ('{CODE}', 'canon-law', 'Code of Canon Law', NULL, 1983, '',
            '{{"url": "{INDEX}", "official_latin_urls":
               {{"can/295": "{LATIN_295}", "can/579": "{LATIN_579}"}}}}'),
           ('{FATHERS}', 'church-fathers', 'Scanned Works', 'Aphrahat', 345, '', '{{}}');

    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, chapter_label,
                        reference, content, metadata)
    VALUES
      ('{P_PLAIN}', '{CODE}', 0, 'can/1', 'book-1', 'Book I', 'Can. 1', 'canon one', NULL),
      ('{P_UNOFFICIAL}', '{CODE}', 1, 'can/1108', 'book-1', 'Book I', 'Can. 1108',
       'canon 1108', '{{"text_status": "unofficial_english",
                       "official_latin_url": "{LATIN_1108}", "amended": true}}'),
      ('{P_SCANNED}', '{FATHERS}', 0, 'd1/p1', 'd1', 'Demonstration 1', 'Dem. 1.1',
       'scanned text', '{{"text_source": "ocr", "scan_id": "aphrahat-1869"}}');
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, chapter_label,
                        reference, content, retired_at)
    VALUES
      ('{P_RETIRED}', '{CODE}', -1000000, 'can/295', 'book-1', 'Book I', 'Can. 295',
       'old 295', now()),
      ('{P_SUFFIXED}', '{CODE}', -1000001, 'can/579#retired-rel-4', 'book-1', 'Book I',
       'Can. 579', 'old 579', now());

    INSERT INTO corpus_tombstones (entity, id, document_id, retired_at, publish_id,
                                   removal_key, rule, reason_code, public_reason,
                                   church_act, snapshot)
    VALUES
      ('passage', '{P_RETIRED}', '{CODE}', now(), 'rel-4', 'rm-1948', 'other',
       'translation-in-preparation',
       'Canon 295 was amended in 2023; no English translation is available.', NULL,
       '{{"collection": "canon-law", "title": "Code of Canon Law", "author": null,
         "reference": "Can. 295", "chapter_label": "Book I"}}'),
      ('passage', '{P_SUFFIXED}', '{CODE}', now(), 'rel-4', 'rm-1950', 'other',
       'translation-in-preparation',
       'Canon 579 was amended in 2020; no English translation is available.', NULL,
       '{{"collection": "canon-law", "title": "Code of Canon Law", "author": null,
         "reference": "Can. 579", "chapter_label": "Book I"}}');

    INSERT INTO searches (id, user_id, query, filters, result_count)
    VALUES ('{SEARCH}', '{USER}', 'marriage', '{{"collections": ["canon-law"]}}', 4);
    INSERT INTO retrievals (search_id, chunk_id, rank, reranker_score, explanation) VALUES
      ('{SEARCH}', '{P_PLAIN}', 1, 0.9, NULL),
      ('{SEARCH}', '{P_UNOFFICIAL}', 2, 0.8, NULL),
      ('{SEARCH}', '{P_RETIRED}', 3, 0.7, NULL),
      ('{SEARCH}', '{P_SCANNED}', 4, 0.6, NULL);
    INSERT INTO bookmarks (user_id, chunk_id) VALUES
      ('{USER}', '{P_UNOFFICIAL}'), ('{USER}', '{P_SCANNED}'), ('{USER}', '{P_PLAIN}');
"""

LABELS = ("text_source", "text_status", "official_latin_url")


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-text-labels-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(USER_TABLES)
        running.sql(SEED)
        yield running


@pytest.fixture()
async def db(cluster):
    async with _pool_on(cluster) as pool:
        yield pool


def _labels(model) -> tuple:
    return tuple(getattr(model, key) for key in LABELS)


async def test_reader_passages_carry_their_labels(db):
    chapter = await get_document_reader(CODE, anchor=None, chapter="book-1", user=_user())
    passages = {p.id: p for p in chapter.passages}
    assert _labels(passages[P_UNOFFICIAL]) == (None, "unofficial_english", LATIN_1108)
    assert _labels(passages[P_PLAIN]) == (None, None, None)
    scanned = await get_document_reader(FATHERS, anchor=None, chapter=None, user=_user())
    assert _labels(scanned.passages[0]) == ("ocr", None, None)


async def test_only_the_three_keys_leave_the_api(db):
    chapter = await get_document_reader(CODE, anchor=None, chapter="book-1", user=_user())
    dumped = next(p for p in chapter.passages if p.id == P_UNOFFICIAL).model_dump()
    assert "amended" not in dumped and "metadata" not in dumped


async def test_restore_carries_the_labels(db):
    results = {r.chunk_id: r for r in (await get_search_results(SEARCH, user=_user())).results}
    assert _labels(results[P_UNOFFICIAL].source) == (None, "unofficial_english", LATIN_1108)
    assert _labels(results[P_SCANNED].source) == ("ocr", None, None)
    assert _labels(results[P_PLAIN].source) == (None, None, None)


async def test_bookmarks_carry_the_labels(db):
    bookmarks = {b.chunk_id: b for b in (await list_bookmarks(user=_user())).bookmarks}
    assert _labels(bookmarks[P_UNOFFICIAL].chunk.source) == (
        None, "unofficial_english", LATIN_1108)
    assert _labels(bookmarks[P_SCANNED].chunk.source) == ("ocr", None, None)
    assert _labels(bookmarks[P_PLAIN].chunk.source) == (None, None, None)


async def test_an_amended_canons_tombstone_links_to_its_latin(db):
    results = {r.chunk_id: r for r in (await get_search_results(SEARCH, user=_user())).results}
    removed = results[P_RETIRED]
    assert removed.status == "removed"
    assert removed.tombstone.read_elsewhere_url == LATIN_295
    with pytest.raises(CorpusLifecycleError) as raised:
        await get_document_reader(CODE, anchor="can/295", chapter=None, user=_user())
    assert raised.value.body["tombstone"]["read_elsewhere_url"] == LATIN_295


async def test_a_suffixed_retired_canon_still_finds_its_latin(db):
    with pytest.raises(CorpusLifecycleError) as raised:
        await get_document_reader(CODE, anchor="can/579#retired-rel-4", chapter=None,
                                  user=_user())
    assert raised.value.body["tombstone"]["read_elsewhere_url"] == LATIN_579
