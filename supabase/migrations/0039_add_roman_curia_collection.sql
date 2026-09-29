-- Allow the roman-curia collection: doctrinal documents of the Dicastery for the Doctrine
-- of the Faith. Additive: every existing value stays allowed. Numbered 0039 to stay clear
-- of the drafted 0035_studies.sql.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_collection_check;

ALTER TABLE documents
  ADD CONSTRAINT documents_collection_check
  CHECK (collection IN (
    'bible', 'catechism', 'church-fathers', 'encyclicals',
    'apostolic-exhortations', 'papal-documents',
    'canon-law', 'summa', 'medieval', 'councils',
    'roman-curia'
  ));
