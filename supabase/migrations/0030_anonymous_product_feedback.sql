-- Allow privacy-bounded anonymous product reports through FastAPI only.
ALTER TABLE product_feedback ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE product_feedback ADD COLUMN rate_limit_key text;

UPDATE product_feedback
SET rate_limit_key = 'user:' || user_id::text
WHERE rate_limit_key IS NULL;

ALTER TABLE product_feedback ALTER COLUMN rate_limit_key SET NOT NULL;
ALTER TABLE product_feedback ADD CONSTRAINT product_feedback_reporter_context_check CHECK (
    user_id IS NOT NULL OR (
        contact_allowed = false
        AND search_id IS NULL
        AND chunk_id IS NULL
        AND document_id IS NULL
    )
);

CREATE INDEX product_feedback_rate_limit_created_idx
    ON product_feedback (rate_limit_key, created_at DESC);
