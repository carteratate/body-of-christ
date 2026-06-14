from ingest.bible import clamp_pericopes_to_chapters


def test_multi_chapter_pericope_splits_at_chapter_boundary():
    # A pericope spanning 2 Samuel 15–16 yields one passage per chapter.
    verses = [(15, 1, "a"), (15, 2, "b"), (16, 1, "c")]
    out = clamp_pericopes_to_chapters("The Revolt", verses)
    assert len(out) == 2
    assert out[0][0] == 15 and out[1][0] == 16           # (chapter, [verses])
    assert [v for _, vs in out for v in vs] == [(15, 1, "a"), (15, 2, "b"), (16, 1, "c")]


def test_single_chapter_pericope_stays_whole():
    verses = [(3, 14, "x"), (3, 15, "y"), (3, 16, "z")]
    out = clamp_pericopes_to_chapters("Nicodemus", verses)
    assert len(out) == 1 and out[0][0] == 3
