-- User-submitted product feedback and bug reports. This is intentionally
-- separate from retrieval_labels, which remains relevance-training data.

CREATE TABLE product_feedback (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    category         text        NOT NULL CHECK (category IN ('bug', 'content', 'feature', 'general')),
    message          text        NOT NULL CHECK (char_length(message) BETWEEN 10 AND 5000),
    contact_allowed  boolean     NOT NULL DEFAULT false,
    route            text        CHECK (
        route IS NULL OR (
            char_length(route) BETWEEN 1 AND 200
            AND route ~ '^/[A-Za-z0-9/_-]*$'
        )
    ),
    viewport_width   integer     CHECK (viewport_width IS NULL OR viewport_width BETWEEN 200 AND 10000),
    viewport_height  integer     CHECK (viewport_height IS NULL OR viewport_height BETWEEN 200 AND 10000),
    browser_family   text        CHECK (browser_family IS NULL OR browser_family IN ('chrome', 'safari', 'firefox', 'edge', 'other')),
    search_id        uuid        REFERENCES searches(id) ON DELETE SET NULL,
    chunk_id         uuid        REFERENCES chunks(id) ON DELETE SET NULL,
    document_id      uuid        REFERENCES documents(id) ON DELETE SET NULL,
    error_code       text        CHECK (error_code IS NULL OR error_code IN (
        'auth_error', 'network_error', 'rate_limit', 'restore_unavailable',
        'server_error', 'stream_interrupted', 'unknown'
    )),
    status           text        NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewing', 'resolved', 'closed')),
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX product_feedback_user_created_idx
    ON product_feedback (user_id, created_at DESC);
CREATE INDEX product_feedback_status_created_idx
    ON product_feedback (status, created_at DESC);

ALTER TABLE product_feedback ENABLE ROW LEVEL SECURITY;

-- Reports must pass through FastAPI so its shared rate limit and context
-- relationship checks cannot be bypassed through Supabase's Data API.
REVOKE ALL ON TABLE product_feedback FROM PUBLIC, anon, authenticated;

CREATE POLICY "users can read own product feedback"
    ON product_feedback FOR SELECT
    USING (auth.uid() = user_id);
