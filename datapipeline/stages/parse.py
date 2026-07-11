"""Parse stage: build in-memory Document/Passage objects via the existing parsers."""
from __future__ import annotations

from model import Document
from ingest import (church_fathers, summa, bible, catechism, medieval,
                    encyclicals, councils, canon_law,
                    apostolic_exhortations, papal_documents)

BUILDERS = {
    "church-fathers": church_fathers.build_all,
    "summa": lambda: [summa.build_document()],
    "bible": bible.build_documents,
    "catechism": lambda: [catechism.build_document()],
    "medieval": medieval.build_documents,
    "encyclicals": encyclicals.build_documents,
    "apostolic-exhortations": apostolic_exhortations.build_documents,
    "papal-documents": papal_documents.build_documents,
    "councils": councils.build_documents,
    "canon-law": canon_law.build_documents,
}


def parse(collection: str) -> list[Document]:
    return BUILDERS[collection]()
