-- A papal document's form, beside its genre (Carter, 9 Nov 2026; corpus cleanup 1.3b,
-- issue #156).
--
-- A document's genre (0042) is its kind, what it is: encyclical, apostolic constitution.
-- Its form is how the papal chancery issued it, a bull or a brief. Many older documents
-- are both, as Ineffabilis Deus is an apostolic constitution issued as a bull and Probe
-- Nostis an encyclical issued as a brief, so the two are separate columns. `bull` was a
-- genre in 0042's seed; it moves here, and leaves `corpus_genres`.
--
-- Adds `corpus_forms` (seeded from datapipeline/registry/genres.py PAPAL_FORMS, which
-- test_corpus_facts_migration.py checks) and a nullable `documents.form` referencing it.
-- Nothing writes the column yet: 1.3b records each papal document's form in the
-- datapipeline, and the registry, writer and filter that carry it to this column are a
-- follow-up. NULL means no chancery form is recorded, as for nearly every modern document.
--
-- The ADD COLUMN takes ACCESS EXCLUSIVE on `documents` until commit, which blocks reads.
-- The column is nullable (no rewrite), and the foreign key's check scans `documents`,
-- which holds a few hundred rows, all NULL in the new column: milliseconds. `chunks` is
-- not touched, so no 0043-style second file is needed.
--
-- The DELETE fails, and the whole migration rolls back, if any document still holds the
-- genre `bull`: documents_genre_fk refuses it. None should, since no publish has written
-- `bull`; if one has, re-genre that document first.

SET LOCAL lock_timeout = '2s';

CREATE TABLE corpus_forms (
    key text PRIMARY KEY CHECK (key ~ '^[a-z]+(-[a-z]+)*$')
);
INSERT INTO corpus_forms (key) VALUES ('bull'), ('brief');

ALTER TABLE documents
    ADD COLUMN form text,
    ADD CONSTRAINT documents_form_fk FOREIGN KEY (form) REFERENCES corpus_forms(key);

-- create_corpus_staging() copies the live shape, so staging tables made after this have
-- the column. A staging schema made before it gains it here, so a publish staged across
-- this migration keeps the live shape.
ALTER TABLE IF EXISTS staging.documents ADD COLUMN IF NOT EXISTS form text;

DELETE FROM corpus_genres WHERE key = 'bull';

ALTER TABLE corpus_forms ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE corpus_forms FROM PUBLIC, anon, authenticated;
