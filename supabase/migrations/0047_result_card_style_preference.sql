-- Result card style (Settings, "Result card style"): how search result cards are drawn.
-- 'tint' lays a card on its collection's colour, today's look and the default; 'plain'
-- draws it like a saved passage. Additive, as 0012's theme column was: every existing
-- row reads 'tint'. The API tolerates the column being absent until this is applied.
-- ADD COLUMN with a constant default does not rewrite the table, but it takes an ACCESS
-- EXCLUSIVE lock, and the CHECK is validated by a scan of the existing rows under it (one
-- per account; small). lock_timeout bounds only the wait for the lock: fail after 2 s
-- rather than queue preference reads behind it, as 0041 does.
SET LOCAL lock_timeout = '2s';

ALTER TABLE user_preferences
  ADD COLUMN IF NOT EXISTS result_card_style text NOT NULL DEFAULT 'tint'
  CONSTRAINT user_preferences_result_card_style_check
    CHECK (result_card_style IN ('tint', 'plain'));
