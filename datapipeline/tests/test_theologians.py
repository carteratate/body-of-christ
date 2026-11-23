"""5.6b's theologians and spiritual writers (issue #207): Teresa of Avila's Interior Castle
(Stanbrook, 1921) and Life (Lewis, 1904), from CCEL ThML."""
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re

import pytest

import headings
from ingest import theologians as T

pytestmark = pytest.mark.skipif(
    not all(os.path.exists(os.path.join(T._SRC, w.file)) for w in T.WORKS),
    reason="5.6b's sources not in sources/theologians/ (moved from _incoming/ at merge)")

_docs = None


def _built():
    global _docs
    if _docs is None:
        _docs = {d.title: d for d in T.build_documents()}
    return _docs


def _castle():
    return _built()["The Interior Castle"]


def _life():
    return _built()["The Life of St. Teresa of Jesus"]


def _text(doc) -> str:
    return "\n".join(p.content for p in doc.passages)


def _labels(doc) -> list[str]:
    out = []
    for p in doc.passages:
        if p.chapter_label not in out:
            out.append(p.chapter_label)
    return out


def test_the_documents_under_the_collection_key():
    docs = _built()
    assert sorted(docs) == ["Introduction to the Devout Life", "The Interior Castle",
                            "The Life of St. Teresa of Jesus", "Treatise on the Love of God"]
    for d in docs.values():
        assert d.collection == T.COLLECTION
        assert d.author in ("Teresa of Avila", "Francis de Sales")
        # The source key is the file's path under sources/, so 5.1b.3's rename keeps it.
        assert "../" + d.metadata["source_key"] == d.metadata["source_file"]
    assert (_castle().year, _life().year) == (1577, 1565)
    assert _castle().translation == "Benedictines of Stanbrook (1921)"
    assert _life().translation == "David Lewis (1904)"


def test_castle_chapters_are_the_mansions_with_teresas_preface_and_epilogue():
    labels = _labels(_castle())
    assert labels[0] == "Preface" and labels[-1] == "Epilogue"
    assert labels[1] == "The First Mansions · Chapter I. Description of the Castle"
    assert "The Sixth Mansions · Chapter XI. The Dart of Love" in labels
    assert len(labels) == 2 + 27          # 2, 1, 2, 3, 4, 11 and 4 chapters
    # Zimmerman's introductory note to VI, ch. iii is not a chapter.
    assert not any("Introductory" in label for label in labels)


def test_castle_leaves_out_the_editors_and_keeps_teresas_headings_out_of_the_text():
    text = _text(_castle())
    assert "No trace of these trials is to be found" not in text     # introduction
    assert "new edition the wording has been revised" not in text    # Zimmerman's note
    assert "Plan of this book" not in text                           # chapter outline
    assert "THIS CHAPTER TREATS" not in text.upper()                 # Teresa's heading
    assert "WAS WRITTEN BY TERESA OF JESUS" not in text.upper()      # preface title line
    assert _castle().passages[0].metadata["heading"].startswith(
        "This treatise, styled the Interior Castle, was written by Teresa of Jesus")
    first = next(p for p in _castle().passages if p.chapter_key == "v.i")
    assert first.metadata["heading"].startswith(
        "This chapter treats of the beauty and dignity of our souls")
    assert first.content.startswith("1. While I was begging our Lord to-day")
    assert first.metadata["book"] == "The First Mansions"


def test_every_castle_chapter_keeps_teresas_heading():
    chapters = {p.chapter_key: p.metadata.get("heading") for p in _castle().passages
                if p.metadata.get("book")}
    assert len(chapters) == 27 and all(chapters.values())
    # An empty paragraph stands before the heading in IV ch. ii and VI ch. iv.
    assert chapters["viii.ii"].startswith("Continues the same subject")
    assert chapters["x.v"].startswith("Treats of how God suspends the soul in prayer")


def test_an_opening_i_keeps_the_next_word_in_normal_case():
    assert "1. I have known some" in _text(_castle())


def test_castle_reads_note_255s_caller_out():
    text = _text(_castle())
    assert "described later on. It takes place far" in text
    assert " 8 It takes" not in text


def test_life_has_its_prologue_forty_chapters_and_the_relations():
    labels = _labels(_life())
    assert labels[0] == "Prologue"
    chapters = [label for label in labels if label.startswith("Chapter ")]
    assert len(chapters) == 40
    assert chapters[0] == "Chapter I. Childhood and Early Impressions"
    # "St." does not end the argument's first sentence.
    assert "Chapter XXX. St. Peter of Alcantara Comforts the Saint" in chapters
    relations = [label for label in labels if label.startswith("The Relations · ")]
    assert relations == [f"The Relations · Relation {n}" for n in (
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI")]


def test_life_keeps_teresas_own_heading_on_each_chapter():
    first = next(p for p in _life().passages if p.chapter_key == "viii.ii")
    assert first.metadata["heading"].startswith(
        "In which she tells how God began to dispose this soul from childhood for virtue")
    with_heading = {p.chapter_key for p in _life().passages if p.metadata.get("heading")}
    assert len(with_heading) == 40


def test_life_leaves_out_the_editors_matter():
    text = _text(_life())
    assert "This translation of the Life of St. Teresa is so excellent" not in text
    assert "great-grandmother on the father's side was Teresa Sanchez" not in text
    assert "Childhood and Early Impressions. The Blessing" not in text   # Lewis's argument
    assert "Relations or Manifestations" not in text                    # their title page
    assert "This date refers to the first account" not in text          # Báñez's note
    assert "Fray Do Bañes" not in text
    assert "{p. 479}" not in text                                       # page marker
    assert text.count("This book was finished in June, 1562.") == 1
    # A bracketed note call leaves with its note (ch. xxvi).
    assert "I had never had a vision. But, a very few days afterwards" in text


def test_no_heading_or_note_leaks_and_passages_are_not_empty():
    for doc in _built().values():
        anchors = [p.anchor for p in doc.passages]
        assert len(anchors) == len(set(anchors)), doc.title
        for p in doc.passages:
            assert p.content.strip() and p.chapter_label and p.chapter_key
            assert not p.content.startswith(("CHAPTER", "Chapter ")), p.anchor


def test_a_paragraph_split_at_a_page_break_is_one_paragraph():
    text = _text(_life())
    assert "most grievously tormented; and then it was that these two assaults" in text
    # Across the page marker the build drops (Relation XI).
    assert "for so many years when I thought I was under a delusion" in text
    for doc in (_castle(), _life()):
        for p in doc.passages:
            assert not re.search(r"(?:[a-z,]|\bI)\n\n(?!\d+\. )|\n\n[a-z]", p.content), p.anchor
    # The Devout Life's (Body paragraphs join too).
    assert "as much devotion as I ought; I have not loved my neighbour" in _text(_devout())
    # A numbered paragraph after "Amen" stays its own (VI ch. i).
    assert "for ever blessed! Amen\n\n25. The devils" in _text(_castle())


def test_genres_by_source_key():
    assert T.genre("theologians/desales-devout_life.xml") == "manual"
    assert T.genre("theologians/desales-love.xml") == "treatise"
    assert T.genre("theologians/teresa-castle2.xml") == "treatise"
    assert T.genre("theologians/teresa-life.xml") == "other"
    assert T.genre("medieval/on-loving-god.xml") is None


def test_sentence_case_of_a_heading_in_capitals():
    assert T._sentence_case("OF THE FOURTH MANSIONS. HOW GOD AND OUR LORD SPEAK. I SAY.") \
        == "Of the fourth mansions. How God and Our Lord speak. I say."
    assert T._sentence_case("AS ALSO THE GLORIOUS MOTHER OF GOD") \
        == "As also the glorious Mother of God"
    assert T._sentence_case("HOW ADVANTAGEOUS IT WAS FOR ST. TERESA") \
        == "How advantageous it was for St. Teresa"


def test_the_extractor_reads_the_headings_as_the_adapter_does():
    classes, divs, paragraphs = T.not_body("../theologians/teresa-castle2.xml")
    assert classes == {"Centered": "heading", "Outline": "apparatus"}
    assert not divs and not paragraphs
    assert T.not_body("../theologians/teresa-life.xml") == (
        {}, frozenset({"v"}), {"viii.xli-p58": "apparatus", "ix.xi-p12": "apparatus"})
    assert T.not_body("../theologians/desales-love.xml")[1] == frozenset(
        {"ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii"})
    assert T.not_body("teresa-life.xml") == ({}, frozenset(), {})


def test_source_lock_reads_the_theologians_folder():
    from scripts import source_lock as SL

    inputs = SL._ADAPTER_DIRS["theologians"]()
    assert inputs == {f"theologians/{w.file}": w.url for w in T.WORKS}
    assert SL._role_and_url(SL.SOURCES, "theologians", "theologians/teresa-life.xml",
                            None, {}) == ("adapter-input", "https://ccel.org/ccel/t/teresa/life.xml")
    assert SL._role_and_url(SL.SOURCES, "theologians", "theologians/other.xml", None, {}) \
        == ("vendored-unregistered", None)


# --------------------------------------------------------------------------- de Sales

def _devout():
    return _built()["Introduction to the Devout Life"]


def _love():
    return _built()["Treatise on the Love of God"]


def _marks(p):
    return [(p.content[m["at"]:m["end"]], m["level"], m.get("chapter_title", False))
            for m in (p.metadata or {}).get("headings", [])]


def test_devout_life_is_the_preface_and_five_parts():
    labels = _labels(_devout())
    assert labels[0] == "Preface"
    assert labels[1] == "Part I · Chapter I. What true Devotion is"
    assert labels[-1] == "Part V · Chapter XVIII. Three Important and Final Counsels"
    assert len(labels) == 1 + 24 + 21 + 41 + 15 + 18
    assert (_devout().year, _devout().translation) == (
        1609, "Anonymous translation (Rivingtons, 1876)")
    text = _text(_devout())
    assert "Library of Spiritual Works" not in text and ". . ." not in text   # title, contents
    assert "Pausias of Sicyon" not in text                                    # a note
    assert text.startswith("Dear reader, I request you")                      # opening caps


def test_devout_life_marks_its_meditations_headings():
    first = next(p for p in _devout().passages if p.chapter_key == "iii.ix")
    assert _marks(first)[:3] == [("Of Creation.", 2, False), ("Preparation.", 3, False),
                                 ("Considerations.", 3, False)]
    marked = [m for p in _devout().passages for m in _marks(p)]
    assert sum(1 for m in marked if m[1] == 2) == 10          # one subject per meditation
    assert sum(1 for m in marked if m[1] == 3) == 36
    assert {p.chapter_key for p in _devout().passages
            if any(m[1] > 1 for m in _marks(p))} == {
        f"iii.{n}" for n in ("ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii",
                             "xviii")}


def test_love_of_god_is_the_prayer_preface_and_twelve_books():
    labels = _labels(_love())
    assert labels[:3] == ["Dedicatory Prayer", "Preface", "Book I · Chapter I. That for "
                          "the Beauty of Human Nature God Has Given the Government of All "
                          "the Faculties of the Soul to the Will"]
    assert len(labels) == 2 + 188
    assert all(len(label.split(" · ")[-1]) <= 140 for label in labels)    # cut as thml_doc
    # The label is the printed title, not CCEL's typed div title ("Died by and").
    assert "Book VII · Chapter XIV. That the Glorious Virgin Died by an Extremely Sweet " \
           "and Tranquil Death" in labels
    # Chapters whose div titles carry no number take it from their "CHAPTER N." line.
    assert "Book VII · Chapter VI. Of the Signs of Good Rapture, and of the Third Species " \
           "of the Same" in labels
    text = _text(_love())
    assert "following treatise presents, at first sight" not in text   # Mackey's introduction
    assert "TAN BOOKS" not in text and "Bookdealer" not in text        # TAN's pages
    assert "THE END." not in text


def test_love_of_god_keeps_each_chapter_title_in_the_text_marked():
    openers = {}
    for p in _love().passages:
        openers.setdefault(p.chapter_key, p)
    titled = [p for p in openers.values() if _marks(p)]
    assert len(titled) == 188
    cut = 0
    for p in titled:
        title, level, repeats = _marks(p)[-1]      # a book's first also opens with the book's
        assert level == 1 and title in p.content
        # It repeats the label only where the label holds it whole; a cut label leaves it
        # for the reader to show.
        whole = p.chapter_label.split(" · ", 1)[1].split(". ", 1)[1]
        assert repeats == (headings.normalized(title) == headings.normalized(whole))
        cut += not repeats
    assert cut == 9
    # A long first paragraph does not leave the title alone in a piece (V ch. vii).
    vii = openers["vi.vii"]
    assert vii.content.startswith("HOW THE DESIRE TO EXALT AND MAGNIFY GOD") \
        and "The love of benevolence, then," in vii.content


def test_each_book_and_part_opens_with_its_own_heading():
    def opening(doc, key):
        return _marks(next(p for p in doc.passages if p.chapter_key == key))[0]

    assert opening(_love(), "ii.i") == (
        "BOOK I. CONTAINING A PREPARATION FOR THE WHOLE TREATISE.", 1, False)
    assert opening(_love(), "iii.i")[0] == \
        "THE SECOND BOOK. THE HISTORY OF THE GENERATION AND HEAVENLY BIRTH OF DIVINE LOVE."
    assert opening(_devout(), "v.i") == (
        "PART III. CONTAINING COUNSELS CONCERNING THE PRACTICE OF VIRTUE.", 1, False)
    books = [m for p in _love().passages for m in _marks(p) if "BOOK" in m[0]]
    parts = [m for p in _devout().passages for m in _marks(p) if m[0].startswith("PART ")]
    assert (len(books), len(parts)) == (12, 5)


def test_love_of_god_reads_its_verse_line_by_line():
    p = next(p for p in _love().passages if "Mercy, O Lord, hath not thy soul" in p.content)
    assert "Mercy, O Lord, hath not thy soul forsaken,\nE’en while thy justice" in p.content
    assert "If thou hast ill done, chide thyself bitterly,\nIf thou hast well done" \
        in _text(_love())
    assert "Saint Francis’ song, —\n\n“So vast the joys that I await,\nNo earthly travail" \
        in _text(_devout())


def test_de_sales_stray_note_callers_are_read_out():
    assert "and I am His. A bundle of myrrh" in _text(_devout())
    assert "as his own soul. The great Apostle" in _text(_love())


def test_de_sales_works_are_opted_into_the_heading_checks():
    import health

    documents = health.load_patterns()["H7_unmarked_heading"]["documents"]
    assert {_devout().id, _love().id} <= set(documents)
