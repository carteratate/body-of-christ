"""Deterministic document identity and passage anchors.

Both ingestion pipelines (reader → Supabase, search → Qdrant) derive document
ids and anchors from this module so the two stores agree. See the passage
contract spec §2–3.
"""
from __future__ import annotations

import re
import uuid

# Fixed project namespace — NEVER change. Every document_id derives from this;
# changing it would re-key the entire corpus.
DOCUMENT_NS = uuid.UUID("8b4a9d2e-1c6f-4e7a-bf3d-2a5c9e0f17b6")

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphenate, trim to a URL-safe slug."""
    return _NON_SLUG.sub("-", text.strip().lower()).strip("-")


def document_id(*parts: object) -> str:
    """Deterministic UUIDv5 for a work, from its work-key parts (contract §2)."""
    key = "|".join(slugify(str(p)) for p in parts)
    return str(uuid.uuid5(DOCUMENT_NS, key))


def anchor(*segments: object) -> str:
    """Build a stable '/'-joined anchor; integers and digit strings pass through,
    text segments are slugified (contract §3.3)."""
    out: list[str] = []
    for seg in segments:
        s = str(seg)
        out.append(s if s.isdigit() else slugify(s))
    return "/".join(out)


def passage_id(document_id_str: str, anchor_str: str) -> str:
    """Deterministic passage UUID. Used as BOTH chunks.id and the Qdrant point
    id so the reader and search pipelines produce identical ids (contract §4)."""
    return str(uuid.uuid5(DOCUMENT_NS, f"{document_id_str}#{anchor_str}"))
