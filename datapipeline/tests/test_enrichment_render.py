from model import Document, Passage
from enrichment.render import strip_verse_markers, enrichment_content, build_context


def _passage(content):
    return Passage(content=content, reference="Gen 1:1", anchor="genesis/1/1",
                   chapter_key="genesis/1", chapter_label="Genesis 1", position=0)


def test_strip_verse_markers():
    assert strip_verse_markers("{{v:1}} In the beginning {{v:2}} and") == "In the beginning and"


def test_enrichment_content_strips_and_collapses():
    assert enrichment_content(_passage("{{v:1}}  In   the beginning")) == "In the beginning"


def test_build_context_contains_metadata_and_clean_content():
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses")
    ctx = build_context(doc, _passage("{{v:1}} In the beginning"))
    assert "collection: bible" in ctx
    assert "author: Moses" in ctx
    assert "title: Genesis" in ctx
    assert "chapter_label: Genesis 1" in ctx
    assert "reference: Gen 1:1" in ctx
    assert "In the beginning" in ctx
    assert "{{v:" not in ctx
