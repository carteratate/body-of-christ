from model import Passage, Document


def test_passage_defaults():
    p = Passage(
        content="For God so loved the world…",
        reference="John 3:16",
        anchor="john/3/16",
        chapter_key="john/3",
        chapter_label="John 3",
        position=15,
    )
    assert p.unit_label is None
    assert p.metadata is None
    assert p.position == 15


def test_document_holds_passages():
    p = Passage(
        content="x", reference="r", anchor="a", chapter_key="c",
        chapter_label="C", position=0, unit_label="16",
    )
    doc = Document(id="d", collection="bible", title="John", passages=[p])
    assert doc.translation == ""
    assert doc.passages[0].unit_label == "16"
    assert doc.author is None
