from normalize.text import collapse_whitespace, tighten_punctuation, normalize_ellipses, clean_text


def test_collapse_whitespace_keeps_paragraphs():
    assert collapse_whitespace("a   b\t c") == "a b c"
    assert collapse_whitespace("para one\n\npara two") == "para one\n\npara two"


def test_tighten_punctuation():
    assert tighten_punctuation("word .") == "word."
    assert tighten_punctuation("a ; b") == "a; b"


def test_normalize_ellipsis_three_dots():
    assert normalize_ellipses("no other gods before me . . .") == "no other gods before me …"
    assert normalize_ellipses("bone of my bones. . .") == "bone of my bones …"


def test_normalize_ellipsis_collapses_long_table_runs():
    # Summa "diagram" leader-dot artifact: a long run collapses to a single space.
    out = normalize_ellipses("UNDER THE LAW . . . . . . . . all descendants")
    assert "…" not in out and ". ." not in out
    assert "UNDER THE LAW all descendants" == " ".join(out.split())


def test_clean_text_pipeline():
    assert clean_text("word  .  Next . . .") == "word. Next …"
