-- Allow reports for searches rejected before execution, such as invalid request shapes.
ALTER TABLE product_feedback
    DROP CONSTRAINT IF EXISTS product_feedback_error_code_check;

ALTER TABLE product_feedback
    ADD CONSTRAINT product_feedback_error_code_check CHECK (
        error_code IS NULL OR error_code IN (
            'auth_error', 'invalid_request', 'network_error', 'rate_limit',
            'restore_not_found', 'restore_unavailable', 'server_error',
            'stream_interrupted', 'unknown'
        )
    );
