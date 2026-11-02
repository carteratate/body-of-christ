-- Corpus cleanup 2.2a, schema (issue #178): somewhere to put what the cleanup decides.
--
-- Adds, without changing anything a reader sees:
--   * document facts: genre, issuer, display date, certainty, notes, source credit,
--     supersession (documents.*);
--   * works inside one document (D6): document_works, and chunks.work_key;
--   * passage fields: searchable, language, quoted author, voice, note, and a history
--     link (chunks.superseded_by, rule F);
--   * retirement (D3): documents.retired_at and chunks.retired_at, with tombstones and
--     redirects for what left or moved;
--   * one row per publish (corpus_publishes), and the `staging` schema that the
--     stage-then-apply writer (2.2w, D2) builds into.
-- Nothing reads or writes any of it yet. The specification is
-- docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.2a.
--
-- Additive: every existing row is live (retired_at NULL) and searchable (DEFAULT true),
-- no constraint, index or column is dropped, and the replaced outline function returns
-- the same outline while nothing is retired. The API runs unchanged with or without it.
--
-- Two files, as 0037/0038 are. A migration is one transaction, and the ADD COLUMNs
-- below take ACCESS EXCLUSIVE locks on `documents` and `chunks`, which block every
-- search until commit. So this file does only catalog changes: the new columns are
-- nullable or have a constant default (no rewrite, Postgres 11+), and the CHECK and
-- foreign-key constraints on existing tables are added NOT VALID (no scan). It commits
-- in milliseconds. 0043 then validates them, builds the one new index on `chunks` and
-- creates the staging tables, under locks that do not block reads.
--
-- Numbered 0042, not the 0039 CLAUDE.md reserved for it, so that it runs after 0040
-- (document_contents) and 0041 (documents.reader_access), whose tables staging mirrors
-- (Carter, 2 Nov 2026). 0039 stays unused.

-- While an ALTER TABLE waits for its lock, every new reader of the table queues behind
-- it. Fail after 2 s rather than stall searches; rerun when it clears.
SET LOCAL lock_timeout = '2s';

-- --- new tables (no lock on existing tables beyond the foreign keys' SHARE ROW
-- EXCLUSIVE, which blocks writers, not readers) ---------------------------------------

-- Genre vocabulary (D5). A lookup table, so adding a genre later is an INSERT, not a
-- constraint change. The rows are exactly datapipeline/registry/genres.py ALL_GENRES, in
-- its order (2.1, D11); test_corpus_facts_migration.py fails if the two differ.
CREATE TABLE corpus_genres (
    key text PRIMARY KEY CHECK (key ~ '^[a-z]+(-[a-z]+)*$')
);
INSERT INTO corpus_genres (key) VALUES
    -- Papal
    ('encyclical'), ('apostolic-exhortation'), ('apostolic-letter'),
    ('apostolic-constitution'), ('motu-proprio'), ('bull'), ('letter'),
    -- Roman Curia
    ('declaration'), ('instruction'), ('doctrinal-note'), ('note'), ('response'),
    ('norms'), ('considerations'), ('commentary'),
    -- Catechisms and law
    ('catechism'), ('compendium'), ('code'), ('law'),
    -- Writers ('commentary' is listed once, above)
    ('treatise'), ('manual'), ('sermon'), ('poem'), ('rule'),
    -- Anything else
    ('other');

-- Works inside one document (D6), the database side of 2.1's Work model
-- (datapipeline/model.py Work). ANF volumes hold several works per document ("Dubious or
-- Spurious Writings." holds the Sectional Confession, the Twelve Topics and four
-- homilies), and each carries its own attribution. Which passages belong to a work is
-- chunks.work_key, never a position range.
CREATE TABLE document_works (
    document_id      uuid    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    work_key         text    NOT NULL CHECK (char_length(work_key) BETWEEN 1 AND 200),
    ordinal          integer NOT NULL CHECK (ordinal > 0),
    title            text    NOT NULL,
    author           text,
    certainty        text    CHECK (certainty IN ('genuine', 'disputed', 'pseudonymous', 'anonymous')),
    attribution_note text,
    notes            text,
    date_display     text,
    year             integer,
    genre            text    REFERENCES corpus_genres(key),
    clavis_ref       text,
    PRIMARY KEY (document_id, work_key),
    UNIQUE (document_id, ordinal)
);

-- One row per publish (D2), written by 2.2w. The id is the release name: the lock
-- entry's "release", the --release flag and the suffix of the Qdrant collection
-- chunks-<release> (D11).
CREATE TABLE corpus_publishes (
    id                         text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
    collections                text[] NOT NULL,
    report_sha256              text,
    qdrant_collection          text NOT NULL,
    previous_qdrant_collection text,
    -- The embedding model and dimensions behind the publish's vectors (C-23).
    embed_model                text,
    embed_dimensions           integer CHECK (embed_dimensions > 0),
    -- {"<file in the before-snapshot>": "<sha256>"}; rollback refuses on a mismatch.
    snapshot_sha256            jsonb CHECK (jsonb_typeof(snapshot_sha256) = 'object'),
    staged_at                  timestamptz,
    applied_at                 timestamptz,
    alias_switched_at          timestamptz,
    rolled_back_at             timestamptz,
    -- `stage` refuses while staging holds a publish that has neither of these.
    cleaned_up_at              timestamptz,
    discarded_at               timestamptz
);

-- What left the corpus, and the sentence shown in its place (D3, D4). Tombstones outlive
-- the rows they describe, so they have no foreign keys to chunks or documents.
CREATE TABLE corpus_tombstones (
    entity        text NOT NULL CHECK (entity IN ('document', 'passage')),
    id            uuid NOT NULL,
    document_id   uuid NOT NULL,
    retired_at    timestamptz NOT NULL,
    publish_id    text NOT NULL REFERENCES corpus_publishes(id),
    -- The removal-registry entry's id (D4); NULL only for a rolled-back tombstone.
    removal_key   text,
    -- Derived from reason_code by 2.2w, never stored in the registry.
    rule          text NOT NULL CHECK (rule IN ('A', 'B', 'C', 'G', 'other')),
    -- datapipeline/registry REMOVAL_REASONS plus ROLLED_BACK, in that order (D11);
    -- test_corpus_facts_migration.py fails if the two differ.
    reason_code   text NOT NULL CHECK (reason_code IN (
                      'rule-a', 'rule-b', 'rule-c', 'rule-g-editorial', 'note-split-off',
                      'duplicate', 'debris', 'other-author', 'superseded-translation',
                      'translation-in-preparation', 'not-current-law', 'awaiting-permission',
                      'rolled-back')),
    -- The registry entry's tombstone sentence, shown to users.
    public_reason text NOT NULL,
    -- 'Second Council of Constantinople, anathema 11, 553'
    church_act    text,
    -- {collection, title, author, reference, chapter_label} of the row when it left.
    snapshot      jsonb NOT NULL,
    PRIMARY KEY (entity, id),
    CHECK ((reason_code = 'rolled-back') = (removal_key IS NULL))
);
CREATE INDEX corpus_tombstones_document_idx ON corpus_tombstones (document_id);

-- Old identities to new ones. Kinds are 0.1c's four redirect words (D5, D11); 'same' and
-- 'removed' are release-report outcomes only. An anchor or chapter whose string alone
-- changed uses 'moved'. Staged rows' ids are local to staging; the apply inserts without
-- them, so this table's identity numbers them.
CREATE TABLE corpus_redirects (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity          text NOT NULL CHECK (entity IN ('document', 'passage', 'anchor', 'chapter')),
    old_id          uuid,   -- document or passage ID; NULL for anchor and chapter rows
    old_document_id uuid NOT NULL,
    old_anchor      text,   -- the old anchor, or for chapter rows the old chapter_key
    new_id          uuid,
    new_document_id uuid NOT NULL,
    new_anchor      text,   -- the new anchor, or for chapter rows the new chapter_key
    kind            text NOT NULL CHECK (kind IN ('moved', 'split', 'merged', 'renumbered')),
    publish_id      text NOT NULL REFERENCES corpus_publishes(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((entity IN ('anchor', 'chapter')) = (old_id IS NULL))
);
CREATE UNIQUE INDEX corpus_redirects_id_uniq
    ON corpus_redirects (old_id) WHERE entity IN ('document', 'passage');
CREATE UNIQUE INDEX corpus_redirects_anchor_uniq
    ON corpus_redirects (entity, old_document_id, old_anchor) WHERE entity IN ('anchor', 'chapter');

-- --- staging (D2) ----------------------------------------------------------------------
--
-- The tables 2.2w builds a publish into, with the live corpus tables' names, columns,
-- defaults, CHECK constraints, generated columns and indexes (LIKE ... INCLUDING ALL),
-- but no foreign keys, so nothing in staging can reach a user table. The full-text GIN
-- index comes along because the pre-cutover eval (4.2) searches staging. The tables are
-- made by a function so that 2.2w can drop them after an apply and recreate them, with
-- the live shape of that moment, for the next publish; a later migration that adds a
-- corpus column therefore needs no staging change. 0043 calls it for the first time.
CREATE SCHEMA staging;

CREATE FUNCTION public.create_corpus_staging()
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['documents', 'chunks', 'document_chapters', 'document_contents',
                             'document_works', 'corpus_tombstones', 'corpus_redirects'] LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS staging.%I (LIKE public.%I INCLUDING ALL)', t, t);
        -- LIKE copies neither row security nor privileges.
        EXECUTE format('ALTER TABLE staging.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON TABLE staging.%I FROM PUBLIC, anon, authenticated', t);
    END LOOP;
END;
$$;

CREATE FUNCTION public.drop_corpus_staging()
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    DROP TABLE IF EXISTS staging.corpus_redirects, staging.corpus_tombstones,
        staging.document_works, staging.document_contents, staging.document_chapters,
        staging.chunks, staging.documents;
END;
$$;

-- --- documents and chunks (ACCESS EXCLUSIVE until commit; catalog changes only) -------
--
-- Last, so the locks that block readers are held for the shortest time.

ALTER TABLE documents
    ADD COLUMN retired_at       timestamptz,
    ADD COLUMN genre            text,
    ADD COLUMN issuer           text,   -- slug for filters: 'pope-leo-xiii', 'ddf', 'holy-see'
    ADD COLUMN issuer_label     text,   -- display: 'Pope Leo XIII'
    ADD COLUMN date_display     text,   -- 'c. 375-380', '1077-78', '1265-1274'
    ADD COLUMN certainty        text,   -- the attribution label
    ADD COLUMN attribution_note text,   -- 'Heimgartner (2001) assigns it to Athenagoras.'
    ADD COLUMN notes            text,   -- reader note, e.g. the Apostolic Canons note
    ADD COLUMN source_credit    text,   -- 'Text: Libreria Editrice Vaticana'
    ADD COLUMN clavis_ref       text,   -- 'CPG 1083'
    ADD COLUMN superseded_by    uuid,   -- rule F: an older text names the current one (D5)
    ADD COLUMN superseded_note  text,   -- 'Superseded by the 2023 text of canon 295.'
    ADD CONSTRAINT documents_genre_fk
        FOREIGN KEY (genre) REFERENCES corpus_genres(key) NOT VALID,
    ADD CONSTRAINT documents_certainty_check
        CHECK (certainty IN ('genuine', 'disputed', 'pseudonymous', 'anonymous')) NOT VALID,
    ADD CONSTRAINT documents_issuer_slug_check
        CHECK (issuer IS NULL OR issuer ~ '^[a-z0-9]+(-[a-z0-9]+)*$') NOT VALID,
    ADD CONSTRAINT documents_superseded_by_fk
        FOREIGN KEY (superseded_by) REFERENCES documents(id) ON DELETE SET NULL NOT VALID;

-- searchable, language, passage_author, voice, note and work_key are 2.1's Passage
-- fields (D11): adapters may set them and the passage registry overrides.
ALTER TABLE chunks
    ADD COLUMN retired_at     timestamptz,
    ADD COLUMN searchable     boolean NOT NULL DEFAULT true,
    ADD COLUMN language       text,   -- ISO 639 code; NULL means English
    ADD COLUMN work_key       text,
    ADD COLUMN passage_author text,   -- 'Chrysostom, quoted in Aquinas''s Catena Aurea'
    ADD COLUMN voice          text,   -- NULL, or 'rejected' (C-01, D5)
    ADD COLUMN note           text,
    -- A history passage (<anchor>/history-<year>) names the current passage that
    -- replaced it (rule F, D11).
    ADD COLUMN superseded_by  uuid,
    ADD CONSTRAINT chunks_language_check
        CHECK (language IS NULL OR language ~ '^[a-z]{2,3}$') NOT VALID,
    ADD CONSTRAINT chunks_voice_check
        CHECK (voice IS NULL OR voice = 'rejected') NOT VALID,
    -- Retired rows sit below every live and temporary position (2.2w), so they never
    -- collide on UNIQUE (document_id, position) with the rows that replace them.
    ADD CONSTRAINT chunks_retired_position_range
        CHECK (retired_at IS NULL OR position <= -1000000) NOT VALID,
    ADD CONSTRAINT chunks_work_fk FOREIGN KEY (document_id, work_key)
        REFERENCES document_works (document_id, work_key) NOT VALID,
    ADD CONSTRAINT chunks_superseded_by_fk FOREIGN KEY (superseded_by)
        REFERENCES chunks (id) ON DELETE SET NULL NOT VALID,
    -- A history passage is never searchable.
    ADD CONSTRAINT chunks_history_not_searchable
        CHECK (superseded_by IS NULL OR NOT searchable) NOT VALID;

-- --- the reader outline counts only what readers see -----------------------------------
--
-- 0037's function and trigger, with retired rows left out. While nothing is retired the
-- outline is the same as before.

CREATE OR REPLACE FUNCTION public.refresh_document_outline(p_document_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    -- Lock order as in 0037: the document row first, then its chapters.
    PERFORM 1 FROM documents WHERE id = p_document_id FOR NO KEY UPDATE;

    DELETE FROM document_chapters WHERE document_id = p_document_id;

    INSERT INTO document_chapters (document_id, ordinal, chapter_key, chapter_label)
    SELECT p_document_id,
           row_number() OVER (ORDER BY min(c.position))::integer,
           c.chapter_key,
           (array_agg(c.chapter_label ORDER BY c.position))[1]
    FROM chunks AS c
    WHERE c.document_id = p_document_id
      AND c.chapter_key IS NOT NULL
      AND c.retired_at IS NULL
    GROUP BY c.chapter_key;

    UPDATE documents
    SET chunk_count = (SELECT count(*) FROM chunks AS c
                       WHERE c.document_id = p_document_id AND c.retired_at IS NULL)
    WHERE id = p_document_id;
END;
$$;

-- Retiring or un-retiring a passage changes the outline, so it invalidates it.
CREATE OR REPLACE TRIGGER chunks_invalidate_outline_on_restructure
    AFTER UPDATE OF document_id, position, chapter_key, chapter_label, retired_at ON chunks
    FOR EACH ROW
    WHEN ((OLD.document_id, OLD.position, OLD.chapter_key, OLD.chapter_label, OLD.retired_at)
          IS DISTINCT FROM
          (NEW.document_id, NEW.position, NEW.chapter_key, NEW.chapter_label, NEW.retired_at))
    EXECUTE FUNCTION public.invalidate_document_outline();

-- The same outline for staged documents, resolved against staging's tables (2.2w calls
-- it for every staged document, so the pre-cutover eval has document_chapters and
-- chunk_count). Keep its body in step with the public function above.
CREATE FUNCTION staging.refresh_document_outline(p_document_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = staging
AS $$
BEGIN
    PERFORM 1 FROM documents WHERE id = p_document_id FOR NO KEY UPDATE;

    DELETE FROM document_chapters WHERE document_id = p_document_id;

    INSERT INTO document_chapters (document_id, ordinal, chapter_key, chapter_label)
    SELECT p_document_id,
           row_number() OVER (ORDER BY min(c.position))::integer,
           c.chapter_key,
           (array_agg(c.chapter_label ORDER BY c.position))[1]
    FROM chunks AS c
    WHERE c.document_id = p_document_id
      AND c.chapter_key IS NOT NULL
      AND c.retired_at IS NULL
    GROUP BY c.chapter_key;

    UPDATE documents
    SET chunk_count = (SELECT count(*) FROM chunks AS c
                       WHERE c.document_id = p_document_id AND c.retired_at IS NULL)
    WHERE id = p_document_id;
END;
$$;

-- --- access -----------------------------------------------------------------------------
--
-- FastAPI and the datapipeline connect as the database owner, which bypasses RLS. RLS
-- with no policies plus the revokes keeps everything out of the Data API, as 0037 does.
ALTER TABLE corpus_genres     ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_works    ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_publishes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_tombstones ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_redirects  ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE corpus_genres, document_works, corpus_publishes, corpus_tombstones,
    corpus_redirects FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SCHEMA staging FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_corpus_staging(), public.drop_corpus_staging(),
    staging.refresh_document_outline(uuid), public.refresh_document_outline(uuid)
    FROM PUBLIC, anon, authenticated;
