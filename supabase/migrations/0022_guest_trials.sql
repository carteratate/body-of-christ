-- supabase/migrations/0022_guest_trials.sql
-- IP-hash store for guest trial rate limiting. No RLS — server-side writes only.

CREATE TABLE IF NOT EXISTS guest_trials (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_hash     text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX guest_trials_ip_hash_idx     ON guest_trials (ip_hash);
CREATE INDEX guest_trials_created_at_idx  ON guest_trials (created_at);
