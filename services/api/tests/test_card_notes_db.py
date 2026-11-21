"""Corpus cleanup 4.4 against a real database migrated through 0043.

The notes under an opened passage reach saved searches and bookmarks as the optional
`card`, built from the keys a 4.4 publish writes into `documents.metadata` and
`chunks.metadata`; a document without `metadata.card_version` keeps today's payload. The
overview and the Library row read the document-wide notes.
"""
import pytest

from app import reader_access
from app.routes import sources as sources_route
from app.routes.bookmarks import list_bookmarks
from app.routes.documents import get_document
from app.routes.search import get_search_results
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)
from tests.test_corpus_lifecycle import USER, USER_TABLES, _pool_on, _user

pytestmark = pytest.mark.real_corpus_schema

SEARCH = "00000000-0000-0000-0000-0000000000cb"
COUNCIL = "00000000-0000-0000-0000-00000000c001"  # migrated, two translators
FATHERS = "00000000-0000-0000-0000-00000000c002"  # migrated, a work and a record note
OLD = "00000000-0000-0000-0000-00000000c003"      # not migrated

P_EXTRACT = "00000000-0000-0000-0000-0000000000c1"
P_CANON = "00000000-0000-0000-0000-0000000000c2"
P_WORK = "00000000-0000-0000-0000-0000000000c3"
P_OLD = "00000000-0000-0000-0000-0000000000c4"

COUNCIL_NOTES = ('[{"kind": "incomplete", "text": "Its sentence is not available on '
                 'TheoCorpus at present.", "show": "overview"}]')
FATHERS_NOTES = """[
  {"kind": "authorship", "text": "A later addition by another hand.", "show": "card",
   "work_key": "w1"},
  {"text": "Preserved in Eusebius, Church History.", "show": "record"}]"""

SEED = f"""
    INSERT INTO documents (id, collection, title, author, year, translation, metadata,
                           source_credit)
    VALUES ('{COUNCIL}', 'councils', 'Council of Florence', NULL, 1439, '',
            '{{"url": "https://www.vatican.va/florence.html", "card_version": 1,
               "card_translator": "Translated by H. J. Schroeder (1937)",
               "card_notes": {COUNCIL_NOTES}}}', 'Translated by H. J. Schroeder (1937)'),
           ('{FATHERS}', 'church-fathers', 'Fragments', 'Dionysius', NULL,
            'Ante-Nicene Fathers (1885-1896)',
            '{{"card_version": 1, "card_translator": "Ante-Nicene Fathers (1885–1896)",
               "card_notes": {FATHERS_NOTES}}}', 'Sourced via CCEL.org'),
           ('{OLD}', 'church-fathers', 'Old', 'Justin Martyr', 155,
            'Ante-Nicene Fathers (1885-1896)', '{{}}', 'Sourced via CCEL.org');
    INSERT INTO document_works (document_id, work_key, ordinal, title)
    VALUES ('{FATHERS}', 'w1', 1, 'A Fragment');

    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, chapter_label,
                        reference, content, note, work_key, metadata)
    VALUES
      ('{P_EXTRACT}', '{COUNCIL}', 0, 's11/1', 's11', 'Session 11', 'Session 11',
       'an extract', 'An extract; the full decree is not available on TheoCorpus at present.',
       NULL, '{{"note_kind": "incomplete", "translator":
               "Translated by Roy J. Deferrari (1957), in The Sources of Catholic Dogma",
               "text_source": "ocr"}}'),
      ('{P_CANON}', '{COUNCIL}', 1, 's11/2', 's11', 'Session 11', 'Session 11',
       'a canon', NULL, NULL, NULL),
      ('{P_WORK}', '{FATHERS}', 0, 'f/1', 'f', 'Fragment', 'Fragment 1', 'a fragment',
       NULL, 'w1', NULL),
      ('{P_OLD}', '{OLD}', 0, 'o/1', 'o', 'One', 'One 1', 'old text', 'A note.', NULL, NULL);

    INSERT INTO searches (id, user_id, query, filters, result_count)
    VALUES ('{SEARCH}', '{USER}', 'decree', '{{"collections": ["councils"]}}', 4);
    INSERT INTO retrievals (search_id, chunk_id, rank, reranker_score, explanation) VALUES
      ('{SEARCH}', '{P_EXTRACT}', 1, 0.9, NULL), ('{SEARCH}', '{P_CANON}', 2, 0.8, NULL),
      ('{SEARCH}', '{P_WORK}', 3, 0.7, NULL), ('{SEARCH}', '{P_OLD}', 4, 0.6, NULL);
    INSERT INTO bookmarks (user_id, chunk_id) VALUES ('{USER}', '{P_EXTRACT}'),
      ('{USER}', '{P_OLD}');
"""


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-card-notes-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(USER_TABLES)
        running.sql(SEED)
        yield running


@pytest.fixture()
async def db(cluster):
    async with _pool_on(cluster) as pool:
        yield pool


async def _restored():
    return {r.chunk_id: r.source for r in
            (await get_search_results(SEARCH, user=_user())).results}


async def test_restore_builds_each_passages_card(db):
    sources = await _restored()
    extract = sources[P_EXTRACT].card
    assert [(c.kind, c.text) for c in extract.cautions] == [
        ("incomplete", "An extract; the full decree is not available on TheoCorpus at present.")]
    assert extract.record == [
        "Translated by Roy J. Deferrari (1957), in The Sources of Catholic Dogma", "scanned"]
    assert extract.notice == reader_access.VATICAN_CREDIT
    canon = sources[P_CANON].card
    assert canon.cautions == [] and canon.record == ["Translated by H. J. Schroeder (1937)"]
    work = sources[P_WORK].card
    assert [c.text for c in work.cautions] == ["A later addition by another hand."]
    assert work.record == ["Preserved in Eusebius, Church History.",
                           "Ante-Nicene Fathers (1885–1896)"]
    assert work.notice is None


async def test_a_document_from_before_4_4_keeps_todays_fields_and_no_card(db):
    old = (await _restored())[P_OLD]
    assert old.card is None
    assert old.passage_note == "A note."
    assert old.facts.source_credit == "Sourced via CCEL.org"


async def test_bookmarks_carry_the_card(db):
    bookmarks = {b.chunk_id: b.chunk.source for b in (await list_bookmarks(user=_user())).bookmarks}
    assert bookmarks[P_EXTRACT].card.record[-1] == "scanned"
    assert bookmarks[P_OLD].card is None


async def test_the_overview_and_the_library_read_the_document_wide_notes(db):
    council = await get_document(COUNCIL, user=_user())
    assert [(n.kind, n.text) for n in council.overview_notes] == [
        ("incomplete", "Its sentence is not available on TheoCorpus at present.")]
    fathers = await get_document(FATHERS, user=_user())
    assert [(n.kind, n.text) for n in fathers.overview_notes] == [
        (None, "Preserved in Eusebius, Church History.")]
    assert (await get_document(OLD, user=_user())).overview_notes is None

    sources_route._sources_cache = None
    library = {s.id: s for s in (await sources_route.get_sources(user=_user())).sources}
    assert library[COUNCIL].overview_notes == council.overview_notes
    assert library[OLD].overview_notes is None
    sources_route._sources_cache = None
