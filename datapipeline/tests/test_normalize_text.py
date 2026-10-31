import json
import re

import pytest

from normalize.text import (BROKEN_WORDS_PATH, clean_text, collapse_whitespace,
                            fold_ligatures, normalize_ellipses, rejoin_broken_words,
                            repair_sentence_joins, tighten_punctuation)


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


# Sentence joins (1.10a): (source text, cleaned text).
JOINS = [
    ("by a special consecration.The Synod was", "by a special consecration. The Synod was"),
    ("as he said.”The Lord", "as he said.” The Lord"),
    ("parentibus.§2. An infant", "parentibus. §2. An infant"),
    ("Earlier version.Cf.Apostolic Letter", "Earlier version. Cf. Apostolic Letter"),
    ("see www.vatican.va for the text", "see www.vatican.va for the text"),
    ("the U.S.Bishops wrote", "the U.S.Bishops wrote"),
    ("St.Augustine says", "St. Augustine says"),
]


@pytest.mark.parametrize("raw, cleaned", JOINS[:4] + JOINS[6:])
def test_repair_sentence_joins_inserts_space(raw, cleaned):
    assert repair_sentence_joins(raw) == cleaned


def test_repair_sentence_joins_ignores_urls_and_initials():
    for raw in ("see www.vatican.va for the text", "the U.S.Bishops wrote",
                "at https://www.vatican.va/content/Index.html", "write to office@vatican.Va"):
        assert repair_sentence_joins(raw) == raw


def test_clean_text_repairs_a_join_tightening_makes():
    # "life .Nor" becomes "life.Nor" when the space before the period goes.
    assert clean_text("the consecrated life .Nor can it") == "the consecrated life. Nor can it"


@pytest.mark.parametrize("raw, cleaned", JOINS)
def test_clean_text_only_adds_whitespace(raw, cleaned):
    out = clean_text(raw)
    assert out == cleaned
    assert re.sub(r"\s", "", out) == re.sub(r"\s", "", raw)


def test_fold_ligatures():
    assert fold_ligatures("Irenæus on the æons; Œcumenius and Cœlestius. ÆTERNI") == \
        "Irenaeus on the aeons; Oecumenius and Coelestius. AeTERNI"
    assert clean_text("the Manichæans of Judæa") == "the Manichaeans of Judaea"


def test_rejoin_broken_words_uses_the_reviewed_list_only():
    assert rejoin_broken_words("it is pre- cisely here") == "it is precisely here"
    assert rejoin_broken_words("where anti- religious laws") == "where anti-religious laws"
    assert rejoin_broken_words("cling so- firmly to Christ") == "cling so firmly to Christ"
    # Whole words only, and nothing that is not on the list: a lost dash stays.
    assert rejoin_broken_words("re- establishment") == "re-establishment"
    assert rejoin_broken_words("pre- ciselyx") == "pre- ciselyx"
    assert rejoin_broken_words("freedom of action- it has escaped") == \
        "freedom of action- it has escaped"
    assert rejoin_broken_words("unpre- cisely") == "unpre- cisely"


def test_broken_words_list_is_well_formed():
    with open(BROKEN_WORDS_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    brokens = [e["broken"] for e in entries]
    assert len(brokens) == len(set(brokens))
    for e in entries:
        assert re.fullmatch(r"[A-Za-z]+- [a-z]+", e["broken"]), e
        assert e["collections"] and e["corrected"] != e["broken"]
        # A correction removes the space, keeps or drops the hyphen, and nothing else.
        assert e["corrected"].replace(" ", "").replace("-", "") == \
            e["broken"].replace(" ", "").replace("-", ""), e
