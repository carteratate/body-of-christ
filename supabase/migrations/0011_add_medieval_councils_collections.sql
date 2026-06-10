-- Expand documents.collection allowlist to include medieval and councils.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_collection_check;

ALTER TABLE documents
  ADD CONSTRAINT documents_collection_check
  CHECK (collection IN ('bible', 'catechism', 'church-fathers', 'encyclicals', 'canon-law', 'summa', 'medieval', 'councils'));
