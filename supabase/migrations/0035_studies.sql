-- Private Studies contain ordered writing and source Passage occurrences.
-- A Passage occurrence keeps a private source snapshot. Corpus pruning may
-- remove its live chunk, but must not erase the Study or authored work.

CREATE TABLE studies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, user_id)
);

CREATE INDEX studies_user_updated_idx ON studies (user_id, updated_at DESC, id);

CREATE TRIGGER studies_updated_at
    BEFORE UPDATE ON studies
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TABLE study_blocks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id uuid NOT NULL,
    user_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    kind text NOT NULL CHECK (kind IN ('writing', 'passage')),
    writing text,
    heading text,
    commentary text,
    -- Keep the stable ID even after collection publication removes its chunk.
    -- Readers can LEFT JOIN chunks to check current source availability.
    source_passage_id uuid,
    source_content text,
    source_reference text,
    source_unit_label text,
    source_document_title text,
    source_collection text,
    source_author text,
    source_translation text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (study_id, user_id) REFERENCES studies(id, user_id) ON DELETE CASCADE,
    CONSTRAINT study_blocks_study_position_key UNIQUE (study_id, position)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT study_blocks_kind_fields_check CHECK (
        (kind = 'writing'
            AND writing IS NOT NULL
            AND heading IS NULL AND commentary IS NULL
            AND source_passage_id IS NULL
            AND source_content IS NULL AND source_reference IS NULL
            AND source_unit_label IS NULL
            AND source_document_title IS NULL AND source_collection IS NULL
            AND source_author IS NULL AND source_translation IS NULL)
        OR
        (kind = 'passage'
            AND writing IS NULL
            AND source_passage_id IS NOT NULL
            AND source_content IS NOT NULL
            AND source_document_title IS NOT NULL
            AND source_collection IS NOT NULL)
    )
);

CREATE INDEX study_blocks_user_study_idx ON study_blocks (user_id, study_id);
CREATE INDEX study_blocks_source_passage_idx ON study_blocks (source_passage_id)
    WHERE source_passage_id IS NOT NULL;

-- Populate the source snapshot from the reader store, never from client fields.
-- Later edits to the same occurrence retain that snapshot, including after a
-- corpus prune. Choosing a different Passage takes a fresh snapshot.
CREATE FUNCTION public.study_block_source_snapshot()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF NEW.kind <> 'passage' THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF OLD.kind = 'passage' AND NEW.source_passage_id = OLD.source_passage_id THEN
            NEW.source_content := OLD.source_content;
            NEW.source_reference := OLD.source_reference;
            NEW.source_unit_label := OLD.source_unit_label;
            NEW.source_document_title := OLD.source_document_title;
            NEW.source_collection := OLD.source_collection;
            NEW.source_author := OLD.source_author;
            NEW.source_translation := OLD.source_translation;
            RETURN NEW;
        END IF;
    END IF;

    SELECT c.content, c.reference, c.unit_label,
           d.title, d.collection, d.author, d.translation
    INTO NEW.source_content, NEW.source_reference, NEW.source_unit_label,
         NEW.source_document_title, NEW.source_collection,
         NEW.source_author, NEW.source_translation
    FROM public.chunks AS c
    JOIN public.documents AS d ON d.id = c.document_id
    WHERE c.id = NEW.source_passage_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Study Passage source does not exist'
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER study_blocks_source_snapshot
    BEFORE INSERT OR UPDATE ON study_blocks
    FOR EACH ROW EXECUTE FUNCTION public.study_block_source_snapshot();

CREATE TRIGGER study_blocks_updated_at
    BEFORE UPDATE ON study_blocks
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

ALTER TABLE studies ENABLE ROW LEVEL SECURITY;
ALTER TABLE study_blocks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owners manage studies" ON studies FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "owners manage study blocks" ON study_blocks FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- FastAPI owns Study operations and validates the JWT. Direct Data API writes
-- would bypass its title, ordering, and source-selection checks.
REVOKE ALL ON TABLE studies, study_blocks FROM PUBLIC, anon, authenticated;
