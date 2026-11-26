-- Corpus cleanup 5.1b.3 (issue #200): the new collection keys.
--
-- Widens documents.collection to the old keys plus the new ones (papal, church-law,
-- theologians), so the 5.1b.3 publish can write the new keys in place while rows still
-- carry the old ones; 5.1b.4 narrows it to the new keys alone. And new users' default
-- collections use the new keys (the API's own default has since 5.1b.2).
--
-- No data changes: the publish rewrites documents.collection and the Qdrant payload,
-- and datapipeline/scripts/rewrite_collection_keys.py the keys stored in user rows.
-- Safe to apply at any time. The staging schema copies the live constraint (0042's
-- LIKE ... INCLUDING ALL), so staging.documents is widened the same way when it
-- exists, which keeps a publish staged before this migration intact.

ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
ALTER TABLE public.documents
  ADD CONSTRAINT documents_collection_check
  CHECK (collection IN (
    'bible', 'catechism', 'church-fathers', 'councils', 'summa',
    'papal', 'church-law', 'theologians',
    'encyclicals', 'apostolic-exhortations', 'papal-documents', 'canon-law', 'medieval'
  ));

DO $$
BEGIN
  IF to_regclass('staging.documents') IS NOT NULL THEN
    ALTER TABLE staging.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
    ALTER TABLE staging.documents
      ADD CONSTRAINT documents_collection_check
      CHECK (collection IN (
        'bible', 'catechism', 'church-fathers', 'councils', 'summa',
        'papal', 'church-law', 'theologians',
        'encyclicals', 'apostolic-exhortations', 'papal-documents', 'canon-law', 'medieval'
      ));
  END IF;
END $$;

DO $$
BEGIN
  -- Guarded only so the datapipeline's corpus-only test database can apply this file;
  -- production has the table.
  IF to_regclass('public.user_preferences') IS NOT NULL THEN
    ALTER TABLE public.user_preferences
      ALTER COLUMN default_collections
      SET DEFAULT ARRAY['bible', 'catechism', 'church-fathers', 'papal', 'church-law', 'summa'];
  END IF;
END $$;
