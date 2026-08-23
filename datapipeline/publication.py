"""Reconcile one canonical collection into its selected publication targets.

The runner is the collection-publication boundary. Source adapters stay concerned with
building canonical Documents and Passages; the concrete store adapters translate the
runner's small interface to Supabase/Postgres and Qdrant operations.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Protocol

import asyncpg

from identity import passage_id
from model import Document
from writers import reader_writer


SourceAdapter = Callable[[], list[Document]]

def _build_from(module_name: str, builder_name: str, single: bool = False) -> list[Document]:
    """Load only the selected source adapter and normalize its builder return shape."""
    builder = getattr(import_module(f"ingest.{module_name}"), builder_name)
    built = builder()
    return [built] if single else built


SOURCE_ADAPTERS: dict[str, SourceAdapter] = {
    "apostolic-exhortations": lambda: _build_from(
        "apostolic_exhortations", "build_documents"
    ),
    "bible": lambda: _build_from("bible", "build_documents"),
    "canon-law": lambda: _build_from("canon_law", "build_documents"),
    "catechism": lambda: _build_from("catechism", "build_document", single=True),
    "church-fathers": lambda: _build_from("church_fathers", "build_all"),
    "councils": lambda: _build_from("councils", "build_documents"),
    "encyclicals": lambda: _build_from("encyclicals", "build_documents"),
    "medieval": lambda: _build_from("medieval", "build_documents"),
    "papal-documents": lambda: _build_from("papal_documents", "build_documents"),
    "summa": lambda: _build_from("summa", "build_document", single=True),
}

_MAX_SHRINK = 0.10


class PublicationTarget(str, Enum):
    READER = "reader"
    SEARCH = "search"
    BOTH = "both"

    @property
    def includes_reader(self) -> bool:
        return self in (PublicationTarget.READER, PublicationTarget.BOTH)

    @property
    def includes_search(self) -> bool:
        return self in (PublicationTarget.SEARCH, PublicationTarget.BOTH)


@dataclass(frozen=True)
class PublicationRequest:
    collection: str
    target: PublicationTarget = PublicationTarget.BOTH
    limit: int | None = None
    reset_search_index: bool = False
    wipe_reader: bool = False
    wipe_reader_confirmation: str | None = None


@dataclass(frozen=True)
class PublicationResult:
    collection: str
    target: PublicationTarget
    document_count: int
    passage_count: int
    reader_passages_pruned: int = 0
    reader_documents_pruned: int = 0
    search_passages_pruned: int = 0


class ReaderStore(Protocol):
    async def passage_ids(self, collection: str) -> set[str]: ...

    async def wipe(self, collection: str) -> None: ...

    async def write(self, document: Document, *, prune: bool) -> int: ...

    async def prune_documents(self, collection: str, keep_ids: set[str]) -> int: ...


class SearchIndex(Protocol):
    async def passage_ids(self, collection: str) -> set[str]: ...

    async def reset(self, collection: str) -> None: ...

    async def write(self, document: Document) -> None: ...

    async def prune(self, collection: str, keep_ids: set[str]) -> int: ...


ReaderStoreFactory = Callable[[], AbstractAsyncContextManager[ReaderStore]]
SearchIndexFactory = Callable[[], AbstractAsyncContextManager[SearchIndex]]


class CollectionPublicationRunner:
    def __init__(
        self,
        *,
        source_adapters: Mapping[str, SourceAdapter],
        acquire_reader_store: ReaderStoreFactory,
        acquire_search_index: SearchIndexFactory,
    ) -> None:
        self._source_adapters = source_adapters
        self._acquire_reader_store = acquire_reader_store
        self._acquire_search_index = acquire_search_index

    async def publish(self, request: PublicationRequest) -> PublicationResult:
        self._validate_request(request)
        documents = self._source_adapters[request.collection]()
        if request.limit is not None:
            documents = documents[: request.limit]

        self._validate_documents(request.collection, documents)
        built_ids = {
            passage_id(document.id, passage.anchor)
            for document in documents
            for passage in document.passages
        }

        reader_passages_pruned = 0
        reader_documents_pruned = 0
        search_passages_pruned = 0

        if request.target.includes_reader:
            async with self._acquire_reader_store() as reader:
                if request.limit is None:
                    live_ids = await reader.passage_ids(request.collection)
                    self._validate_build(
                        request.collection,
                        live_ids,
                        built_ids,
                        allow_identity_churn=request.wipe_reader,
                    )
                if request.wipe_reader:
                    await reader.wipe(request.collection)
                for document in documents:
                    reader_passages_pruned += await reader.write(
                        document,
                        prune=request.limit is None and not request.wipe_reader,
                    )
                if request.limit is None and not request.wipe_reader:
                    reader_documents_pruned = await reader.prune_documents(
                        request.collection, {document.id for document in documents}
                    )

        if request.target.includes_search:
            async with self._acquire_search_index() as search:
                if request.limit is None:
                    live_ids = await search.passage_ids(request.collection)
                    self._validate_build(
                        request.collection,
                        live_ids,
                        built_ids,
                        allow_identity_churn=request.reset_search_index,
                    )
                if request.reset_search_index:
                    await search.reset(request.collection)
                for document in documents:
                    await search.write(document)
                if request.limit is None and not request.reset_search_index:
                    search_passages_pruned = await search.prune(
                        request.collection, built_ids
                    )

        return PublicationResult(
            collection=request.collection,
            target=request.target,
            document_count=len(documents),
            passage_count=len(built_ids),
            reader_passages_pruned=reader_passages_pruned,
            reader_documents_pruned=reader_documents_pruned,
            search_passages_pruned=search_passages_pruned,
        )

    def _validate_request(self, request: PublicationRequest) -> None:
        if request.collection not in self._source_adapters:
            raise ValueError(f"unknown collection: {request.collection}")
        if request.limit is not None and request.limit <= 0:
            raise ValueError("limit must be greater than zero")
        if request.reset_search_index and not request.target.includes_search:
            raise ValueError("search-index reset requires a search target")
        if request.wipe_reader and not request.target.includes_reader:
            raise ValueError("reader wipe requires a reader target")
        if request.limit is not None and (
            request.reset_search_index or request.wipe_reader
        ):
            raise ValueError(
                "limited publication cannot reset the search index or wipe the reader store"
            )
        if request.wipe_reader:
            if request.wipe_reader_confirmation != request.collection:
                raise ValueError(
                    "reader-wipe confirmation must exactly match "
                    f"'{request.collection}'"
                )
        elif request.wipe_reader_confirmation is not None:
            raise ValueError("reader-wipe confirmation requires --wipe-reader")

    @staticmethod
    def _validate_documents(collection: str, documents: list[Document]) -> None:
        wrong_collection = next(
            (document.collection for document in documents if document.collection != collection),
            None,
        )
        if wrong_collection is not None:
            raise ValueError(
                f"source adapter for '{collection}' emitted a '{wrong_collection}' document"
            )

    @staticmethod
    def _validate_build(
        collection: str,
        live_ids: set[str],
        built_ids: set[str],
        *,
        allow_identity_churn: bool,
    ) -> None:
        if live_ids and len(built_ids) < len(live_ids) * (1 - _MAX_SHRINK):
            raise ValueError(
                f"REFUSING: the build produced {len(built_ids)} passages against "
                f"{len(live_ids)} live passages for '{collection}' "
                f"({(1 - len(built_ids) / len(live_ids)):.0%} fewer)."
            )
        removed = live_ids - built_ids
        if (
            live_ids
            and not allow_identity_churn
            and len(removed) > len(live_ids) * _MAX_SHRINK
        ):
            raise ValueError(
                f"REFUSING: the build replaces {len(removed)} of {len(live_ids)} "
                f"live passage ids for '{collection}' "
                f"({len(removed) / len(live_ids):.0%})."
            )


class PostgresReaderStore:
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def passage_ids(self, collection: str) -> set[str]:
        rows = await self._connection.fetch(
            """
            SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE d.collection = $1
            """,
            collection,
        )
        return {str(row["id"]) for row in rows}

    async def wipe(self, collection: str) -> None:
        await reader_writer.clear_collection(self._connection, collection)

    async def write(self, document: Document, *, prune: bool) -> int:
        return await reader_writer.write_document(
            self._connection, document, prune=prune
        )

    async def prune_documents(self, collection: str, keep_ids: set[str]) -> int:
        return await reader_writer.prune_missing_documents(
            self._connection, collection, keep_ids
        )


class QdrantSearchIndex:
    def __init__(self, client) -> None:
        self._client = client

    async def passage_ids(self, collection: str) -> set[str]:
        from writers.qdrant import collection_point_ids

        return await collection_point_ids(self._client, collection)

    async def reset(self, collection: str) -> None:
        from writers.qdrant import delete_collection_points

        await delete_collection_points(self._client, collection)

    async def write(self, document: Document) -> None:
        from writers import search_writer

        await search_writer.write_document(self._client, document)

    async def prune(self, collection: str, keep_ids: set[str]) -> int:
        from writers.qdrant import prune_missing_points

        return await prune_missing_points(self._client, collection, keep_ids)


@asynccontextmanager
async def acquire_postgres_reader_store() -> AsyncIterator[ReaderStore]:
    from config import settings

    connection = await asyncpg.connect(settings.DATABASE_URL)
    try:
        yield PostgresReaderStore(connection)
    finally:
        await connection.close()


@asynccontextmanager
async def acquire_qdrant_search_index() -> AsyncIterator[SearchIndex]:
    from writers.qdrant import ensure_collection, get_client

    client = get_client()
    try:
        await ensure_collection(client)
        yield QdrantSearchIndex(client)
    finally:
        await client.close()


def production_runner() -> CollectionPublicationRunner:
    return CollectionPublicationRunner(
        source_adapters=SOURCE_ADAPTERS,
        acquire_reader_store=acquire_postgres_reader_store,
        acquire_search_index=acquire_qdrant_search_index,
    )
