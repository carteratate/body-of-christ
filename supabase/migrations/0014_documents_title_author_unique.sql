-- Migration 0014: make document title-uniqueness author-aware.
-- Document identity is the deterministic UUIDv5 primary key (passage contract §2).
-- The old UNIQUE(collection, title, translation) wrongly blocked distinct same-title
-- works by different authors (e.g. Polycarp vs Ignatius, both "Epistle to the
-- Philippians"). Replace it with an author-aware constraint.
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_collection_title_translation_key;
ALTER TABLE documents
  ADD CONSTRAINT documents_collection_title_translation_author_key
  UNIQUE (collection, title, translation, author);
