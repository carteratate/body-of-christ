import sys, os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.thml_doc import make_doc, _cap_pieces


def test_cap_pieces_splits_oversized():
    # Sentence-delimited prose (~5600 chars) so the splitter has real boundaries
    # to break on — mirrors actual ThML passage content.
    text = "Lorem ipsum dolor sit amet. " * 200
    pieces = _cap_pieces(text, 3500)
    assert len(pieces) >= 2
    assert all(len(p) <= 3500 for p in pieces)


def test_make_doc_uses_collection_in_id_and_year():
    import defusedxml.ElementTree as ET
    elem = ET.fromstring("<div2 title='Chapter 1'><p>" + ("word " * 40) + "</p></div2>")
    doc = make_doc(collection="medieval", filename="f.xml", author="Boethius",
                   title="Consolation of Philosophy", chapters=[(None, elem)], year=524)
    assert doc is not None
    assert doc.collection == "medieval"
    assert doc.year == 524
    assert doc.passages and doc.passages[0].chapter_key
    assert not doc.passages[0].content.lstrip().startswith("[")
    from identity import document_id
    assert doc.id == document_id("medieval", "Boethius", "Consolation of Philosophy")
