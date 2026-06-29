-- Migration 0018: compare_runs table for RAG pipeline evaluation framework
-- Stores timing and cost data for each pipeline run in a compare invocation.
-- No RLS needed — server-side writes only, no user-owned data.

CREATE TABLE IF NOT EXISTS compare_runs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       timestamptz NOT NULL DEFAULT now(),
    query            text NOT NULL,
    collections      text[] NOT NULL,
    quota            int NOT NULL,
    pipeline         text NOT NULL,
    total_duration_s float NOT NULL,
    total_cost       float NOT NULL,
    chunk_count      int NOT NULL,
    step_timings     jsonb NOT NULL DEFAULT '[]',
    cost_breakdown   jsonb NOT NULL DEFAULT '{}'
);

CREATE INDEX compare_runs_pipeline_idx    ON compare_runs (pipeline);
CREATE INDEX compare_runs_created_at_idx  ON compare_runs (created_at);
