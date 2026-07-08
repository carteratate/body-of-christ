"""Build the per-chunk context block sent to Opus, and clean Bible verse markers."""
from __future__ import annotations

import re

from model import Document, Passage

_VERSE_MARKER_RE = re.compile(r"\{\{v:\d+\}\}\s*")
_WS_RE = re.compile(r"\s+")


def strip_verse_markers(text: str) -> str:
    return _WS_RE.sub(" ", _VERSE_MARKER_RE.sub("", text)).strip()


def enrichment_content(passage: Passage) -> str:
    return strip_verse_markers(passage.content)


def build_context(doc: Document, passage: Passage) -> str:
    return (
        f"collection: {doc.collection}\n"
        f"author: {doc.author or ''}\n"
        f"title: {doc.title}\n"
        f"chapter_label: {passage.chapter_label}\n"
        f"reference: {passage.reference}\n"
        f"content: {enrichment_content(passage)}"
    )
