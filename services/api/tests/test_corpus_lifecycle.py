"""Corpus cleanup 2.4a against a real database migrated through 0043.

Retired passages and documents come back as tombstones or redirects in history restore,
bookmarks, the reader and reading progress, and are hidden from chapters and /sources.
The rows are shaped the way 2.2w's apply and retire-only commands write them
(datapipeline/writers/apply.py): retired passages below position -1,000,000, a retired
anchor a current passage took carries `#retired-<release>`, passages of a removed
document carry their own tombstones, and tombstone snapshots hold the row as it left.

The acceptance checks are docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.4a.
"""
import contextlib
from unittest.mock import patch

import asyncpg
import httpx
import pytest
from fastapi import HTTPException

from app.corpus_lifecycle import CorpusLifecycleError
from app.db import _init_connection
from app.models.auth import AuthUser
from app.routes import sources
from app.routes.bookmarks import list_bookmarks
from app.routes.documents import (
    get_document, get_document_reader, get_document_toc, require_document_access,
)
from app.routes.reading_progress import get_reading_progress, list_reading_progress
from app.routes.search import get_search_results
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

pytestmark = pytest.mark.real_corpus_schema

USER = "00000000-0000-0000-0000-0000000000aa"
SEARCH = "00000000-0000-0000-0000-0000000000bb"
GUEST_TOKEN = "g" * 40

LIVE = "00000000-0000-0000-0000-00000000d001"      # church-fathers, stays
GONE = "00000000-0000-0000-0000-00000000d002"      # papal, removed awaiting permission
OLD = "00000000-0000-0000-0000-00000000d003"       # superseded: redirects to LIVE
COUNCIL = "00000000-0000-0000-0000-00000000d004"   # councils, one gap passage

P_CURRENT = "00000000-0000-0000-0000-0000000000c1"   # c1/p1, in work w1
P_TAKER = "00000000-0000-0000-0000-0000000000c2"     # c1/p2, took a retired anchor
P_REMOVED = "00000000-0000-0000-0000-0000000000c3"   # retired, c1/p2#retired-rel-1
P_OLD = "00000000-0000-0000-0000-0000000000c4"       # retired, renumbered to P_NEW
P_NEW = "00000000-0000-0000-0000-0000000000c5"       # c2/p1
P_ORPHAN = "00000000-0000-0000-0000-0000000000c6"    # retired, nothing explains it
P_GONE = "00000000-0000-0000-0000-0000000000c7"      # passage of GONE
P_OLD_DOC = "00000000-0000-0000-0000-0000000000c8"   # passage of OLD, moved to P_NEW
P_GAP = "00000000-0000-0000-0000-0000000000c9"       # councils gap passage
P_COUNCIL = "00000000-0000-0000-0000-0000000000ca"   # councils, current

USER_TABLES = """
    CREATE TABLE searches (id uuid PRIMARY KEY, user_id uuid NOT NULL, query text NOT NULL,
                           filters jsonb, result_count int);
    CREATE TABLE retrievals (search_id uuid NOT NULL REFERENCES searches(id),
                             chunk_id uuid NOT NULL REFERENCES chunks(id), rank int NOT NULL,
                             reranker_score float, explanation text);
    CREATE TABLE bookmarks (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id uuid NOT NULL, chunk_id uuid NOT NULL REFERENCES chunks(id),
                            created_at timestamptz NOT NULL DEFAULT now(), note text);
    CREATE TABLE reading_progress (user_id uuid NOT NULL,
                                   document_id uuid NOT NULL REFERENCES documents(id),
                                   chapter_key text NOT NULL, anchor text,
                                   updated_at timestamptz NOT NULL DEFAULT now(),
                                   PRIMARY KEY (user_id, document_id));
    CREATE TABLE guest_trials (id uuid PRIMARY KEY, session_token_hash text NOT NULL,
                               created_at timestamptz NOT NULL DEFAULT now(), claimed_by uuid);
    CREATE TABLE guest_trial_retrievals (guest_trial_id uuid NOT NULL REFERENCES guest_trials(id),
                                         chunk_id uuid NOT NULL REFERENCES chunks(id));
"""

SEED = f"""
    INSERT INTO corpus_publishes (id, collections, qdrant_collection)
    VALUES ('rel-1', ARRAY['church-fathers'], 'chunks-rel-1');

    INSERT INTO documents (id, collection, title, author, year, translation, metadata,
                           genre, date_display, certainty, source_credit, issuer, issuer_label)
    VALUES ('{LIVE}', 'church-fathers', 'Works', 'Gregory Thaumaturgus', 260,
            'Ante-Nicene Fathers', '{{}}', 'treatise', 'c. 260', 'genuine',
            'Sourced via CCEL.org', NULL, NULL),
           ('{GONE}', 'papal-documents', 'Held Letter', 'Pope Pius IX', 1860, '',
            '{{"url": "https://www.papalencyclicals.net/held"}}', 'letter', NULL, NULL,
            NULL, 'pope-pius-ix', 'Pope Pius IX'),
           ('{OLD}', 'church-fathers', 'Old Works', 'Gregory Thaumaturgus', 260, '', '{{}}',
            NULL, NULL, NULL, NULL, NULL, NULL),
           ('{COUNCIL}', 'councils', 'Council of Somewhere', NULL, 1215, '',
            '{{"url": "https://example.org/council", "held_text_url": "https://example.org/held"}}',
            NULL, NULL, NULL, NULL, NULL, NULL);
    INSERT INTO document_works (document_id, work_key, ordinal, title, author, certainty)
    VALUES ('{LIVE}', 'w1', 1, 'Sectional Confession', 'Pseudo-Gregory', 'pseudonymous');

    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, chapter_label,
                        reference, content, work_key, passage_author, note)
    VALUES
      ('{P_CURRENT}', '{LIVE}', 0, 'c1/p1', 'c1', 'Chapter 1', 'Works 1.1', 'first text',
       'w1', NULL, 'A note.'),
      ('{P_TAKER}', '{LIVE}', 1, 'c1/p2', 'c1', 'Chapter 1', 'Works 1.2', 'returning text',
       NULL, NULL, NULL),
      ('{P_NEW}', '{LIVE}', 2, 'c2/p1', 'c2', 'Chapter 2', 'Works 2.1', 'renumbered text',
       NULL, 'Chrysostom, quoted in the Catena Aurea', NULL),
      ('{P_COUNCIL}', '{COUNCIL}', 0, 'can/1', 'can', 'Canons', 'Canon 1', 'canon one',
       NULL, NULL, NULL);
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, chapter_label,
                        reference, content, retired_at)
    VALUES
      ('{P_REMOVED}', '{LIVE}', -1000000, 'c1/p2#retired-rel-1', 'c1', 'Chapter 1',
       'Works 1.2', 'excluded text', now()),
      ('{P_OLD}', '{LIVE}', -1000001, 'c1/p3', 'c1', 'Chapter 1', 'Works 1.3',
       'old numbering', now()),
      ('{P_ORPHAN}', '{LIVE}', -1000002, 'c3/p1', 'c3', 'Chapter 3', 'Works 3.1',
       'orphan text', now()),
      ('{P_GONE}', '{GONE}', -1000000, 'p1', 'p', 'Letter', 'Held Letter 1', 'held text', now()),
      ('{P_OLD_DOC}', '{OLD}', -1000000, 'o1', 'o', 'Old', 'Old Works 1', 'old doc text', now()),
      ('{P_GAP}', '{COUNCIL}', -1000000, 'can/2', 'can', 'Canons', 'Canon 2', 'gap text', now());
    UPDATE documents SET retired_at = now() WHERE id IN ('{GONE}', '{OLD}');

    INSERT INTO corpus_tombstones (entity, id, document_id, retired_at, publish_id,
                                   removal_key, rule, reason_code, public_reason,
                                   church_act, snapshot)
    VALUES
      ('passage', '{P_REMOVED}', '{LIVE}', now(), 'rel-1', 'rm-1', 'A', 'rule-a',
       'This text is not by Gregory.', 'Second Council of Constantinople, anathema 11, 553',
       '{{"collection": "church-fathers", "title": "Works", "author": "Gregory Thaumaturgus",
         "reference": "Works 1.2", "chapter_label": "Chapter 1"}}'),
      ('document', '{GONE}', '{GONE}', now(), 'rel-1', 'rm-2', 'other', 'awaiting-permission',
       'Held until we have permission to publish its English text.', NULL,
       '{{"collection": "papal-documents", "title": "Held Letter", "author": "Pope Pius IX",
         "reference": null, "chapter_label": null}}'),
      ('passage', '{P_GONE}', '{GONE}', now(), 'rel-1', 'rm-2', 'other', 'awaiting-permission',
       'Held until we have permission to publish its English text.', NULL,
       '{{"collection": "papal-documents", "title": "Held Letter", "author": "Pope Pius IX",
         "reference": "Held Letter 1", "chapter_label": "Letter"}}'),
      ('passage', '{P_GAP}', '{COUNCIL}', now(), 'rel-1', 'rm-3', 'other',
       'translation-in-preparation', 'An English translation is in preparation.', NULL,
       '{{"collection": "councils", "title": "Council of Somewhere", "author": null,
         "reference": "Canon 2", "chapter_label": "Canons"}}');

    INSERT INTO corpus_redirects (entity, old_id, old_document_id, old_anchor, new_id,
                                  new_document_id, new_anchor, kind, publish_id)
    VALUES
      ('passage', '{P_OLD}', '{LIVE}', 'c1/p3', '{P_NEW}', '{LIVE}', 'c2/p1', 'renumbered', 'rel-1'),
      ('passage', '{P_OLD_DOC}', '{OLD}', 'o1', '{P_NEW}', '{LIVE}', 'c2/p1', 'moved', 'rel-1'),
      ('document', '{OLD}', '{OLD}', NULL, '{LIVE}', '{LIVE}', NULL, 'moved', 'rel-1'),
      ('anchor', NULL, '{LIVE}', 'old/anchor', NULL, '{LIVE}', 'c2/p1', 'moved', 'rel-1'),
      ('chapter', NULL, '{LIVE}', 'oldch', NULL, '{LIVE}', 'c2', 'moved', 'rel-1');

    INSERT INTO searches (id, user_id, query, filters, result_count)
    VALUES ('{SEARCH}', '{USER}', 'grace', '{{"collections": ["church-fathers"]}}', 4);
    INSERT INTO retrievals (search_id, chunk_id, rank, reranker_score, explanation) VALUES
      ('{SEARCH}', '{P_CURRENT}', 1, 0.9, 'why 1'),
      ('{SEARCH}', '{P_REMOVED}', 2, 0.8, 'why 2'),
      ('{SEARCH}', '{P_OLD}', 3, 0.7, 'why 3'),
      ('{SEARCH}', '{P_ORPHAN}', 4, 0.6, 'why 4');
    INSERT INTO bookmarks (user_id, chunk_id, note, created_at) VALUES
      ('{USER}', '{P_REMOVED}', 'keep me', now() - interval '2 minutes'),
      ('{USER}', '{P_OLD}', 'moved note', now() - interval '1 minute'),
      ('{USER}', '{P_CURRENT}', NULL, now());
    INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor) VALUES
      ('{USER}', '{GONE}', 'p', 'p1'), ('{USER}', '{LIVE}', 'c1', 'c1/p1');
    INSERT INTO guest_trials (id, session_token_hash) VALUES
      ('00000000-0000-0000-0000-0000000000ee', encode(sha256('{GUEST_TOKEN}'), 'hex'));
    INSERT INTO guest_trial_retrievals (guest_trial_id, chunk_id) VALUES
      ('00000000-0000-0000-0000-0000000000ee', '{P_OLD_DOC}');
"""

ROUTE_MODULES = ("search", "bookmarks", "documents", "sources", "reading_progress")


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-lifecycle-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(USER_TABLES)
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
            for name in ROUTE_MODULES:
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


def _user():
    return AuthUser(user_id=USER, email=None)


# --- history restore -------------------------------------------------------------------

async def test_restore_marks_removed_passage_with_tombstone_and_no_content(db):
    results = {r.chunk_id: r for r in (await get_search_results(SEARCH, user=_user())).results}
    removed = results[P_REMOVED]
    assert removed.status == "removed"
    assert removed.content == ""
    assert removed.footnotes == [] and removed.context is None
    assert removed.tombstone.public_reason == "This text is not by Gregory."
    assert removed.tombstone.church_act == "Second Council of Constantinople, anathema 11, 553"
    assert (removed.tombstone.title, removed.tombstone.author, removed.tombstone.reference) == (
        "Works", "Gregory Thaumaturgus", "Works 1.2")
    assert removed.tombstone.read_elsewhere_url is None
    # The saved explanation is returned unchanged; the web decides whether to show it.
    assert removed.explanation == "why 2"


async def test_restore_follows_redirect_to_new_passage(db):
    results = {r.chunk_id: r for r in (await get_search_results(SEARCH, user=_user())).results}
    moved = results[P_OLD]
    assert moved.status == "moved"
    assert moved.content == "renumbered text"
    assert moved.source.anchor == "c2/p1" and moved.source.chapter_key == "c2"
    assert moved.redirect.model_dump() == {
        "kind": "renumbered", "document_id": LIVE, "anchor": "c2/p1", "chunk_id": P_NEW,
        "chapter_key": None}
    assert moved.source.passage_author == "Chrysostom, quoted in the Catena Aurea"


async def test_restore_with_removal_is_complete(db):
    response = await get_search_results(SEARCH, user=_user())
    assert response.restore_status == "complete"
    assert [r.chunk_id for r in response.results] == [P_CURRENT, P_REMOVED, P_OLD, P_ORPHAN]


async def test_restore_treats_an_unexplained_retired_passage_as_current(db, caplog):
    results = {r.chunk_id: r for r in (await get_search_results(SEARCH, user=_user())).results}
    assert results[P_ORPHAN].status == "current"
    assert results[P_ORPHAN].content == "orphan text"
    assert "no tombstone or redirect" in caplog.text


async def test_restore_shows_corrected_text_for_same_id(db, cluster):
    """D1: fixing a passage's text keeps its ID, so a saved search shows the fix."""
    cluster.sql(f"UPDATE chunks SET content = 'first text, corrected' WHERE id = '{P_CURRENT}'")
    try:
        results = {r.chunk_id: r for r in
                   (await get_search_results(SEARCH, user=_user())).results}
        assert results[P_CURRENT].content == "first text, corrected"
        assert results[P_CURRENT].status == "current"
    finally:
        cluster.sql(f"UPDATE chunks SET content = 'first text' WHERE id = '{P_CURRENT}'")


async def test_restore_sends_document_facts_with_the_work_overriding(db):
    current = (await get_search_results(SEARCH, user=_user())).results[0]
    facts = current.source.facts
    assert current.source.author == "Pseudo-Gregory"
    assert facts.certainty == "pseudonymous" and facts.work_title == "Sectional Confession"
    assert facts.genre == "treatise" and facts.date_display == "c. 260"
    assert facts.translation == "Ante-Nicene Fathers"
    assert facts.source_credit == "Sourced via CCEL.org"
    assert current.source.passage_note == "A note."
    assert current.source.language is None


# --- bookmarks -------------------------------------------------------------------------

async def test_bookmarks_mark_removed_and_moved_and_keep_notes(db):
    bookmarks = {b.chunk_id: b for b in (await list_bookmarks(user=_user())).bookmarks}
    removed, moved = bookmarks[P_REMOVED], bookmarks[P_OLD]
    assert removed.status == "removed" and removed.note == "keep me"
    assert removed.chunk.content == ""
    assert removed.tombstone.public_reason == "This text is not by Gregory."
    assert moved.status == "moved" and moved.note == "moved note"
    assert moved.chunk.content == "renumbered text"
    assert moved.redirect.chunk_id == P_NEW
    assert bookmarks[P_CURRENT].status == "current"
    assert bookmarks[P_CURRENT].chunk.source.facts.work_title == "Sectional Confession"


# --- reader ----------------------------------------------------------------------------

async def test_retired_passages_are_not_in_the_chapter(db):
    chapter = await get_document_reader(LIVE, anchor=None, chapter="c1", user=_user())
    assert [p.id for p in chapter.passages] == [P_CURRENT, P_TAKER]
    assert chapter.passages[0].work_key == "w1" and chapter.passages[0].note == "A note."


async def test_outline_and_fallback_agree_when_some_rows_are_retired(db, cluster):
    async def snapshot():
        toc = await get_document_toc(LIVE, user=_user())
        document = await get_document(LIVE, user=_user())
        chapters = {}
        for entry in toc.chapters:
            c = await get_document_reader(LIVE, anchor=None, chapter=entry.chapter_key,
                                          user=_user())
            chapters[entry.chapter_key] = ([p.id for p in c.passages],
                                           c.prev_chapter_key, c.next_chapter_key)
        with patch.object(sources, "_sources_cache", None):
            listed = {s.id: s.chunk_count for s in (await sources.get_sources(user=_user())).sources}
        return ([e.chapter_key for e in toc.chapters], document.chunk_count, chapters,
                listed[LIVE])

    cluster.sql(f"UPDATE documents SET chunk_count = NULL WHERE id = '{LIVE}'")
    fallback = await snapshot()
    cluster.sql(f"SELECT refresh_document_outline('{LIVE}')")
    outlined = await snapshot()
    assert outlined == fallback
    assert fallback[0] == ["c1", "c2"]   # c3 holds only a retired passage
    assert fallback[1] == 3 and fallback[3] == 3


async def test_retired_document_returns_410_with_the_tombstone(db):
    for call in (lambda: get_document(GONE, user=_user()),
                 lambda: get_document_toc(GONE, user=_user()),
                 lambda: get_document_reader(GONE, anchor=None, chapter=None, user=_user())):
        with pytest.raises(CorpusLifecycleError) as raised:
            await call()
        assert raised.value.status_code == 410
        tombstone = raised.value.body["tombstone"]
        assert raised.value.body["detail"] == "removed"
        assert tombstone["entity"] == "document"
        assert tombstone["reason_code"] == "awaiting-permission"
        assert tombstone["read_elsewhere_url"] == "https://www.papalencyclicals.net/held"


async def test_redirected_document_returns_404_with_the_redirect(db):
    with pytest.raises(CorpusLifecycleError) as raised:
        await get_document(OLD, user=_user())
    assert raised.value.status_code == 404
    assert raised.value.body == {"detail": "moved", "redirect": {
        "kind": "moved", "document_id": LIVE, "anchor": None, "chunk_id": None,
        "chapter_key": None}}


async def test_unknown_document_is_still_a_plain_404(db):
    with pytest.raises(HTTPException) as raised:
        await get_document("00000000-0000-0000-0000-00000000dfff", user=_user())
    assert not isinstance(raised.value, CorpusLifecycleError)
    assert (raised.value.status_code, raised.value.detail) == (404, "Document not found")


async def test_an_old_anchor_returns_the_new_chapter_and_redirected_from(db):
    chapter = await get_document_reader(LIVE, anchor="old/anchor", chapter=None, user=_user())
    assert chapter.chapter_key == "c2" and chapter.highlight_anchor == "c2/p1"
    assert chapter.redirected_from.model_dump() == {
        "document_id": LIVE, "anchor": "old/anchor", "chapter_key": None}
    assert chapter.document.id == LIVE


async def test_the_anchor_of_a_moved_passage_opens_where_it_went(db):
    chapter = await get_document_reader(LIVE, anchor="c1/p3", chapter=None, user=_user())
    assert (chapter.chapter_key, chapter.highlight_anchor) == ("c2", "c2/p1")
    assert chapter.redirected_from.anchor == "c1/p3"


async def test_an_old_chapter_key_returns_the_new_chapter(db):
    chapter = await get_document_reader(LIVE, anchor=None, chapter="oldch", user=_user())
    assert chapter.chapter_key == "c2"
    assert chapter.redirected_from.model_dump() == {
        "document_id": LIVE, "anchor": None, "chapter_key": "oldch"}


async def test_a_retired_suffixed_anchor_opens_the_tombstone_notice(db):
    """2.2w keeps a retired passage's anchor as `<anchor>#retired-<release>` when a
    current passage takes it (Carter, 4 Nov 2026)."""
    with pytest.raises(CorpusLifecycleError) as raised:
        await get_document_reader(LIVE, anchor="c1/p2#retired-rel-1", chapter=None, user=_user())
    assert raised.value.status_code == 410
    assert raised.value.body["tombstone"]["entity"] == "passage"
    assert raised.value.body["tombstone"]["reference"] == "Works 1.2"


async def test_the_unsuffixed_anchor_opens_the_current_passage(db):
    chapter = await get_document_reader(LIVE, anchor="c1/p2", chapter=None, user=_user())
    assert chapter.chapter_key == "c1" and chapter.redirected_from is None
    assert chapter.highlight_anchor == "c1/p2"


async def test_a_council_gap_passage_links_to_the_held_text(db):
    with pytest.raises(CorpusLifecycleError) as raised:
        await get_document_reader(COUNCIL, anchor="can/2", chapter=None, user=_user())
    tombstone = raised.value.body["tombstone"]
    assert tombstone["reason_code"] == "translation-in-preparation"
    assert tombstone["read_elsewhere_url"] == "https://example.org/held"


async def test_document_facts_and_works_reach_the_reader(db):
    document = await get_document(LIVE, user=_user())
    assert document.status == "current"
    assert document.facts.genre == "treatise" and document.facts.year == 260
    assert [(w.work_key, w.author, w.certainty) for w in document.works] == [
        ("w1", "Pseudo-Gregory", "pseudonymous")]


async def test_http_bodies_through_the_app(db):
    """The handler in app.main renders the bodies, and a `#` reaches the route intact
    when the client encodes it as %23, as readerHref and getReaderChapter do."""
    from app.main import app

    app.dependency_overrides[require_document_access] = lambda: None
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as client:
            gone = await client.get(f"/v1/documents/{GONE}")
            moved = await client.get(f"/v1/documents/{OLD}/toc")
            suffixed = await client.get(
                f"/v1/documents/{LIVE}/reader?anchor=c1%2Fp2%23retired-rel-1")
            taker = await client.get(f"/v1/documents/{LIVE}/reader?anchor=c1%2Fp2")
    finally:
        app.dependency_overrides.pop(require_document_access, None)
    assert gone.status_code == 410
    assert gone.json()["detail"] == "removed" and gone.json()["tombstone"]["entity"] == "document"
    assert moved.status_code == 404
    assert moved.json() == {"detail": "moved", "redirect": {
        "kind": "moved", "document_id": LIVE, "anchor": None, "chunk_id": None,
        "chapter_key": None}}
    assert suffixed.status_code == 410
    assert suffixed.json()["tombstone"]["public_reason"] == "This text is not by Gregory."
    assert taker.status_code == 200 and taker.json()["chapter_key"] == "c1"


# --- guests ----------------------------------------------------------------------------

class _Request:
    def __init__(self, token):
        self.headers = {"x-theocorpus-guest-token": token}


async def test_guest_reaches_a_document_through_a_redirect(db):
    # The guest retrieved only P_OLD_DOC, in OLD, which now lives in LIVE.
    await require_document_access(OLD, _Request(GUEST_TOKEN), None)
    await require_document_access(LIVE, _Request(GUEST_TOKEN), None)
    with pytest.raises(HTTPException) as raised:
        await require_document_access(COUNCIL, _Request(GUEST_TOKEN), None)
    assert raised.value.status_code == 403


# --- /sources and reading progress -----------------------------------------------------

async def test_sources_hide_retired_documents(db):
    listed = {s.id: s for s in (await sources.get_sources(user=_user())).sources}
    assert set(listed) == {LIVE, COUNCIL}
    assert listed[COUNCIL].chunk_count == 1


async def test_removed_document_leaves_the_reading_progress_list(db):
    listed = await list_reading_progress(limit=6, user=_user())
    assert [i.document_id for i in listed.items] == [LIVE]
    assert listed.items[0].status == "current"


async def test_single_reading_progress_of_a_removed_document_carries_the_tombstone(db):
    item = await get_reading_progress(GONE, user=_user())
    assert item.status == "removed"
    assert item.tombstone.reason_code == "awaiting-permission"
    assert item.chapter_label == "Letter"
    live = await get_reading_progress(LIVE, user=_user())
    assert live.status == "current" and live.tombstone is None


async def test_a_redirect_to_a_passage_later_removed_shows_the_removal(db, cluster):
    """A moved to B, then a later publish removed B: A shows B's tombstone, not its own
    retired text, even while another result's chain takes a second hop."""
    cluster.sql(f"""
        INSERT INTO corpus_redirects (entity, old_id, old_document_id, old_anchor, new_id,
                                      new_document_id, new_anchor, kind, publish_id)
        VALUES ('passage', '{P_ORPHAN}', '{LIVE}', 'c3/p1', '{P_REMOVED}', '{LIVE}',
                'c1/p2#retired-rel-1', 'moved', 'rel-1'),
               ('passage', '{P_REMOVED}', '{LIVE}', 'c1/p2#retired-rel-1', '{P_TAKER}',
                '{LIVE}', 'c1/p2', 'moved', 'rel-1');
        INSERT INTO corpus_publishes (id, collections, qdrant_collection)
        VALUES ('rel-2', ARRAY['church-fathers'], 'chunks-rel-2');
        UPDATE chunks SET retired_at = now(), position = -1000003 WHERE id = '{P_NEW}';
        INSERT INTO corpus_tombstones (entity, id, document_id, retired_at, publish_id,
            removal_key, rule, reason_code, public_reason, church_act, snapshot)
        VALUES ('passage', '{P_NEW}', '{LIVE}', now(), 'rel-2', 'rm-4', 'G',
                'rule-g-editorial', 'Editor-written.', NULL,
                '{{"collection": "church-fathers", "title": "Works", "reference": "Works 2.1"}}');
    """)
    try:
        results = {r.chunk_id: r for r in
                   (await get_search_results(SEARCH, user=_user())).results}
        assert results[P_OLD].status == "removed"
        assert results[P_OLD].content == ""
        assert results[P_OLD].tombstone.public_reason == "Editor-written."
        assert results[P_ORPHAN].status == "moved"
        assert results[P_ORPHAN].redirect.chunk_id == P_TAKER
    finally:
        cluster.sql(f"""
            DELETE FROM corpus_redirects WHERE old_id IN ('{P_ORPHAN}', '{P_REMOVED}');
            DELETE FROM corpus_tombstones WHERE publish_id = 'rel-2';
            UPDATE chunks SET retired_at = NULL, position = 2 WHERE id = '{P_NEW}';
            DELETE FROM corpus_publishes WHERE id = 'rel-2';
        """)
