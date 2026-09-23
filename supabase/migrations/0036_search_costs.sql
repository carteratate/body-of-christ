-- Per-search provider cost, recorded by the API once per search on every exit that
-- spent money (rag/pipeline.py `_record_search_cost`). Until now cost existed only
-- in Railway log lines, which do not outlive a deploy, so "what does a search cost"
-- could not be answered from data.
--
-- Operational telemetry, not user data: no user_id and no query text. search_id
-- links an authenticated search's row back to `searches` and is NULL for guest
-- searches (which live in guest_trials) and for searches that were not persisted.
--
-- Numbered 0036 because a 0035_studies.sql draft exists on at least one working
-- tree (see CLAUDE.md §4); taking 0035 here would collide with it.

CREATE TABLE search_costs (
    id                      uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              timestamptz      NOT NULL DEFAULT now(),
    search_id               uuid             REFERENCES searches(id) ON DELETE SET NULL,
    audience                text             NOT NULL CHECK (audience IN ('authenticated', 'guest')),
    pipeline                text             NOT NULL,
    -- success | degraded_success | no_candidates | the runner's failure outcome |
    -- stage_failed:<stage> (a runner stage raised) | pipeline_failed (unhandled
    -- error) | abandoned (client left before ranking finished)
    outcome                 text             NOT NULL,
    -- False when the stream closed early (client left during ranking or
    -- explanations): costs are then what was spent before it closed, a lower bound.
    -- An abandoned row can be $0 if the client left before the runner did anything.
    completed               boolean          NOT NULL,
    collection_count        integer          NOT NULL CHECK (collection_count > 0),
    quota                   integer          NOT NULL,
    focused                 boolean          NOT NULL,
    delivered               integer          NOT NULL CHECK (delivered >= 0),
    runner_cost             double precision NOT NULL CHECK (runner_cost >= 0),
    explanation_cost        double precision NOT NULL CHECK (explanation_cost >= 0),
    -- Step -> USD, runner steps plus "explain". Same keys as CostTracker.breakdown().
    cost_breakdown          jsonb            NOT NULL,
    -- False when any billed model had no rate: the totals are then a lower bound.
    cost_eligible           boolean          NOT NULL,
    pricing_effective_date  date             NOT NULL,
    -- Model ids and reasoning efforts that produced this cost.
    models                  jsonb            NOT NULL
);

CREATE INDEX search_costs_created_idx ON search_costs (created_at DESC);

-- Written and read only by FastAPI (service role, which bypasses RLS). RLS with no
-- policies plus the revoke keeps it out of the Data API entirely.
ALTER TABLE search_costs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE search_costs FROM PUBLIC, anon, authenticated;
