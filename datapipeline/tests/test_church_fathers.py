import os
from ingest.church_fathers import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "church-fathers")


def test_apostolic_fathers_splits_into_per_work_documents():
    path = os.path.join(_SRC, "apostolic fathers.xml")
    docs = build_documents(path)
    # Clement of Rome's First Epistle should be its own document with the right author/title.
    clement = [d for d in docs if d.author == "Clement of Rome"
               and "First Epistle" in d.title]
    assert clement, [(d.author, d.title) for d in docs][:10]
    d = clement[0]
    assert d.collection == "church-fathers"
    assert d.passages and d.passages[0].chapter_key
    # No breadcrumb header cruft in clean content.
    assert not d.passages[0].content.lstrip().startswith("[")


def test_single_author_files_unchanged_author():
    path = os.path.join(_SRC, "confessions.xml")
    docs = build_documents(path)
    assert len(docs) == 1
    assert docs[0].author == "Augustine"
