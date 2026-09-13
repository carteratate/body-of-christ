ALTER TABLE user_preferences
    ADD COLUMN last_standard_quota integer;

UPDATE user_preferences
SET last_standard_quota = default_quota;

ALTER TABLE user_preferences
    ALTER COLUMN last_standard_quota SET DEFAULT 4,
    ALTER COLUMN last_standard_quota SET NOT NULL,
    DROP CONSTRAINT IF EXISTS user_preferences_default_quota_check,
    ADD CONSTRAINT user_preferences_default_quota_check
        CHECK (default_quota IN (3, 4, 5, 10)),
    ADD CONSTRAINT user_preferences_last_standard_quota_check
        CHECK (last_standard_quota IN (3, 4, 5)),
    ADD CONSTRAINT user_preferences_focused_quota_collections_check
        CHECK (
            default_quota <> 10
            OR (
                COALESCE(cardinality(default_collections), 0) = 1
                AND default_collections[1] IS NOT NULL
            )
        );
