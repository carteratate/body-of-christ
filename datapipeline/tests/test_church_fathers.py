import os
from ingest.church_fathers import build_documents, build_all

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "church-fathers")


def test_apostolic_fathers_splits_into_per_work_documents():
    path = os.path.join(_SRC, "apostolic fathers.xml")
    docs = build_documents(path)
    clement = [d for d in docs if d.author == "Clement of Rome"
               and "First Epistle" in d.title]
    assert clement, [(d.author, d.title) for d in docs][:10]
    d = clement[0]
    assert d.collection == "church-fathers"
    assert d.passages and d.passages[0].chapter_key
    assert not d.passages[0].content.lstrip().startswith("[")


def test_single_author_files_unchanged_author():
    path = os.path.join(_SRC, "confessions.xml")
    docs = build_documents(path)
    assert len(docs) == 1
    assert docs[0].author == "Augustine"


def test_city_of_god_is_one_document_with_books_as_chapters():
    path = os.path.join(_SRC, "city-of-god.xml")
    docs = build_documents(path)
    cog = [d for d in docs if d.title == "City of God"]
    assert len(cog) == 1, [d.title for d in docs]
    d = cog[0]
    assert d.author == "Augustine"
    # Book structure flattened into labels + metadata, not separate documents.
    assert any((p.metadata or {}).get("book", "").startswith("Book") for p in d.passages)
    assert any(" · " in p.chapter_label for p in d.passages)


def test_build_all_has_unique_ids_and_anchors():
    docs = build_all()
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids)), "duplicate document ids"
    for d in docs:
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"duplicate anchors in {d.title!r}"
