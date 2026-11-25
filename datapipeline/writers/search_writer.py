"""Embed neighbor-augmented passages and write them as Qdrant points.

Stored payload content stays clean; overlap exists only in the embedded text.
point.id == chunks.id (the passage ID, `Passage.id`), so RRF dedup across the
vector + FTS paths is correct.

A publish (2.2w) writes every staged passage, searchable or not, into the publish's own
collection (D5). Each vector comes from the first source that has it (D11): the
content-addressed embedding cache, then the point with the same ID and `embed_sha256`
in the collection users search today, then OpenAI for the rest. A vector from OpenAI is
written to the cache before its point is upserted, so an interrupted stage never pays
twice.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import openai
from qdrant_client.models import PointStruct

import collection_keys
from config import settings
from model import Document, Passage
from registry import resolve_passage_id
from writers.qdrant import retrieve, upsert_points

_VERSE_MARKER_RE = re.compile(r"\{\{v:\d+\}\}\s*")


def _strip_verse_markers(text: str) -> str:
    return _VERSE_MARKER_RE.sub("", text)


def _neighbour(passages: list[Passage], idx: int, step: int) -> Passage | None:
    """The nearest searchable passage before (step -1) or after (step 1) `idx` in the
    same chapter key, or None. A history passage, a Latin canon or any other passage
    with searchable = false is skipped, so its text never enters a current passage's
    vector (C-21)."""
    key = passages[idx].chapter_key
    i = idx + step
    while 0 <= i < len(passages) and passages[i].chapter_key == key:
        if passages[i].searchable:
            return passages[i]
        i += step
    return None


def build_embedding_input(passages: list[Passage], idx: int,
                          k_prev: int, k_next: int, prefix: str) -> str:
    p = passages[idx]
    parts = [prefix] if prefix else []
    prev = _neighbour(passages, idx, -1) if k_prev else None
    if prev is not None:
        parts.append(prev.content[-k_prev:])
    parts.append(p.content)
    nxt = _neighbour(passages, idx, 1) if k_next else None
    if nxt is not None:
        parts.append(nxt.content[:k_next])
    return _strip_verse_markers(" ".join(parts).strip())


def display_author(doc: Document, p: Passage) -> str | None:
    """The author shown to users: the passage's own, then its work's, then the
    document's (C-15)."""
    if p.passage_author:
        return p.passage_author
    if p.work_key:
        work = next((w for w in doc.works if w.work_key == p.work_key), None)
        if work is not None and work.author:
            return work.author
    return doc.author


def embedding_prefix(doc: Document, p: Passage) -> str:
    author = display_author(doc, p)
    return f"{author + ' — ' if author else ''}{doc.title}, {p.chapter_label}"


def embedding_inputs(doc: Document) -> list[str]:
    """The exact text embedded for each passage of `doc`, in order."""
    # By source, so the 5.1b.3 rename changes no embedding input and no vector.
    k_prev, k_next = settings.overlap_for(collection_keys.source_of(doc.id, doc.collection))
    return [build_embedding_input(doc.passages, i, k_prev, k_next, embedding_prefix(doc, p))
            for i, p in enumerate(doc.passages)]


def input_sha256(text: str) -> str:
    """The embedding cache key (cache.Cache.embedding_input_hash) and `embed_sha256`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_point(doc: Document, p: Passage, vector: list[float], *,
                embed_sha256: str | None = None, embed_model: str | None = None
                ) -> PointStruct:
    return PointStruct(
        id=p.id or resolve_passage_id(doc.id, p.anchor),
        vector=vector,
        payload={
            "collection": doc.collection,
            "document_id": doc.id,
            "document_title": doc.title,
            "author": display_author(doc, p),
            "content": p.content,          # CLEAN, never the augmented text
            "reference": p.reference,
            "anchor": p.anchor,
            "chapter_label": p.chapter_label,
            # Both are load-bearing and were missing here: `reconcile_qdrant_payloads`
            # added them to 53,747 live points precisely because this writer omitted
            # them, so re-ingesting a collection silently undid that.
            #
            # `fetch_positions` does backfill them from Postgres when a payload lacks
            # them — but only on the healthy path. It is skipped when the pipeline
            # degrades, and `unit_label` is what tells the reranker a Summa passage is an
            # objection Aquinas refutes rather than his teaching.
            "chapter_key": p.chapter_key,
            "unit_label": p.unit_label,
            # Facts search filters on (D5), and the role (C-01).
            "genre": doc.genre,
            "issuer": doc.issuer,
            "searchable": p.searchable,
            "voice": p.voice,
            # What produced the vector (C-23): the hash of the exact input and the model.
            "embed_sha256": embed_sha256,
            "embed_model": embed_model,
        },
    )


async def _embed(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    for attempt in range(3):
        try:
            resp = await client.embeddings.create(
                input=texts, model=settings.EMBEDDING_MODEL,
                # Explicit: omitting it yields the model's native 3072, which the live
                # collection cannot store and the API cannot query.
                dimensions=settings.EMBEDDING_DIMS,
            )
            return [r.embedding for r in sorted(resp.data, key=lambda r: r.index)]
        except openai.RateLimitError:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


@dataclass
class VectorSource:
    """Where a stage gets each vector from, in order (D11): `cache` (an object with
    cache.Cache's get_embedding / put_embedding), then the points of `reuse_from` (the
    collection the live alias targets) whose `embed_sha256` and `embed_model` match, then
    `embed` (OpenAI by default). Counts each source, so the stage can report them."""
    qdrant: object
    cache: object
    reuse_from: str | None
    embed: Callable | None = None
    model: str = field(default_factory=lambda: settings.EMBEDDING_MODEL)
    dimensions: int = field(default_factory=lambda: settings.EMBEDDING_DIMS)
    counts: dict = field(default_factory=lambda: {"cache": 0, "reused": 0, "embedded": 0,
                                                   "embedded_chars": 0})

    async def vectors(self, ids: list[str], inputs: list[str]) -> list[list[float]]:
        hashes = [input_sha256(t) for t in inputs]
        out: list[list[float] | None] = [
            self.cache.get_embedding(h, self.model, self.dimensions) for h in hashes]
        self.counts["cache"] += sum(v is not None for v in out)

        missing = [i for i, v in enumerate(out) if v is None]
        if missing and self.reuse_from:
            found = await retrieve(self.qdrant, self.reuse_from, [ids[i] for i in missing])
            for i in missing:
                point = found.get(ids[i])
                payload = (point.payload or {}) if point is not None else {}
                if payload.get("embed_sha256") == hashes[i] \
                        and payload.get("embed_model") == self.model:
                    out[i] = list(point.vector)
                    self.cache.put_embedding(hashes[i], self.model, self.dimensions, out[i])
                    self.counts["reused"] += 1

        missing = [i for i, v in enumerate(out) if v is None]
        if missing:
            vectors = await self._embed([inputs[i] for i in missing])
            if len(vectors) != len(missing):
                raise RuntimeError(f"got {len(vectors)} vectors for {len(missing)} inputs")
            for i, v in zip(missing, vectors):
                # Into the cache first: an interrupted stage never pays for it again.
                self.cache.put_embedding(hashes[i], self.model, self.dimensions, v)
                out[i] = v
            self.counts["embedded"] += len(missing)
            self.counts["embedded_chars"] += sum(len(inputs[i]) for i in missing)
        return out  # type: ignore[return-value]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if self.embed is not None:
            return await self.embed(texts)
        oa = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        try:
            return await _embed(oa, texts)
        finally:
            await oa.close()


async def write_document(client_qdrant, doc: Document, *, collection_name: str,
                         vectors: VectorSource) -> int:
    """Write one point per passage of `doc` into `collection_name`; return how many.
    Every passage must already carry its `Passage.id` (the stage assigns them)."""
    inputs = embedding_inputs(doc)
    batch = settings.EMBEDDING_BATCH_SIZE
    written = 0
    for start in range(0, len(doc.passages), batch):
        window = doc.passages[start:start + batch]
        texts = inputs[start:start + batch]
        if any(p.id is None for p in window):
            raise ValueError(f"{doc.title}: a passage has no ID; the stage assigns them")
        got = await vectors.vectors([p.id for p in window], texts)
        points = [build_point(doc, p, v, embed_sha256=input_sha256(t),
                              embed_model=vectors.model)
                  for p, v, t in zip(window, got, texts)]
        await upsert_points(client_qdrant, collection_name, points)
        written += len(points)
    return written
