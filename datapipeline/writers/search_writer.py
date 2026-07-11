"""Embed neighbor-augmented passages and upsert them to Qdrant.

Stored payload content stays clean; overlap exists only in the embedded text.
point.id == chunks.id (deterministic passage id), so RRF dedup across the
vector + FTS paths is correct.
"""
from __future__ import annotations

import asyncio
import re

import openai
from qdrant_client.models import PointStruct

from config import settings
from identity import passage_id
from model import Document, Passage
from writers.qdrant import upsert_points

_VERSE_MARKER_RE = re.compile(r"\{\{v:\d+\}\}\s*")


def _strip_verse_markers(text: str) -> str:
    return _VERSE_MARKER_RE.sub("", text)


def build_embedding_input(passages: list[Passage], idx: int,
                          k_prev: int, k_next: int, prefix: str) -> str:
    p = passages[idx]
    parts = [prefix] if prefix else []
    if k_prev and idx > 0 and passages[idx - 1].chapter_key == p.chapter_key:
        parts.append(passages[idx - 1].content[-k_prev:])
    parts.append(p.content)
    if k_next and idx + 1 < len(passages) and passages[idx + 1].chapter_key == p.chapter_key:
        parts.append(passages[idx + 1].content[:k_next])
    return _strip_verse_markers(" ".join(parts).strip())


def build_point(doc: Document, p: Passage, vector: list[float]) -> PointStruct:
    return PointStruct(
        id=passage_id(doc.id, p.anchor),
        vector={"dense": vector},          # named vector (was a bare list)
        payload={
            "collection": doc.collection,
            "document_id": doc.id,
            "document_title": doc.title,
            "author": doc.author,
            "content": p.content,          # CLEAN, never the augmented text
            "reference": p.reference,
            "anchor": p.anchor,
            "chapter_label": p.chapter_label,
        },
    )


async def _embed(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    for attempt in range(3):
        try:
            resp = await client.embeddings.create(
                input=texts, model=settings.EMBEDDING_MODEL,
            )
            return [r.embedding for r in sorted(resp.data, key=lambda r: r.index)]
        except openai.RateLimitError:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


async def write_document(client_qdrant, doc: Document) -> None:
    """Embed all passages (augmented) and upsert points for one document."""
    oa = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    k_prev, k_next = settings.overlap_for(doc.collection)
    try:
        batch = settings.EMBEDDING_BATCH_SIZE
        for start in range(0, len(doc.passages), batch):
            window = doc.passages[start:start + batch]
            author_part = f"{doc.author} — " if doc.author else ""
            inputs = [
                build_embedding_input(doc.passages, start + i, k_prev, k_next,
                                      f"{author_part}{doc.title}, {p.chapter_label}")
                for i, p in enumerate(window)
            ]
            vectors = await _embed(oa, inputs)
            points = [build_point(doc, p, v) for p, v in zip(window, vectors)]
            await upsert_points(client_qdrant, points)
    finally:
        await oa.close()
