from normalize.caps import title_case_shouting


def test_title_cases_long_caps_runs():
    assert title_case_shouting("THE FORMATION OF CLERICS") == "The Formation of Clerics"
    assert title_case_shouting("OF THE GIFTS") == "Of the Gifts"


def test_preserves_known_acronyms():
    assert title_case_shouting("CCC IN BRIEF") == "CCC in Brief"


def test_leaves_normal_text_alone():
    assert title_case_shouting("For God so loved the world") == "For God so loved the world"
    assert title_case_shouting("Chapter I") == "Chapter I"
