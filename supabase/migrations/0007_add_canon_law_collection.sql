-- Expand the documents.collection allowlist to include canon-law.
-- PostgreSQL auto-named the inline constraint 'documents_collection_check'.

alter table documents drop constraint if exists documents_collection_check;

alter table documents
  add constraint documents_collection_check
  check (collection in ('bible', 'catechism', 'church-fathers', 'encyclicals', 'canon-law', 'saints'));

-- Update default for new user_preferences rows (existing rows keep their stored value).
alter table user_preferences
  alter column default_collections
  set default '{bible,catechism,church-fathers,encyclicals,canon-law,saints}';
