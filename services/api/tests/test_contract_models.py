from app.models.documents import (
    DocumentResponse, ReaderPassage, ReaderChapter, TocEntry, TocResponse,
)
from app.models.search import ChunkSource


def _doc() -> DocumentResponse:
    return DocumentResponse(id="d", collection="bible", title="John", chunk_count=21)


def test_reader_chapter_shape():
    passage = ReaderPassage(
        id="p1", anchor="john/3/16", chapter_key="john/3", chapter_label="John 3",
        unit_label="16", reference="John 3:16", content="For God so loved…",
    )
    chapter = ReaderChapter(
        document=_doc(), chapter_key="john/3", chapter_label="John 3",
        passages=[passage], prev_chapter_key="john/2", next_chapter_key="john/4",
        highlight_anchor="john/3/16",
    )
    assert chapter.passages[0].unit_label == "16"
    assert chapter.next_chapter_key == "john/4"


def test_reader_passage_optionals_default_none():
    p = ReaderPassage(
        id="p", anchor="a", chapter_key="c", chapter_label="C", content="x",
    )
    assert p.unit_label is None
    assert p.reference is None


def test_toc_response_shape():
    toc = TocResponse(document=_doc(), chapters=[TocEntry(chapter_key="john/1", chapter_label="John 1")])
    assert toc.chapters[0].chapter_label == "John 1"


def test_chunk_source_accepts_anchor():
    src = ChunkSource(collection="bible", document_title="John", document_id="d", anchor="john/3/16")
    assert src.anchor == "john/3/16"


def test_chunk_source_anchor_defaults_none():
    src = ChunkSource(collection="bible", document_title="John", document_id="d")
    assert src.anchor is None
