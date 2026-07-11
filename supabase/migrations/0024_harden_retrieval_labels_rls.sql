-- Migration 0024: ensure labels submitted through the authenticated Data API
-- can only describe a real retrieval from a search owned by that user.

DROP POLICY IF EXISTS "users can manage own labels" ON retrieval_labels;

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
