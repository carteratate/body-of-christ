-- Keyword search without verse markers and with each passage's reference
-- (corpus cleanup 2.2c, issue #181, C-16; decided by Carter on 9 Oct 2026).
--
-- `chunks.search_vector` was to_tsvector('english', content) (0004). Bible passages carry
-- `{{v:N}}` verse markers, which that indexed as the words `v` and `N`, so "John 3:16"
-- matched Maccabees passages holding "John" and the markers 3 and 16. References were in
-- no vector, so "canon 1055" and "CCC 2267" found nothing. The column becomes:
--   * content with the markers replaced by spaces, at weight A, and
--   * the reference with its punctuation (§ : ; , . ( ) – — -) replaced by spaces, at
--     weight B, so "CCC §2266–2267" indexes ccc, 2266 and 2267, and "John 3:1–21" john,
--     3, 1 and 21. The default parser would otherwise keep '§2267' and '1–21' whole.
-- ts_rank weighs A above B, so a passage matched by its text ranks above one matched
-- only by its citation. retrieve_fts.py keeps its query; only matches and order change.
-- Both functions are immutable, as a generated column requires.
--
-- NOT APPLIED ON MERGE. This is the one cleanup migration that is not additive: changing
-- a generated column's expression rewrites `chunks` and rebuilds its indexes under an
-- ACCESS EXCLUSIVE lock, as VACUUM FULL does, so search and the reader pause while it
-- runs. It is applied by hand in 4.0's approved window, from psql over a direct
-- connection, and recorded in the Supabase ledger then (runbook:
-- docs/corpus-cleanup/P4-P5-republish-expand.md, 4.0 step 3). Right after it the window
-- runs `SELECT drop_corpus_staging(); SELECT create_corpus_staging();`, because 0043
-- made the staging tables with the old expression and the staging shape check
-- (datapipeline/writers/reader_writer.py) refuses a stage until they match.
--
-- Postgres 17 changes the expression in place (ALTER COLUMN ... SET EXPRESSION), which
-- keeps the column's position; production is 17.6. Postgres 12 to 16 drop the column and
-- add it again with the new expression, which moves it to the end of the table; nothing
-- reads chunks by column position. Older servers have no generated columns and fail.
-- Either way the GIN index is dropped first and built once, after the rewrite.
--
-- Rollback is 0004's expression applied the same way, then the same staging recreate.
-- No data is lost in either direction: the column is derived from content and reference.

-- Fail fast rather than queue every search behind the lock; retry once a minute (4.0).
-- The rewrite itself must not be cut off by a role's statement timeout.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = 0;

DO $migration$
DECLARE
    expression constant text := $expr$
        setweight(to_tsvector('english',
                  regexp_replace(content, '\{\{v:\d+\}\}', ' ', 'g')), 'A')
        || setweight(to_tsvector('english',
                  regexp_replace(coalesce(reference, ''), '[§:;,.()–—-]', ' ', 'g')), 'B')
    $expr$;
    version constant int := current_setting('server_version_num')::int;
BEGIN
    IF version < 120000 THEN
        RAISE EXCEPTION 'search_vector rebuild needs PostgreSQL 12 or later (generated '
                        'columns); this server is %', current_setting('server_version');
    END IF;

    DROP INDEX public.chunks_search_vector_idx;

    IF version >= 170000 THEN
        EXECUTE format('ALTER TABLE public.chunks ALTER COLUMN search_vector '
                       'SET EXPRESSION AS (%s)', expression);
    ELSE
        EXECUTE format('ALTER TABLE public.chunks DROP COLUMN search_vector, '
                       'ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (%s) STORED',
                       expression);
    END IF;
END
$migration$;

CREATE INDEX chunks_search_vector_idx ON public.chunks USING gin (search_vector);
