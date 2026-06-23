-- Add personal note to bookmarks (one note per saved passage).
-- Nullable: existing rows get NULL. CHECK constraint is defense-in-depth;
-- primary enforcement is in the Pydantic model layer.
alter table bookmarks
  add column note text check (char_length(note) <= 3000);
