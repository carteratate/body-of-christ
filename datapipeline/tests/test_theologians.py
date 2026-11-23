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
    assert sorted(docs) == ["The Interior Castle", "The Life of St. Teresa of Jesus"]
    for d in docs.values():
        assert d.collection == T.COLLECTION
        assert d.author == "Teresa of Avila"
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
    # A numbered paragraph after "Amen" stays its own (VI ch. i).
    assert "for ever blessed! Amen\n\n25. The devils" in _text(_castle())


def test_genres_by_source_key():
    assert T.genre("theologians/teresa-castle2.xml") == "treatise"
    assert T.genre("theologians/teresa-life.xml") == "other"
    assert T.genre("medieval/on-loving-god.xml") is None


def test_the_extractor_reads_the_headings_as_the_adapter_does():
    classes, divs, paragraphs = T.not_body("../theologians/teresa-castle2.xml")
    assert classes == {"Outline": "apparatus"}
    assert not divs and not paragraphs
    assert T.not_body("../theologians/teresa-life.xml") == (
        {}, frozenset({"v"}), {"viii.xli-p58": "apparatus", "ix.xi-p12": "apparatus"})
    assert T.not_body("teresa-life.xml") == ({}, frozenset(), {})


def test_source_lock_reads_the_theologians_folder():
    from scripts import source_lock as SL

    inputs = SL._ADAPTER_DIRS["theologians"]()
    assert inputs == {f"theologians/{w.file}": w.url for w in T.WORKS}
    assert SL._role_and_url(SL.SOURCES, "theologians", "theologians/teresa-life.xml",
                            None, {}) == ("adapter-input", "https://ccel.org/ccel/t/teresa/life.xml")
    assert SL._role_and_url(SL.SOURCES, "theologians", "theologians/other.xml", None, {}) \
        == ("vendored-unregistered", None)


def test_the_works_are_opted_into_the_heading_checks():
    import health

    documents = health.load_patterns()["H7_unmarked_heading"]["documents"]
    assert {d.id for d in _built().values()} <= set(documents)
