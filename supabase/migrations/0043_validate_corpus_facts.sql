-- Corpus cleanup 2.2a, second half (issue #178): validate 0042's constraints, index the
-- passage history link, and create the staging tables.
--
-- Split from 0042 because a migration is one transaction: there, the ADD COLUMNs' ACCESS
-- EXCLUSIVE locks would have blocked every search for as long as these scans of `chunks`
-- take. Here nothing blocks reads:
--   * VALIDATE CONSTRAINT takes SHARE UPDATE EXCLUSIVE on the table it checks (and ROW
--     SHARE on a foreign key's referenced table), which conflicts with neither reads nor
--     writes;
--   * CREATE INDEX takes SHARE on `chunks`, which blocks writes until commit, not reads.
--     Only the datapipeline writes chunks, and the publish lock (0.4) holds it.
-- Every existing row passes every check: the new columns are NULL, or true for
-- `searchable`. Apply right after 0042. Until then the constraints already hold for new
-- writes; they are only unproven for old rows.

SET LOCAL lock_timeout = '2s';

ALTER TABLE documents VALIDATE CONSTRAINT documents_genre_fk;
ALTER TABLE documents VALIDATE CONSTRAINT documents_certainty_check;
ALTER TABLE documents VALIDATE CONSTRAINT documents_issuer_slug_check;
ALTER TABLE documents VALIDATE CONSTRAINT documents_superseded_by_fk;
ALTER TABLE chunks VALIDATE CONSTRAINT chunks_language_check;
ALTER TABLE chunks VALIDATE CONSTRAINT chunks_voice_check;
ALTER TABLE chunks VALIDATE CONSTRAINT chunks_retired_position_range;
ALTER TABLE chunks VALIDATE CONSTRAINT chunks_work_fk;
ALTER TABLE chunks VALIDATE CONSTRAINT chunks_superseded_by_fk;
ALTER TABLE chunks VALIDATE CONSTRAINT chunks_history_not_searchable;

-- chunks_superseded_by_fk is ON DELETE SET NULL, so every deleted chunk looks up the
-- rows that name it. Without an index each lookup scans all of `chunks`, and today's
-- prune (reader_writer.prune_missing_chunks), which deletes passages one statement at a
-- time, would scan the table once per passage. Partial, because only history passages
-- set it; the lookup's `superseded_by = $1` implies the predicate.
CREATE INDEX chunks_superseded_by_idx ON chunks (superseded_by) WHERE superseded_by IS NOT NULL;

-- Last, so staging copies the finished live shape: validated constraints and the index
-- above. Empty tables and their indexes cost a few kilobytes.
SELECT public.create_corpus_staging();
