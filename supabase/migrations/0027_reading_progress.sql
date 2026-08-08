-- Cross-device continue-reading state. One latest location per user/document.
CREATE TABLE reading_progress (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chapter_key text NOT NULL CHECK (char_length(chapter_key) BETWEEN 1 AND 500),
    anchor text CHECK (anchor IS NULL OR char_length(anchor) BETWEEN 1 AND 500),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, document_id)
);

CREATE INDEX reading_progress_user_recent_idx
    ON reading_progress (user_id, updated_at DESC);

ALTER TABLE reading_progress ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users can read own reading progress"
    ON reading_progress FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "users can insert own reading progress"
    ON reading_progress FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users can update own reading progress"
    ON reading_progress FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users can delete own reading progress"
    ON reading_progress FOR DELETE
    USING (auth.uid() = user_id);
