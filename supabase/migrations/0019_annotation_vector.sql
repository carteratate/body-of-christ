-- supabase/migrations/0019_annotation_vector.sql
-- V5 enrichment: full-text index over Opus-generated annotation prose.
-- search_vector (content tsvector) and its GIN index are intentionally untouched.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS annotation_vector tsvector;
CREATE INDEX IF NOT EXISTS chunks_annotation_vector_idx
    ON chunks USING gin(annotation_vector);
