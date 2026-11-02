"""The source label every passage built from scanned text carries, so the reader can say
"Text from a scanned edition" (2.4b). Passages from clean typed text carry no label."""
from __future__ import annotations

from model import Passage

TEXT_SOURCE = "text_source"
SCAN_ID = "scan_id"
OCR = "ocr"


def ocr_metadata(scan_id: str) -> dict:
    if not scan_id:
        raise ValueError("a scanned passage needs its scan identifier")
    return {TEXT_SOURCE: OCR, SCAN_ID: scan_id}


def label_passage(passage: Passage, scan_id: str) -> Passage:
    """Add the OCR label to a passage an adapter built from scanned text."""
    passage.metadata = {**(passage.metadata or {}), **ocr_metadata(scan_id)}
    return passage


def is_scanned(passage: Passage) -> bool:
    return (passage.metadata or {}).get(TEXT_SOURCE) == OCR


def scanned_text(workdir) -> list[dict]:
    """A work's final text as the tool hands it to an adapter: per passage its text (the
    accepted correction, else the cleaned text), pages and the OCR label."""
    meta = ocr_metadata(workdir.config.scan)
    return [{"id": p.id, "text": p.text, "pages": p.pages, "leaves": p.leaves,
             "metadata": dict(meta)} for p in workdir.passages()]
