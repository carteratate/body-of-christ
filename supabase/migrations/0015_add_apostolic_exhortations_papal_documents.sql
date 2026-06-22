-- Expand documents.collection allowlist to include apostolic-exhortations and papal-documents.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_collection_check;

ALTER TABLE documents
  ADD CONSTRAINT documents_collection_check
  CHECK (collection IN (
    'bible', 'catechism', 'church-fathers', 'encyclicals',
    'apostolic-exhortations', 'papal-documents',
    'canon-law', 'summa', 'medieval', 'councils'
  ));
