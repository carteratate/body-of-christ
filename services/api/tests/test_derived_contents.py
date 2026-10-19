"""The stopgap Summa contents tree derived from today's chapter list (#251)."""

import asyncio
from unittest.mock import patch

from app.derived_contents import derive_summa_contents
from app.models.auth import AuthUser
from app.routes.documents import get_document_toc
from tests.fake_pool import FakePool

FP = "summa/first-part"
FS = "summa/first-part-of-the-second-part-first-part-of-the-second-part-qq-1-114"
SS = "summa/second-part-of-the-second-part-second-part-of-the-second-part-qq-1-189"
APP = "summa/appendix"

# Shapes taken from the live chapter list, including its three irregular labels.
CHAPTERS = [
    (f"{FP}/question-1-the-nature-ten-articles/article-1-whether-besides",
     "Question 1 - The Nature and Extent of Sacred Doctrine (Ten Articles) — "
     "Article 1 - Whether, besides philosophy, any further doctrine is required?"),
    (f"{FP}/question-1-the-nature-ten-articles/article-2-whether-science",
     "Question 1 - The Nature and Extent of Sacred Doctrine (Ten Articles) — "
     "Article 2 - Whether sacred doctrine is a science?"),
    (f"{FP}/question-114-of-the-assaults-five-articles/article-4-whether-miracles",
     "Question 114 - Of the Assaults of the Demons (FIVE ARTICLES) — "
     "Article 4 - Whether demons can lead men astray by means of real miracles?"),
    (f"{FP}/question-114-of-the-assaults-five-articles/article-4-whether-overcome",
     "Question 114 - Of the Assaults of the Demons (FIVE ARTICLES) — "
     "Article 4 - Whether a demon who is overcome by man, is hindered?"),
    (f"{FS}/question-1-of-mans-last-end-eight-articles/article-1-whether-end",
     "Question 1 - Of Man's Last End (EIGHT ARTICLES) — "
     "Article 1 - Whether it belongs to man to act for an end?"),
    (f"{SS}/question-103-of-dulia-four-articles/whether-dulia-is-a-special-virtue",
     "Question 103 - OF DULIA (FOUR ARTICLES) — Whether dulia is a special virtue distinct "
     "from latria?"),
    (f"{APP}/two-articles-on-purgatory/article-2-whether-same-place",
     "Two Articles on Purgatory — Article 2 - Whether it is the same place where souls are "
     "cleansed, and the damned  punished?"),
]


def _shape(nodes):
    return [(n.key, n.kind, n.short_label, n.range_label, _shape(n.children)) for n in nodes]


def test_parts_questions_and_articles_from_the_live_label_shapes():
    tree = derive_summa_contents(CHAPTERS)

    assert _shape(tree) == [
        ("I", "part", "I · First Part", "Qq. 1–114", [
            ("I/q1", "question", "Q. 1 · The Nature and Extent of Sacred Doctrine", "2 articles", [
                ("I/q1/a1", "article",
                 "Art. 1 · Whether, besides philosophy, any further doctrine is required?",
                 None, []),
                ("I/q1/a2", "article", "Art. 2 · Whether sacred doctrine is a science?", None, []),
            ]),
            ("I/q114", "question", "Q. 114 · Of the Assaults of the Demons", "2 articles", [
                ("I/q114/a4", "article",
                 "Art. 4 · Whether demons can lead men astray by means of real miracles?",
                 None, []),
                # The source numbers I q.114's fifth article "4" too; the key stays unique.
                ("I/q114/article-4-whether-overcome", "article",
                 "Art. 4 · Whether a demon who is overcome by man, is hindered?", None, []),
            ]),
        ]),
        ("I-II", "part", "I-II · First Part of the Second Part", "Q. 1", [
            ("I-II/q1", "question", "Q. 1 · Of Man's Last End", "1 article", [
                ("I-II/q1/a1", "article", "Art. 1 · Whether it belongs to man to act for an end?",
                 None, []),
            ]),
        ]),
        ("II-II", "part", "II-II · Second Part of the Second Part", "Q. 103", [
            ("II-II/q103", "question", "Q. 103 · Of Dulia", "1 article", [
                ("II-II/q103/whether-dulia-is-a-special-virtue", "article",
                 "Whether dulia is a special virtue distinct from latria?", None, []),
            ]),
        ]),
        ("App.", "part", "App. · Appendix", None, [
            ("App./two-articles-on-purgatory", "question", "Two Articles on Purgatory",
             "1 article", [
                 ("App./two-articles-on-purgatory/a2", "article",
                  "Art. 2 · Whether it is the same place where souls are cleansed, and the "
                  "damned punished?", None, []),
             ]),
        ]),
    ]


def test_every_node_opens_its_first_chapter():
    [first_part, *_] = derive_summa_contents(CHAPTERS)
    assert first_part.chapter_key == CHAPTERS[0][0]
    assert first_part.children[1].chapter_key == CHAPTERS[2][0]


def test_unreadable_chapters_give_no_tree():
    assert derive_summa_contents([("summa/first-part/q1", "Question 1 — Article 1")]) is None
    assert derive_summa_contents([("summa/unknown-part/q/a", "Question 1 - X — Article 1 - Y")]) is None
    assert derive_summa_contents([(f"{FP}/q/a", "no separator")]) is None
    assert derive_summa_contents([]) is None


def test_a_part_or_question_that_returns_later_gives_no_tree():
    back = CHAPTERS[:1] + CHAPTERS[4:5] + CHAPTERS[1:2]
    assert derive_summa_contents(back) is None


def _toc(collection, contents_rows):
    pool = FakePool()
    pool.conn.fetchrow.return_value = {
        "id": "11111111-1111-1111-1111-111111111111", "collection": collection,
        "title": "Summa Theologiae", "author": None, "year": None, "translation": "",
        "metadata": None, "cnt": 7, "reader_access": "full", "outline_ready": True}
    pool.conn.fetch.side_effect = [
        [{"chapter_key": k, "chapter_label": label} for k, label in CHAPTERS], contents_rows]
    with patch("app.routes.documents.get_pool", return_value=pool):
        return asyncio.run(get_document_toc("11111111-1111-1111-1111-111111111111",
                                            user=AuthUser(user_id="u", email=None)))


def test_toc_derives_the_summa_tree_until_one_is_stored():
    assert [n.key for n in _toc("summa", []).contents] == ["I", "I-II", "II-II", "App."]


def test_a_stored_tree_wins_over_the_derived_one():
    stored = [{"ordinal": 1, "parent_ordinal": None, "node_key": "FP", "kind": "part",
               "label": "First Part", "short_label": "I", "chapter_key": CHAPTERS[0][0],
               "anchor": None, "range_label": None, "anchor_missing": False}]
    assert [n.key for n in _toc("summa", stored).contents] == ["FP"]


def test_a_stale_stored_tree_is_not_replaced_by_a_derived_one():
    stale = [{"ordinal": 1, "parent_ordinal": None, "node_key": "FP", "kind": "part",
              "label": "First Part", "short_label": "I", "chapter_key": "gone",
              "anchor": None, "range_label": None, "anchor_missing": False}]
    assert _toc("summa", stale).contents is None


def test_other_collections_derive_nothing():
    # The Catechism has its own stopgap (tests/test_catechism_contents.py).
    assert _toc("church-fathers", []).contents is None


def test_capitals_inside_a_title_are_title_cased_and_numerals_kept():
    chapters = [(f"{FP}/question-38-of-the-name-five-articles/article-1-whether",
                 "Question 38 - Of the Name of the Holy Ghost---AS GIFT (TWO ARTICLES) — "
                 "Article 1 - Whether Gift is a personal name?"),
                (f"{FP}/question-39-x/article-1-whether",
                 "Question 39 - Of Christ's Grace (II) — Article 1 - Whether I baptize thee?")]
    [part] = derive_summa_contents(chapters)
    assert [q.short_label for q in part.children] == [
        "Q. 38 · Of the Name of the Holy Ghost — as Gift", "Q. 39 · Of Christ's Grace (II)"]
    assert part.children[1].children[0].short_label == "Art. 1 · Whether I baptize thee?"


def test_treatise_headings_in_question_titles_lose_their_range_and_letter():
    chapters = [(f"{SS}/question-71-evil-habits/article-1-whether",
                 "Question 71 - EVIL HABITS, i.e. Vices and Sins (Qq. 71–89) — Article 1 - Whether?"),
                (f"{SS}/question-77-d-by-sins/article-1-whether",
                 "Question 77 - (D) By Sins Committed in Buying and Selling (Q. 77) — Article 1 - Whether?")]
    [part] = derive_summa_contents(chapters)
    assert [q.short_label for q in part.children] == [
        "Q. 71 · Evil Habits, i.e. Vices and Sins", "Q. 77 · By Sins Committed in Buying and Selling"]
