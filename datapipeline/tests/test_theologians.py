"""5.6b's theologians and spiritual writers (issue #207), from CCEL ThML: Teresa of Avila,
Francis de Sales, Julian of Norwich, Thérèse of Lisieux and Ignatius of Loyola; and from
Project Gutenberg text, Alphonsus Liguori and Brother Lawrence."""
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
    assert sorted(docs) == ["Introduction to the Devout Life", "Revelations of Divine Love",
                            "The Autobiography of St. Ignatius", "The Glories of Mary",
                            "The Interior Castle", "The Life of St. Teresa of Jesus",
                            "The Practice of the Presence of God",
                            "The Spiritual Exercises of St. Ignatius of Loyola",
                            "The Story of a Soul", "Treatise on the Love of God"]
    for d in docs.values():
        assert d.collection == T.COLLECTION
        assert d.author in ("Teresa of Avila", "Francis de Sales", "Julian of Norwich",
                            "Thérèse of Lisieux", "Ignatius of Loyola",
                            "Alphonsus Liguori", "Brother Lawrence")
        # The source key is the file's path under sources/.
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


def _opening_marks(doc, key):
    p = next(p for p in doc.passages if p.chapter_key == key)
    return [(p.content[m["at"]:m["end"]], m["level"])
            for m in (p.metadata or {}).get("headings", [])]


def test_castle_leaves_out_the_editors_and_keeps_teresas_headings_in_the_text_marked():
    """Teresa's headings stay in the text, marked (Carter, 23 Nov 2026)."""
    text = _text(_castle())
    assert "No trace of these trials is to be found" not in text     # introduction
    assert "new edition the wording has been revised" not in text    # Zimmerman's note
    assert "Plan of this book" not in text                           # chapter outline
    assert _opening_marks(_castle(), "iv")[0][0].startswith(
        "THIS TREATISE, STYLED THE INTERIOR CASTLE, WAS WRITTEN BY TERESA OF JESUS")
    marks = _opening_marks(_castle(), "v.i")
    assert marks[0] == ("THE FIRST MANSIONS", 1)                   # the mansion's own heading
    assert marks[1][0].startswith("THIS CHAPTER TREATS OF THE BEAUTY AND DIGNITY OF OUR SOULS")
    assert marks[1][1] == 2
    first = next(p for p in _castle().passages if p.chapter_key == "v.i")
    assert "\n\n1. While I was begging our Lord to-day" in first.content
    assert first.metadata["book"] == "The First Mansions"
    assert not any("heading" in (p.metadata or {}) for p in _castle().passages)


def test_every_castle_chapter_keeps_teresas_heading():
    chapters = {p.chapter_key for p in _castle().passages if p.metadata.get("book")}
    heads = {k: [t for t, level in _opening_marks(_castle(), k) if level == 2]
             for k in chapters}
    assert len(heads) == 27 and all(len(h) == 1 for h in heads.values())
    # An empty paragraph stands before the heading in IV ch. ii and VI ch. iv.
    assert heads["viii.ii"][0].startswith("CONTINUES THE SAME SUBJECT")
    assert heads["x.v"][0].startswith("TREATS OF HOW GOD SUSPENDS THE SOUL IN PRAYER")
    mansions = [t for k in chapters for t, level in _opening_marks(_castle(), k) if level == 1]
    assert len(mansions) == 7


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


def test_life_opens_each_chapter_with_teresas_own_heading():
    (heading,) = _opening_marks(_life(), "viii.ii")
    assert heading[1] == 2 and heading[0].startswith(
        "In which she tells how God began to dispose this soul from childhood for virtue")
    first = next(p for p in _life().passages if p.chapter_key == "viii.ii")
    assert first.content.startswith(heading[0] + "\n\n1. I had a father and mother")
    with_heading = {p.chapter_key for p in _life().passages
                    if any(m["level"] == 2 for m in (p.metadata or {}).get("headings", []))}
    assert len(with_heading) == 40
    assert _opening_marks(_life(), "ix.i") == [("The Relations.", 1)]
    # The headings are not Lewis's (Zimmerman's introduction); the document says so.
    assert "left out of the original translation" in _life().notes


def test_castle_epilogue_ends_with_teresas_amen():
    epilogue = [p for p in _castle().passages if p.chapter_key == "xii"]
    assert epilogue[-1].content.rstrip().endswith("Amen.")
    assert "HERE ENDS THE INTERIOR CASTLE" not in _text(_castle())


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
            # A chapter line opens a passage only as a marked heading.
            marked = any(m["at"] == 0 for m in p.metadata.get("headings") or [])
            assert marked or not p.content.startswith(("CHAPTER", "Chapter ")), p.anchor


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


def test_the_extractor_reads_the_headings_as_the_adapter_does():
    classes, divs, paragraphs = T.not_body("../theologians/teresa-castle2.xml")
    assert classes == {"Outline": "apparatus"}
    assert not divs and paragraphs == {"xii-p3": "apparatus"}       # the colophon
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
    ninth = next(p for p in _devout().passages if p.chapter_key == "iii.xvii")
    assert _marks(ninth)[0][0] == "On the Choice open to you between Heaven and Hell."
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
    assert "excessive watching, fasting, or overwork" in _text(_devout())
    # A numbered step glued to the sentence before it (meditations VII to X).
    assert "in God’s Presence. 2. Humble yourself" in _text(_devout())
    assert not re.search(r"[a-z][.!?”]\d{1,2}\. [A-Z]", _text(_devout()))


def test_the_works_are_opted_into_the_heading_checks():
    import health

    documents = health.load_patterns()["H7_unmarked_heading"]["documents"]
    assert {d.id for d in _built().values()} <= set(documents)


# --------------------------------------------------------------------------- Julian, Thérèse

def _julian():
    return _built()["Revelations of Divine Love"]


def _therese():
    return _built()["The Story of a Soul"]


def test_julian_is_the_86_chapters_under_their_revelations():
    labels = _labels(_julian())
    assert labels[:4] == ["Chapter I", "Chapter II", "Chapter III",
                          "The First Revelation · Chapter IV"]
    numbers = [label.rsplit("Chapter ", 1)[1] for label in labels]
    assert len(numbers) == len(set(numbers)) == 86
    # The file types LXXXII as "LXXII"; its place says which it is.
    assert "The Sixteenth Revelation · Chapter LXXXII" in labels
    assert (_julian().year, _julian().translation) == (1393, "Grace Warrack (1901)")


def test_julian_leaves_out_the_scribe_glosses_and_warracks_chapter_subtitles():
    text = _text(_julian())
    assert "Amen Jesu amen" not in text and "Sloane MS." not in text     # the scribe's
    assert "dearworthy Passion" in text                                  # gloss gone
    assert "precious, honoured" not in text
    assert "I saw . . . as it were in the time of His Passion" not in text   # subtitle
    first = next(p for p in _julian().passages if p.chapter_key == "ii.i")
    assert first.content.startswith("In this [moment] suddenly I saw the red blood")
    assert not any((p.metadata or {}).get("headings") for p in _julian().passages)


def test_story_of_a_soul_is_hers_only():
    labels = _labels(_therese())
    assert labels[0] == "Chapter I. Earliest Memories"
    assert labels[10] == "Chapter XI. A Canticle of Love"
    assert labels[11] == "Counsels and Reminiscences"
    assert "Letters to Her Sister Céline · Letter I" in labels
    assert "Letter to Her Cousin, Jeanne Guérin (Madame La Néele)" in labels
    assert "Prayers · An Act of Oblation As a Victim of Divine Love" in labels
    text = _text(_therese())
    for editors in ("electronic edition", "Cardinal Bourne", "END OF THE AUTOBIOGRAPHY",
                    "Most of what follows has been gathered", "(Written during her retreat",
                    "This Prayer was found after the death", "Written for a Novice",
                    "MY SONG OF TO-DAY", "Oh! how I love Thee, Jesus!", "* * *", ". . . . . ."):
        assert editors not in text, editors
    assert "It is to you, dear Mother, that I am about to confide the story of" in text
    assert "J.M.J.T.\n\nMay 8, 1888.\n\nDearest Céline,—There are moments" in text
    assert "Thérèse." in text and "ThÉRÈSE" not in text            # accented opening caps
    assert "novices recorded" in _therese().notes


def test_julian_and_therese_genres():
    assert T.genre("theologians/julian-revelations.xml") == "treatise"
    assert T.genre("theologians/therese-autobio.xml") == "other"


def test_therese_letters_keep_their_dates_and_prayers_their_epigraphs():
    labels = _labels(_therese())
    assert "Letters to Sister Mary of the Sacred Heart · Letter I, February 21, 1888" in labels
    text = _text(_therese())
    assert re.search(r"(?m)^1889\.$", text)                    # a year-only dateline kept
    # Letter V is of 1889 (the file prints 1899); the omission mark after it stays apart.
    assert "March 12, 1889.\n\n… I must forget this world" in text
    various = next(p for p in _therese().passages if p.chapter_key == "xxix.iv")
    roles = [(various.content[m["at"]:m["end"]][:20], m["role"])
             for m in various.metadata["headings"]]
    assert roles == [('"If you ask the Fath', "epigraph"), ('"Just as the King\'s ', "epigraph")]
    joan = next(p for p in _therese().passages if p.chapter_key == "xxix.vii")
    assert joan.content.startswith("PRAYER\n\nInspired by the sight of a statue")
    assert [m["level"] for m in joan.metadata["headings"]] == [1, 2]
    # Each prayer opens with its own printed title, marked as repeating its label.
    humility = next(p for p in _therese().passages if p.chapter_key == "xxix.viii")
    assert humility.content.startswith("PRAYER TO OBTAIN HUMILITY\n\nO JESUS!")
    assert humility.metadata["headings"][0] == {"at": 0, "end": 25, "level": 1,
                                                "role": "heading", "chapter_title": True}


def test_lines_split_without_a_page_break_stay_apart_unless_the_second_runs_on():
    # In Julian and Thérèse, a lead-in ending in a dash and an address are separate
    # paragraphs; de Sales's files join as #460 built them.
    assert "Annecy, the day of the most loving Apostles S. Peter and S. Paul. 1616." \
        in _text(_love())
    assert "open example.—\n\nIt is the most worship" in _text(_julian())
    assert "Your little daughter,\n\nTeresa of the Child Jesus." in _text(_therese())
    # A sentence cut with nothing between, its second part in lower case, is one.
    assert "as much devotion as I ought; I have not loved my neighbour" in _text(_devout())
    assert "Our way and our heaven is true love" in _text(_julian())


# --------------------------------------------------------------------------- Ignatius

def _exercises():
    return _built()["The Spiritual Exercises of St. Ignatius of Loyola"]


def _autobiography():
    return _built()["The Autobiography of St. Ignatius"]


def _passage(doc, anchor):
    return next(p for p in doc.passages if p.anchor == anchor)


def _heads(p):
    return [(p.content[m["at"]:m["end"]], m.get("level"), bool(m.get("chapter_title")))
            for m in p.metadata.get("headings") or []]


def test_exercises_are_the_annotations_weeks_methods_mysteries_and_rules():
    labels = _labels(_exercises())
    assert labels[:3] == ["Annotations", "Presupposition", "First Week · Principle and Foundation"]
    assert "Second Week · The Fourth Day. Two Standards" in labels
    assert "Three Methods of Prayer · First Method. I. The Ten Commandments" in labels
    assert labels[-1] == "Rules · To Have the True Sentiment"
    assert "The Mysteries of the Life of Christ Our Lord · Of the Supper at Bethany" in labels
    assert ("The Mysteries of the Life of Christ Our Lord · Of the Eighth and Ninth "
            "Apparitions") in labels
    text = _text(_exercises())
    # Mullan's preface and general note, the approbations, Paul III's brief and Father
    # Diertins's prayer are the edition's, not Ignatius's.
    for gone in ("present translation of the Exercises", "No change whatever is made",
                 "Diertins", "ROUSE up", "Francis de Borgia", "Given at St. Mark"):
        assert gone not in text
    assert sum(p.metadata.get("editor_note_count", 0) for p in _exercises().passages) == 41
    assert (_exercises().year, _exercises().translation) == (1548, "Elder Mullan (1914)")


def test_exercises_keep_the_manuscripts_headlines_in_the_text_marked():
    # A section's heading over its first chapter; a chapter's title, then its subtitle.
    assert _heads(_passage(_exercises(), "xii.i"))[:2] == [
        ("FIRST WEEK", 1, False), ("PRINCIPLE AND FOUNDATION", 1, True)]
    assert _heads(_passage(_exercises(), "xii.v")) == [
        ("FIRST EXERCISE", 1, True),
        ("IT IS A MEDITATION WITH THE THREE POWERS ON THE FIRST, THE SECOND AND THE THIRD "
         "SIN", 2, False)]
    # A title repeats its label though the label lower-cases "at".
    assert _heads(_passage(_exercises(), "xviii.xxv"))[0] == (
        "OF THE SUPPER AT BETHANY", 1, True)
    # One printed heading set over several lines is one heading.
    assert _heads(_passage(_exercises(), "xiii.ii"))[0][0] == (
        "THE FIRST DAY AND FIRST CONTEMPLATION IT IS ON THE INCARNATION AND CONTAINS THE "
        "PREPARATORY PRAYER, THREE PRELUDES, THREE POINTS AND ONE COLLOQUY")
    # A heading inside a chapter is level 2, in its place.
    third = _passage(_exercises(), "xiii.iii")
    assert ("THE THIRD CONTEMPLATION WILL BE A REPETITION OF THE FIRST AND SECOND EXERCISE",
            2, False) in _heads(third)
    # The work's title stands over the Presupposition, after the Annotations.
    assert _passage(_exercises(), "xi").content.startswith(
        "SPIRITUAL EXERCISES to conquer oneself and regulate one’s life")


def test_exercises_read_out_page_references_and_keep_the_examen_chart():
    text = _text(_exercises())
    assert not re.search(r"\b[Pp]p?\.\s*\d", text)
    assert "the Particular Examen, and then the General Examen" in text
    assert "the Deadly Sins, etc. Let him be recommended" in text
    assert "for recognising different spirits.\n" in text and ".." not in text.replace("...", "")
    assert "Consolation and desolation are spoken of" not in text
    assert "Twelfth Day. On Palm Sunday." in text
    assert "INCLUSIVELY\n\nand it contains the Preparatory Prayer, three Preludes" in text
    assert "and so on.\n\nG\nG\nG\nG\nG\nG" in text
    assert "Ibidem." in text and "lbidem" not in text


def test_autobiography_is_da_camaras_preface_and_the_eight_chapters():
    doc = _autobiography()
    labels = _labels(doc)
    assert labels[0] == "Preface of the Writer"
    assert labels[1] == ("Chapter I. His Military Life—He Is Wounded at the Siege of "
                         "Pampeluna—His Cure—Spiritual Reading—The Apparition—The Gift of "
                         "Chastity")
    assert labels[-1] == ("Chapter VIII. His Arrival in His Native Land and the Virtues "
                          "Practised There—His Journey into Spain and Italy")
    assert len(labels) == 9 and all(len(label) <= 140 for label in labels)
    text = _text(doc)
    assert text.startswith("Jesus, Mary. In the year 1553")
    # O'Conor's preface, caption, chapter summaries and appendix are the editor's.
    for gone in ("Bollandists", "Preface of Father Louis Gonzalez", "HIS MILITARY LIFE",
                 "ST. IGNATIUS AND HIS WORK FOR EDUCATION", "kingdom of Navarre"):
        assert gone not in text
    assert text.rstrip().endswith("Master Natalis can tell the rest.")
    assert not any(p.metadata.get("headings") for p in doc.passages)
    assert doc.notes == T.IGNATIUS_NOTE and doc.year == 1555


# --------------------------------------------------------------------------- Gutenberg

def _glories():
    return _built()["The Glories of Mary"]


def _lawrence():
    return _built()["The Practice of the Presence of God"]


def test_gutenberg_reader_cuts_the_licence_and_puts_notes_at_their_callers():
    from ingest import gutenberg_text as G
    root = G.read_root(os.path.join(T._SRC, "pg72411.txt"), "FOOTNOTES")
    paras = list(root[0])
    assert sum(1 for p in paras for c in p if c.tag == "note") == 1934
    text = " ".join("".join(p.itertext()) for p in paras)
    assert "Project Gutenberg" not in text and "INDEX." not in text
    # A note running into a second paragraph stays one note.
    note = next(c for p in paras for c in p if c.tag == "note" and c.get("n") == "20")
    assert note.text.endswith("Filii gloriam cum Matre, non tam communem judico, quam "
                              "eamdem. S. Arnol. de Laud. Virg.")


def test_glories_of_mary_is_the_authors_parts_and_devotions():
    doc = _glories()
    labels = _labels(doc)
    assert labels[:5] == ["Protest of the Author", "Petition of the Author to Jesus and Mary",
                          "To the Reader", "Introduction",
                          "Prayer to the Blessed Virgin to Obtain a Good Death"]
    assert ("Part I · Chapter I, Section I. Of the Great Confidence We Should Have in "
            "Mary, Because She Is the Queen of Mercy") in labels
    assert "Part I · Chapter III, Section II. Mary, the Hope of Sinners" in labels
    assert "Part I · Chapter IX. How Great Is the Clemency and Mercy of Mary" in labels
    assert "Part II · Discourse I. On the Immaculate Conception of Mary" in labels
    assert "Part II · On the Second Dolor. Of the Flight of Jesus into Egypt" in labels
    assert "Part II · Devotion I. Of the “Hail Mary”" in labels
    assert labels[-1] == "Acclamations in Praise of Mary"
    text = _text(doc)
    for gone in ("first complete translation of the work ever made", "Archbishop of New York",
                 "PAGE.", "END OF THE FIRST PART", "SALVE REGINA, MATER MISERICORDIÆ",
                 "VITA, DULCEDO", "HAST THE HOPE"):
        assert gone not in text
    assert sum(p.metadata.get("editor_note_count", 0) for p in doc.passages) == 1934
    assert doc.metadata["gutenberg_ebook"] == 72411
    assert (doc.year, doc.translation) == (1750, T.ANONYMOUS_1852)


def test_glories_of_mary_marks_its_headings():
    first = next(p for p in _glories().passages
                 if p.chapter_label.startswith("Part I · Chapter I, Section I."))
    assert [(t, lvl) for t, lvl, _ in _heads(first)][:5] == [
        ("PART FIRST: ON THE SALVE REGINA.", 1), ("CHAPTER I.", 1),
        ("Hail queen, Mother of mercy.", 2), ("SECTION I.", 1),
        ("OF THE GREAT CONFIDENCE WE SHOULD HAVE IN MARY, BECAUSE SHE IS THE QUEEN OF "
         "MERCY.", 1)]
    assert _heads(first)[4][2]                          # repeats its label
    marks = [t for p in _glories().passages for t, _, _ in _heads(p)]
    assert marks.count("EXAMPLE.") == 38 and marks.count("PRAYER.") == 38
    assert "Prayer of St. Ephrem." in marks and "MONDAY." in marks


def test_brother_lawrence_is_the_conversations_and_letters():
    doc = _lawrence()
    labels = _labels(doc)
    assert labels[0] == "Conversations · First Conversation"
    assert labels[4] == "Letters · First Letter" and labels[-1] == "Letters · Fifteenth Letter"
    assert len(labels) == 19
    text = _text(doc)
    assert "Publishers of Evangelical Literature" not in text
    assert "This book consists of notes" not in text            # Revell's preface
    assert "I suppose he means" not in text                     # a translator's note
    assert "SECOND LETTER.\n\nTo the Reverend--\n\nNot finding" in text
    assert not any(t.startswith("To the") for p in doc.passages for t, _, _ in _heads(p))
    assert doc.notes == T.LAWRENCE_NOTE and doc.metadata["gutenberg_ebook"] == 13871
    assert sum(p.metadata.get("editor_note_count", 0) for p in doc.passages) == 4


def test_gutenberg_works_keep_their_vulgate_scripture_references_as_footnotes():
    from ingest.scripture_notes import scripture_reference
    # Read only where a work asks: every other collection's footnotes stay as they were.
    assert scripture_reference("Joan. xix. 26.") is None
    assert scripture_reference("Joan. xix. 26.", vulgate=True) == "Joan. xix. 26."
    assert scripture_reference("Gal. i, 10; Eph. vi, 5, 6.", vulgate=True) == \
        "Gal. i, 10; Eph. vi, 5, 6."
    assert scripture_reference("Serm. 18, de Sanct.", vulgate=True) is None
    glories = [f["text"] for p in _glories().passages for f in p.metadata.get("footnotes") or []]
    assert "Eccli. xxiv. 19." in glories and "Cant. 6, 9." in glories and len(glories) == 95
    assert [f["text"] for p in _lawrence().passages
            for f in p.metadata.get("footnotes") or []] == ["Gal. i, 10; Eph. vi, 5, 6."]
