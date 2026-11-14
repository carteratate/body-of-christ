import sys, os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.common import DISPLAY_PASSAGE_MAX_OVERSHOOT, split_display_passage
from ingest.thml_doc import make_doc


def test_cap_pieces_splits_oversized():
    # Sentence-delimited prose (~5600 chars) so the splitter has real boundaries
    # to break on — mirrors actual ThML passage content.
    text = "Lorem ipsum dolor sit amet. " * 200
    pieces = split_display_passage(text, 3500)
    assert len(pieces) >= 2
    assert all(len(p) <= 3500 + DISPLAY_PASSAGE_MAX_OVERSHOOT for p in pieces)


def test_make_doc_uses_collection_in_id_and_year():
    import defusedxml.ElementTree as ET
    elem = ET.fromstring("<div2 id='ii.i' title='Chapter 1'><p>" + ("word " * 40) + "</p></div2>")
    doc = make_doc(collection="medieval", filename="f.xml", author="Boethius",
                   title="Consolation of Philosophy", chapters=[(None, elem)],
                   source_key="medieval/f.xml", year=524)
    assert doc is not None
    assert doc.collection == "medieval"
    assert doc.year == 524
    assert doc.passages and doc.passages[0].chapter_key
    assert not doc.passages[0].content.lstrip().startswith("[")
    from identity import document_id
    assert doc.id == document_id("medieval", "Boethius", "Consolation of Philosophy")


def _chapters(xml: str):
    import defusedxml.ElementTree as ET
    root = ET.fromstring(xml)
    return [(None, div) for div in root]


_REPEATED = ("<div1 id='ii'>"
             "<div2 id='ii.i' title='Chapter 1'><p id='ii.i-p1'>{a}</p></div2>"
             "<div2 id='ii.ii' title='Chapter 1'><p id='ii.ii-p1'>{b}</p></div2>"
             "</div1>")


def test_anchor_is_div_id():
    xml = _REPEATED.format(a="first " * 40, b="second " * 40)
    doc = make_doc(collection="church-fathers", filename="f.xml", author="A", title="T",
                   chapters=_chapters(xml), source_key="church-fathers/f.xml#ii")
    assert [(p.anchor, p.chapter_key) for p in doc.passages] == \
        [("ii.i", "ii.i"), ("ii.ii", "ii.ii")]
    assert doc.metadata["source_key"] == "church-fathers/f.xml#ii"
    assert doc.metadata["anchor_scheme"] == 2


def test_no_anchor_suffixes():
    # Two chapters with the same label once became `t/chapter-1` and `t/chapter-1--2`.
    long = " ".join(f"Sentence {k} of a chapter long enough to split." for k in range(200))
    xml = _REPEATED.format(a=long, b="second " * 40)
    doc = make_doc(collection="church-fathers", filename="f.xml", author="A", title="T",
                   chapters=_chapters(xml), source_key="church-fathers/f.xml#ii")
    assert not any("--" in p.anchor for p in doc.passages)
    pieces = [p.anchor for p in doc.passages if p.chapter_key == "ii.i"]
    assert pieces[0] == "ii.i" and len(pieces) > 1
    assert all(a.startswith("ii.i/from-p1-") for a in pieces[1:])


_ONE = "<div1 id='ii'><div2 id='ii.i' title='Chapter 1'><p id='ii.i-p1'>{a}</p></div2></div1>"


def test_make_doc_strips_trailing_period_keeps_id():
    from identity import document_id
    doc = make_doc(collection="church-fathers", filename="f.xml", author="Methodius.",
                   title="Fragments.", chapters=_chapters(_ONE.format(a="word " * 40)),
                   source_key="church-fathers/unregistered.xml#ii")
    assert (doc.author, doc.title) == ("Methodius", "Fragments")
    assert doc.passages[0].reference == "Fragments, Chapter 1"
    # identity.slugify drops punctuation, so the computed ID is the one the period gave.
    assert doc.id == document_id("church-fathers", "Methodius.", "Fragments.")


def test_make_doc_folds_ligatures_in_labels():
    xml = "<div1 id='ii'><div2 id='ii.i' title='The Phœnix'><p>{a}</p></div2></div1>"
    doc = make_doc(collection="church-fathers", filename="f.xml", author="Irenæus",
                   title="Of the Manichæans.", chapters=_chapters(xml.format(a="æons " * 40)),
                   source_key="church-fathers/unregistered.xml#ii")
    p = doc.passages[0]
    assert (doc.author, doc.title, p.chapter_label) == \
        ("Irenaeus", "Of the Manichaeans", "The Phoenix")
    assert p.reference == "Of the Manichaeans, The Phoenix"
    assert "æ" not in p.content


def test_distinct_titles_gives_shared_titles_their_author():
    from ingest.thml_doc import distinct_titles

    def doc(author, title, key):
        return make_doc(collection="church-fathers", filename="f.xml", author=author,
                        title=title, chapters=_chapters(_ONE.format(a="word " * 40)),
                        source_key=f"church-fathers/f.xml#{key}")
    docs = [doc("Papias", "Fragments", "a"), doc("Methodius.", "Fragments.", "b"),
            doc("Polycarp", "Epistle to the Philippians", "c"),
            doc("Ignatius", "Epistle to the Philippians", "d"),
            doc("Ignatius", "Epistle to the Romans", "e")]
    ids = [d.id for d in docs]
    docs = distinct_titles(docs)
    assert [d.title for d in docs] == [
        "Fragments of Papias", "Fragments of Methodius",
        "Epistle of Polycarp to the Philippians", "Epistle of Ignatius to the Philippians",
        "Epistle to the Romans"]
    assert docs[1].passages[0].reference == "Fragments of Methodius, Chapter 1"
    assert [d.id for d in docs] == ids


def test_make_doc_strips_notes_and_counts_them_per_piece():
    import defusedxml.ElementTree as ET
    body = " ".join(f"Sentence {k} of a chapter long enough to split." for k in range(150))
    note = '<note n="1" place="foot"><p>Matt. xxiv. 15.</p></note>'
    xml = (f"<div2 id='ii.i' title='Chapter 1'><p id='ii.i-p1'>Start{note} {body}</p>"
           f"<p id='ii.i-p2'>{body}{note} end{note}.</p></div2>")
    doc = make_doc(collection="church-fathers", filename="f.xml", author="A", title="T",
                   chapters=[(None, ET.fromstring(xml))], source_key="church-fathers/f.xml")
    assert len(doc.passages) >= 2
    assert not any("xxiv" in p.content for p in doc.passages)
    counts = [p.metadata.get("editor_note_count", 0) for p in doc.passages]
    assert sum(counts) == 3 and counts[0] == 1 and counts[-1] == 2
    first, last = doc.passages[0], doc.passages[-1]
    assert first.metadata["footnotes"] == [{"n": 1, "text": "Matt. xxiv. 15.", "at": 5}]
    assert first.content[:5] == "Start"
    assert [(f["n"], f["text"]) for f in last.metadata["footnotes"]] == \
        [(1, "Matt. xxiv. 15."), (2, "Matt. xxiv. 15.")]
    assert last.content[:last.metadata["footnotes"][1]["at"]].endswith(" end")


def test_only_scripture_notes_become_footnotes():
    import defusedxml.ElementTree as ET
    body = "word " * 30
    xml = (f"<div2 id='ii.i'><p id='ii.i-p1'>He said<note n='4'>Ps. xxxiv. 8, where Clem. has "
           f"read otherwise.</note> this<note n='5'>Literally, 'that.'</note>, and"
           f"<note n='6'>[A noble utterance.]</note> {body}</p></div2>")
    doc = make_doc(collection="church-fathers", filename="f.xml", author="A", title="T",
                   chapters=[(None, ET.fromstring(xml))], source_key="church-fathers/f.xml")
    [p] = doc.passages
    assert p.metadata["editor_note_count"] == 3
    assert p.metadata["footnotes"] == [{"n": 1, "text": "Ps. xxxiv. 8.", "at": 7}]
    assert "noble" not in p.content and "Literally" not in p.content


def test_short_chapter_stays_when_its_notes_go():
    # The minimum chapter length is measured with the notes, as before 1.10b, so a short
    # chapter of the author's text is not dropped because its footnote is.
    import defusedxml.ElementTree as ET
    xml = ("<div3 id='v.x.vii'><p id='v.x.vii-p1'>The Christian has not power over himself, "
           "but is ready to be subject to God.<note n='9'>These are the only parts of chaps. "
           "vii. and viii. in the Greek.</note></p></div3>")
    doc = make_doc(collection="church-fathers", filename="f.xml", author="A", title="T",
                   chapters=[(None, ET.fromstring(xml))], source_key="church-fathers/f.xml")
    assert [p.content for p in doc.passages] == \
        ["The Christian has not power over himself, but is ready to be subject to God."]
    assert doc.passages[0].metadata["editor_note_count"] == 1
    assert "footnotes" not in doc.passages[0].metadata


def test_verse_block_is_a_named_paragraph():
    from ingest.thml_doc import paragraph_segments
    import defusedxml.ElementTree as ET
    xml = ("<div3 id='iii.ii'><p id='iii.ii-p1'>Homer says:</p>"
           "<verse id='iii.ii-p1.2'><l>Among the gods</l><l>Rose laughter.</l></verse></div3>")
    assert [(s.locator, s.text) for s in paragraph_segments(ET.fromstring(xml))] == \
        [("p1", "Homer says:"), ("p1.2", "Among the gods\nRose laughter.")]


def test_long_title_label_kept_whole_up_to_140_characters():
    from ingest.thml_doc import _chapter_label
    import defusedxml.ElementTree as ET
    short = "Chapter I. Why we should love God and the measure of that love"
    assert _chapter_label(ET.fromstring(f"<div1 id='iii' title='{short}'/>")) == short
    long = "Chapter II. " + "word " * 40
    label = _chapter_label(ET.fromstring(f"<div1 id='iv' title='{long}'/>"))
    assert len(label) <= 140 and label.endswith("word")


def test_book_without_chapters_labelled_by_its_name():
    chapters = _chapters("<root><div1 id='ii' title='Book I'><p>" + "word " * 40
                         + "</p></div1></root>")
    doc = make_doc(collection="medieval", filename="f.xml", author="Boethius",
                   title="Consolation", chapters=chapters, source_key="medieval/f.xml")
    assert doc.passages[0].chapter_label == "Book I"


def test_book_text_above_its_chapters_is_its_introduction():
    import defusedxml.ElementTree as ET
    book = ET.fromstring("<div1 id='FOUR' type='Book' shorttitle='Book IV'><p>"
                         + "word " * 40 + "</p><div2 id='FOUR.1' title='One'><p>"
                         + "word " * 40 + "</p></div2></div1>")
    doc = make_doc(collection="medieval", filename="f.xml", author="Thomas",
                   title="Imitation", chapters=[(None, book), ("Book IV", book[1])],
                   source_key="medieval/f.xml")
    assert doc.passages[0].chapter_label == "Book IV · Introduction"


def test_roman_capitals():
    from normalize.caps import roman_capitals
    assert roman_capitals("Ii.") == "II."
    assert roman_capitals("Book XII · Chapter Xi") == "Book XII · Chapter XI"
    assert roman_capitals("Civil Law, Ill Health, Lil") == "Civil Law, Ill Health, Lil"
