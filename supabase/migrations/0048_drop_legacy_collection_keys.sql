-- Corpus cleanup 5.1b.4 (issue #201): remove the old collection keys.
--
-- Narrows documents.collection to the eight collections. 0046 widened it to the old keys
-- and the new ones so 5.1b.3 could rewrite the stored values in place; that rewrite is
-- done, and the API no longer accepts the old keys.
--
-- non-additive: a documents row with collection encyclicals, apostolic-exhortations,
-- papal-documents, canon-law or medieval is refused. The running API (5.1b.4) never
-- writes or reads one, and the datapipeline has written only the new keys since 5.1b.3.
-- Apply only once the zero-old-keys count in the 5.1b.4 pull request reads 0 everywhere;
-- a leftover row makes the ADD CONSTRAINT fail and nothing changes. Carter asked for
-- this narrowing in 5.1b.4 (issue #201, 23 Nov 2026); applying it needs his OK.
--
-- The staging schema copies the live constraint (0042's LIKE ... INCLUDING ALL), so
-- staging.documents is narrowed the same way when it exists. One DO block, so the file
-- is all or nothing even when run outside a transaction (psql -f).

DO $$
BEGIN
  ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
  ALTER TABLE public.documents
    ADD CONSTRAINT documents_collection_check
    CHECK (collection IN (
      'bible', 'catechism', 'church-fathers', 'councils', 'summa',
      'papal', 'church-law', 'theologians'
    ));

  IF to_regclass('staging.documents') IS NOT NULL THEN
    ALTER TABLE staging.documents DROP CONSTRAINT IF EXISTS documents_collection_check;
    ALTER TABLE staging.documents
      ADD CONSTRAINT documents_collection_check
      CHECK (collection IN (
        'bible', 'catechism', 'church-fathers', 'councils', 'summa',
        'papal', 'church-law', 'theologians'
      ));
  END IF;
END $$;
