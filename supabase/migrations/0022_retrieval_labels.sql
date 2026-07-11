-- Migration 0022: Replace chunk_feedback with retrieval_labels.
-- The old table had a nullable search_id and no rank column, making rows useless
-- as training data. This replaces it with a clean dataset table that captures
-- the full (user, query, chunk, label, rank) tuple needed for retrieval training.

DROP TABLE IF EXISTS chunk_feedback;

CREATE TABLE retrieval_labels (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES auth.users(id)  ON DELETE CASCADE,
    chunk_id    uuid        NOT NULL REFERENCES chunks(id)       ON DELETE CASCADE,
    search_id   uuid        NOT NULL REFERENCES searches(id)     ON DELETE CASCADE,
    label       text        NOT NULL CHECK (label IN ('up', 'down')),
    rank        int         NOT NULL CHECK (rank >= 1),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT retrieval_labels_user_chunk_search_unique
        UNIQUE (user_id, chunk_id, search_id)
);

CREATE INDEX retrieval_labels_user_id_idx    ON retrieval_labels (user_id);
CREATE INDEX retrieval_labels_chunk_id_idx   ON retrieval_labels (chunk_id);
CREATE INDEX retrieval_labels_search_id_idx  ON retrieval_labels (search_id);
CREATE INDEX retrieval_labels_created_at_idx ON retrieval_labels (created_at);

ALTER TABLE retrieval_labels ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users can manage own labels"
    ON retrieval_labels FOR ALL
    USING (
        auth.uid() = user_id
        AND EXISTS (
            SELECT 1 FROM searches
            WHERE searches.id = retrieval_labels.search_id
              AND searches.user_id = auth.uid()
        )
        AND EXISTS (
            SELECT 1 FROM retrievals
            WHERE retrievals.search_id = retrieval_labels.search_id
              AND retrievals.chunk_id = retrieval_labels.chunk_id
              AND retrievals.rank = retrieval_labels.rank
        )
    )
    WITH CHECK (
        auth.uid() = user_id
        AND EXISTS (
            SELECT 1 FROM searches
            WHERE searches.id = retrieval_labels.search_id
              AND searches.user_id = auth.uid()
        )
        AND EXISTS (
            SELECT 1 FROM retrievals
            WHERE retrievals.search_id = retrieval_labels.search_id
              AND retrievals.chunk_id = retrieval_labels.chunk_id
              AND retrievals.rank = retrieval_labels.rank
        )
    );
