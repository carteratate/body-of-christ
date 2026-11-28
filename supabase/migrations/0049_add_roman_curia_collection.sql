-- Corpus cleanup 5.3a (issue #202): the Roman Curia collection.
--
-- Widens documents.collection to the eight collections and `roman-curia`, rebuilt from
-- the constraint as 0048 left it (the parked branch's 0039 predates the new keys; 0039
-- stays unused). Additive: every row allowed today is still allowed, and no data changes.
-- Apply before the stage that writes the Roman Curia documents; until then the API
-- accepts the key and finds nothing under it.
--
-- The staging schema copies the live constraint (0042's LIKE ... INCLUDING ALL), so
-- staging.documents is widened the same way when it exists. One DO block, so the file is
-- all or nothing even when run outside a transaction (psql -f).

DO $$
BEGIN
  ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
  ALTER TABLE public.documents
    ADD CONSTRAINT documents_collection_check
    CHECK (collection IN (
      'bible', 'catechism', 'church-fathers', 'councils', 'summa',
      'papal', 'church-law', 'theologians', 'roman-curia'
    ));

  IF to_regclass('staging.documents') IS NOT NULL THEN
    ALTER TABLE staging.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
    ALTER TABLE staging.documents
      ADD CONSTRAINT documents_collection_check
      CHECK (collection IN (
        'bible', 'catechism', 'church-fathers', 'councils', 'summa',
        'papal', 'church-law', 'theologians', 'roman-curia'
      ));
  END IF;
END $$;
