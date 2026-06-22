from normalize.summa import expand_apparatus, PART_NAMES


def test_expands_question_article_brackets():
    assert expand_apparatus("as we shall explain further on (TP, Q[7], AA[3],4).") \
        == "as we shall explain further on (Third Part, Q. 7, Aa. 3, 4)."
    assert expand_apparatus("as stated above (A[1]).") == "as stated above (A. 1)."


def test_expands_question_ranges():
    assert expand_apparatus("(QQ[1]-114)") == "(Qq. 1–114)"


def test_drops_editorial_bracket_star():
    assert expand_apparatus("the blessed [*Cf. FP, Q[12]], Article") == "the blessed, Article"


def test_fixes_period_after_label():
    assert expand_apparatus("Question. 102 - OF THE CAUSES") == "Question 102 - OF THE CAUSES"


def test_part_names_present():
    assert PART_NAMES["FS"] == "First Part of the Second Part"
