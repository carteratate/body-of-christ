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
    assert doc.passages[0].reference == "Methodius — Fragments, Chapter 1"
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
    assert p.reference == "Irenaeus — Of the Manichaeans, The Phoenix"
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
    assert docs[1].passages[0].reference == "Methodius — Fragments of Methodius, Chapter 1"
    assert [d.id for d in docs] == ids
