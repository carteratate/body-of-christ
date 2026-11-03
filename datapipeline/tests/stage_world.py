"""A small live corpus, its registry and Qdrant, for the 2.2w stage and report tests.

Live holds two medieval documents (A: four passages in two chapters, B: one passage)
and one summa document, each passage a point in Qdrant collection `chunks`, which the
alias `chunks_live` targets. The registry freezes every live passage. Tests build a new
medieval collection from `World.build` and stage it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (CreateAlias, CreateAliasOperation, Distance, PointStruct,
                                  VectorParams)

import registry
from cache import Cache
from identity import passage_id
from model import ContentsNode, Document, Passage
from publication import StageRunner

DOC_A = "aaaaaaaa-0000-0000-0000-000000000001"
DOC_B = "aaaaaaaa-0000-0000-0000-000000000002"
DOC_S = "aaaaaaaa-0000-0000-0000-000000000003"
DIMS = 1536

# (document, anchor, chapter_key, content)
LIVE = [
    (DOC_A, "a/1", "c1", "Grace perfects nature and does not destroy it."),
    (DOC_A, "a/2", "c1", "Faith seeks understanding in all things."),
    (DOC_A, "a/3", "c2", "Hope is an anchor of the soul, sure and steadfast."),
    (DOC_A, "a/4", "c2", "Charity is the form of all the virtues."),
    (DOC_B, "b/1", "k1", "On consideration, to Pope Eugenius."),
    (DOC_S, "s/1", "q1", "Whether sacred doctrine is a science."),
]
TITLES = {DOC_A: ("medieval", "On Loving God", "Bernard of Clairvaux"),
          DOC_B: ("medieval", "On Consideration", "Bernard of Clairvaux"),
          DOC_S: ("summa", "Summa Theologica", "Thomas Aquinas")}


def pid(document: str, anchor: str) -> str:
    return passage_id(document, anchor)


def vector_for(text: str) -> list[float]:
    """A deterministic unit-ish vector for a text."""
    seed = hashlib.sha256(text.encode()).digest()
    return [((seed[i % 32] + i) % 17 - 8) / 8.0 or 0.125 for i in range(DIMS)]


def passage(anchor: str, chapter: str, content: str, position: int, **extra) -> Passage:
    return Passage(content=content, reference=anchor.upper(), anchor=anchor,
                   chapter_key=chapter, chapter_label=chapter.upper(), position=position,
                   **extra)


def live_documents() -> list[Document]:
    """The live medieval collection as the adapter builds it today."""
    out = []
    for d in (DOC_A, DOC_B):
        rows = [r for r in LIVE if r[0] == d]
        collection, title, author = TITLES[d]
        out.append(Document(id=d, collection=collection, title=title, author=author,
                            passages=[passage(a, k, c, i) for i, (_, a, k, c) in enumerate(rows)]))
    return out


def base_registry() -> registry.WorkRegistry:
    works = [registry.work_entry(collection=c, source_key=f"{c}/{t}", document_id=d,
                                 title=t, author=a, frozen_on="2026-10-30")
             for d, (c, t, a) in TITLES.items()]
    rows = [{"passage_id": pid(d, a), "document_id": d, "anchor": a, "live_anchor": a,
             "status": "active", "frozen_on": "2026-10-30", "work_key": None}
            for d, a, _, _ in LIVE]
    return registry.WorkRegistry(works=works, passages=rows)


@dataclass
class World:
    cluster: object
    database: str
    tmp_path: object
    registry: registry.WorkRegistry = field(default_factory=base_registry)
    build: list[Document] = field(default_factory=live_documents)
    embedded: list[str] = field(default_factory=list)

    async def seed(self) -> None:
        conn = await self.connect()
        try:
            for d, (c, t, a) in TITLES.items():
                await conn.execute(
                    "INSERT INTO documents (id, collection, title, author) VALUES ($1, $2, $3, $4)",
                    d, c, t, a)
            for i, (d, a, k, c) in enumerate(LIVE):
                position = [r for r in LIVE if r[0] == d].index((d, a, k, c))
                await conn.execute(
                    """INSERT INTO chunks (id, document_id, content, position, reference,
                       anchor, chapter_key, chapter_label) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                    pid(d, a), d, c, position, a.upper(), a, k, k.upper())
            for d in TITLES:
                await conn.execute("SELECT refresh_document_outline($1::uuid)", d)
        finally:
            await conn.close()
        self.qdrant = AsyncQdrantClient(location=":memory:")

        async def no_close(*args, **kwargs):
            return None
        self.qdrant.close = no_close
        await self.qdrant.create_collection("chunks", vectors_config=VectorParams(
            size=DIMS, distance=Distance.COSINE))
        await self.qdrant.upsert("chunks", points=[
            PointStruct(id=pid(d, a), vector=vector_for(c),
                        payload={"collection": TITLES[d][0], "document_id": d, "content": c})
            for d, a, _, c in LIVE])
        await self.qdrant.update_collection_aliases(change_aliases_operations=[
            CreateAliasOperation(create_alias=CreateAlias(collection_name="chunks",
                                                          alias_name="chunks_live"))])
        self.cache = Cache(str(self.tmp_path / "cache.db"))
        self.cache.init_schema()

    async def connect(self):
        return await self.cluster.connect(self.database)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded += texts
        return [vector_for(t) for t in texts]

    def runner(self, **kwargs) -> StageRunner:
        adapters = {"medieval": lambda: self.build, "summa": lambda: []}
        return StageRunner(connect=self.connect, qdrant=lambda: self.qdrant,
                           cache=lambda: self.cache, embed=self.embed,
                           source_adapters=kwargs.pop("source_adapters", adapters),
                           registry=self.registry, live_alias="chunks_live", **kwargs)

    async def fetch(self, sql: str, *args):
        conn = await self.connect()
        try:
            return [dict(r) for r in await conn.fetch(sql, *args)]
        finally:
            await conn.close()

    async def public_digest(self) -> dict[str, str]:
        """An md5 of every public table's rows (corpus_publishes aside), to show a stage
        changed nothing live."""
        tables = [r["tablename"] for r in await self.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'corpus_publishes' ORDER BY tablename")]
        out = {}
        for t in tables:
            [row] = await self.fetch(
                f"SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) AS h "
                f"FROM public.{t} t")
            out[t] = row["h"]
        return out


def contents_tree() -> list[ContentsNode]:
    return [ContentsNode(key="book", kind="part", label="Book", short_label="Book",
                         chapter_key="c1", children=[
                             ContentsNode(key="c2", kind="chapter", label="Chapter 2",
                                          short_label="Ch. 2", chapter_key="c2",
                                          anchor="a/3")])]


def dumps(value) -> str:
    return json.dumps(value, sort_keys=True)
