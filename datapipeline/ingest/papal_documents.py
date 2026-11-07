"""Papal documents: bulls and apostolic letters (the parser is `ingest/papal_common.py`)."""
from __future__ import annotations

import os

from ingest import papal_common
from model import Document

COLLECTION = "papal-documents"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", COLLECTION)


def build_documents() -> list[Document]:
    return papal_common.build_documents(COLLECTION, _SRC)
