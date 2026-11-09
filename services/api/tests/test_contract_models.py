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


# --- corpus cleanup 2.4a: every added field is optional ------------------------------

def test_a_chunk_event_without_the_2_4a_fields_validates():
    from app.models.search import ChunkResult

    result = ChunkResult.model_validate({
        "chunk_id": "c", "content": "x",
        "source": {"collection": "bible", "document_title": "John", "document_id": "d"},
    })
    assert result.status == "current"
    assert (result.tombstone, result.redirect) == (None, None)
    assert (result.source.facts, result.source.language, result.source.passage_note,
            result.source.passage_author) == (None, None, None, None)


def test_bookmarks_documents_passages_and_progress_default_the_2_4a_fields():
    from app.models.bookmarks import BookmarkResponse, BookmarkSource
    from app.models.reading_progress import ReadingProgressItem

    bookmark = BookmarkResponse(id="b", chunk_id="c", created_at="t")
    assert (bookmark.status, bookmark.tombstone, bookmark.redirect) == ("current", None, None)
    source = BookmarkSource(collection="bible", document_title="John", document_id="d")
    assert source.facts is None and source.passage_author is None
    document = _doc()
    assert (document.facts, document.works, document.status) == (None, [], "current")
    passage = ReaderPassage(id="p", anchor="a", chapter_key="c", chapter_label="C", content="x")
    assert (passage.language, passage.note, passage.work_key, passage.passage_author,
            passage.superseded_by) == (None, None, None, None, None)
    chapter = ReaderChapter(document=_doc(), chapter_key="c", chapter_label="C", passages=[])
    assert chapter.redirected_from is None
    item = ReadingProgressItem(document_id="d", chapter_key="c", chapter_label="C",
                               updated_at="t", collection="bible", document_title="John")
    assert (item.status, item.tombstone) == ("current", None)


def test_document_facts_accepts_only_the_four_certainty_labels():
    import pytest
    from pydantic import ValidationError

    from app.models.corpus import DocumentFacts

    assert DocumentFacts(certainty="disputed").certainty == "disputed"
    with pytest.raises(ValidationError):
        DocumentFacts(certainty="probably")
