"""Build collections and stage them for a publish (2.2w, D2).

A publish never writes straight into live tables. `StageRunner.stage` builds the
selected collections, writes them into the `staging` schema and a new Qdrant collection
`chunks-<release>`, and records the publish in `corpus_publishes`. `publish.py report`
then compares staging with live, and `publish.py apply` moves it into live in one
transaction. Nothing here writes a `public` table other than
`corpus_publishes`, or a Qdrant collection an alias points at.

Source adapters stay concerned with building canonical Documents and Passages; `build`
runs one and the document checks, and opens no store, so a dry run uses it.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module

import asyncpg

import card_notes
import collection_keys
import contents
import registry as reg
import retirements
from checks import card_notes as card_notes_check
from health import refuse_block_violations
from model import Document
from writers import reader_writer

SourceAdapter = Callable[[], list[Document]]

DATAPIPELINE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(DATAPIPELINE, "cache.db")


def _build_from(module_name: str, builder_name: str, single: bool = False) -> list[Document]:
    """Load only the selected source adapter and normalize its builder return shape."""
    builder = getattr(import_module(f"ingest.{module_name}"), builder_name)
    built = builder()
    return [built] if single else built


# The builds by source (`datapipeline/sources/<key>/`): each adapter as it is, its
# documents filed under the key its frozen IDs are registered by. The coverage, health
# and release checks (0.1a to 0.1c) judge sources, and their known defects are keyed by
# these names, before and after 5.1b.3.
SOURCE_BUILDS: dict[str, SourceAdapter] = {
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

# Boethius's Consolation of Philosophy: built from the medieval source, published with
# the Fathers since 5.1b.3 (by its frozen registry ID).
BOETHIUS_DOCUMENT_ID = "9a6599ee-ac40-5017-a2c6-7aad2cf14296"


def _published_as(collection: str, documents: list[Document]) -> list[Document]:
    """Documents filed under the collection they are published in (5.1b.3)."""
    for document in documents:
        document.collection = collection
    return documents


def _papal() -> list[Document]:
    """The three papal sources as one collection. Publishing one of them alone under
    `papal` would make 2.2w retire the other two, which nothing in the removal registry
    explains (D4), so they are one adapter."""
    return _published_as("papal", [
        *SOURCE_BUILDS["encyclicals"](),
        *SOURCE_BUILDS["apostolic-exhortations"](),
        *SOURCE_BUILDS["papal-documents"](),
    ])


def _theologians() -> list[Document]:
    return _published_as("theologians", [
        d for d in SOURCE_BUILDS["medieval"]() if d.id != BOETHIUS_DOCUMENT_ID])


def _church_fathers() -> list[Document]:
    boethius = [d for d in SOURCE_BUILDS["medieval"]() if d.id == BOETHIUS_DOCUMENT_ID]
    return _published_as("church-fathers", [*SOURCE_BUILDS["church-fathers"](), *boethius])


# The builds by the collection each publishes (`collection_keys`): what a stage writes,
# and what `documents.collection` and the Qdrant payload hold after it.
SOURCE_ADAPTERS: dict[str, SourceAdapter] = {
    "bible": SOURCE_BUILDS["bible"],
    "catechism": SOURCE_BUILDS["catechism"],
    "church-fathers": _church_fathers,
    "church-law": lambda: _published_as("church-law", SOURCE_BUILDS["canon-law"]()),
    "councils": SOURCE_BUILDS["councils"],
    "papal": _papal,
    "summa": SOURCE_BUILDS["summa"],
    "theologians": _theologians,
}


source_of = collection_keys.source_of


def by_source(documents: list[Document], registry: reg.WorkRegistry | None = None
              ) -> dict[str, list[Document]]:
    """Documents grouped by source, each a copy filed under its source key."""
    import dataclasses

    out: dict[str, list[Document]] = {}
    for d in documents:
        key = source_of(d.id, d.collection, registry)
        out.setdefault(key, []).append(
            d if key == d.collection else dataclasses.replace(d, collection=key))
    return out


WORK_ORDINAL_LIMIT = 1_000_000


# --------------------------------------------------------------------------- build

def build(collection: str, *, source_adapters: Mapping[str, SourceAdapter] = SOURCE_ADAPTERS,
          limit: int | None = None, registry: reg.WorkRegistry | None = None,
          held_coverage: bool = True) -> list[Document]:
    """Run the collection's source adapter, drop what the removal registry retires (D4),
    set each document's facts from the work registry (2.3) and its held texts (4.3),
    and run the document checks. Opens no store."""
    if collection not in source_adapters:
        raise ValueError(f"unknown collection: {collection}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")
    documents = source_adapters[collection]()
    if limit is not None:
        documents = documents[:limit]
    removed = reg.removed_document_ids(registry)
    documents = [reg.attach_held_texts(
                     reg.apply_document_facts(reg.drop_removed(d, registry), registry), registry)
                 for d in documents if d.id not in removed]
    validate_documents(collection, documents)
    # 4.3: every held removal of these documents belongs to one held-text entry. Off
    # only for scripts/held_texts.py, which drafts the entries that are missing.
    problems = (reg.held_text_problems(registry, {d.id for d in documents})
                if held_coverage else [])
    if problems:
        raise ValueError(f"REFUSING: {len(problems)} held-text problems: "
                         + "; ".join(problems[:5]))
    return documents


def validate_documents(collection: str, documents: list[Document]) -> None:
    wrong_collection = next(
        (document.collection for document in documents if document.collection != collection),
        None,
    )
    if wrong_collection is not None:
        raise ValueError(
            f"source adapter for '{collection}' emitted a '{wrong_collection}' document"
        )
    # Health block rules (item 0.1b). build() runs this before a stage opens any store,
    # and a dry run runs it too. Rules and their known defects are per source, so a
    # published collection is judged source by source (5.1b.3).
    for source, docs in by_source(documents).items():
        refuse_block_violations(source, docs)
    # Contents trees (#250): a node must open a chapter the document has, in reading
    # order. Raises contents.ContentsError, a ValueError.
    for document in documents:
        contents.check(document)
    # The apply parks live works at ordinal + 1,000,000 while it writes these, and a
    # rollback parks them above both, which holds only while a built ordinal stays below.
    for document in documents:
        bad = [w.work_key for w in document.works if not 0 < w.ordinal < WORK_ORDINAL_LIMIT]
        if bad:
            raise ValueError(f"REFUSING: {document.title}: work ordinal outside 1 to "
                             f"{WORK_ORDINAL_LIMIT - 1}: {', '.join(bad)}")


def prepare(documents: list[Document], registry: reg.WorkRegistry | None = None
            ) -> tuple[list[Document], list[str]]:
    """Each document with its passage-registry overrides applied (the registry wins over
    the adapter, D11), every `Passage.id` assigned (D1) and its card notes stored (4.4,
    `card_notes.apply`, checked by `checks/card_notes.py`), and the genuinely new IDs.
    A dry run and a stage both call this, so both refuse a note without its kind."""
    out, new = [], []
    entries = (registry or reg.current()).entry_by_document
    for d in documents:
        d, fresh = reg.assign_ids(reg.apply_overrides(d, registry), registry)
        out.append(card_notes.apply(d, entries.get(d.id)))
        new += fresh
    card_notes_check.check(out)
    return out, new


# --------------------------------------------------------------------------- stage

@dataclass(frozen=True)
class StageRequest:
    release: str
    collections: tuple[str, ...]


@dataclass
class StageResult:
    release: str
    qdrant_collection: str
    documents: int
    passages: int
    new_ids: list[str]
    tombstones: int
    redirects: dict[str, int]
    moved: int
    copied: dict[str, int]
    vectors: dict[str, int]


class StageRefused(ValueError):
    """A stage that must not run. A ValueError, so the CLI reports it as a refusal."""


def staging_collection_name(release: str) -> str:
    from config import settings

    return settings.QDRANT_WRITE_COLLECTION or f"chunks-{release}"


LIVE_PASSAGES_SQL = """
SELECT c.id::text AS id, c.document_id::text AS document_id, d.collection, c.anchor,
       c.chapter_key, c.chapter_label, c.reference, c.position, d.title, d.author
FROM public.chunks c JOIN public.documents d ON d.id = c.document_id
WHERE d.collection = ANY($1::text[]) AND c.retired_at IS NULL
ORDER BY d.collection, c.document_id, c.position
"""
LIVE_DOCUMENTS_SQL = """
SELECT id::text AS id, collection, title, author FROM public.documents
WHERE collection = ANY($1::text[]) AND retired_at IS NULL
ORDER BY id
"""


LIVE_ANCHOR_REDIRECTS_SQL = """
SELECT old_document_id::text AS old_document_id, old_anchor,
       new_document_id::text AS new_document_id
FROM public.corpus_redirects WHERE entity = 'anchor'
ORDER BY old_document_id, old_anchor
"""


async def live_anchor_redirects(conn: asyncpg.Connection
                                ) -> list[retirements.LiveAnchorRedirect]:
    return [retirements.LiveAnchorRedirect(**dict(r))
            for r in await conn.fetch(LIVE_ANCHOR_REDIRECTS_SQL)]


async def live_rows(conn: asyncpg.Connection, collections: list[str]
                    ) -> tuple[list[retirements.LivePassage], list[retirements.LiveDocument]]:
    passages = [retirements.LivePassage(**dict(r))
                for r in await conn.fetch(LIVE_PASSAGES_SQL, collections)]
    documents = [retirements.LiveDocument(**dict(r))
                 for r in await conn.fetch(LIVE_DOCUMENTS_SQL, collections)]
    return passages, documents


# One advisory lock for every change to who holds the shared staging tables.
PUBLISH_LOCK_KEY = "theocorpus.corpus_publishes"


async def lock_publishes(conn: asyncpg.Connection) -> None:
    """Wait for, then hold until commit, the lock that serializes claiming and releasing
    staging, so two releases cannot both see it free. Call inside a transaction."""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", PUBLISH_LOCK_KEY)


async def begin_publish(conn: asyncpg.Connection, release: str, collections: list[str],
                        qdrant_collection: str) -> dict | None:
    """Record (or extend) the publish row, refusing when staging holds a different
    publish that is neither cleaned up nor discarded, or when `release` names a publish
    that was applied, cleaned up or discarded. Returns the row as it was before, or None
    for a new publish. Call inside the stage's transaction: the check and the claim hold
    `lock_publishes` until it commits."""
    await lock_publishes(conn)
    holder = await conn.fetchval(
        """SELECT id FROM corpus_publishes
           WHERE id <> $1 AND cleaned_up_at IS NULL AND discarded_at IS NULL
           ORDER BY id LIMIT 1""", release)
    if holder is not None:
        raise StageRefused(f"REFUSING: staging holds publish '{holder}', which is neither "
                           "cleaned up nor discarded; run `publish.py cleanup` or `discard` "
                           "for it first")
    row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
    if row is None:
        await conn.execute(
            """INSERT INTO corpus_publishes (id, collections, qdrant_collection)
               VALUES ($1, $2::text[], $3)""", release, sorted(collections), qdrant_collection)
        return None
    for column in ("applied_at", "cleaned_up_at", "discarded_at"):
        if row[column] is not None:
            raise StageRefused(f"REFUSING: publish '{release}' was {column.removesuffix('_at')}"
                               "; name a new release")
    if row["qdrant_collection"] != qdrant_collection:
        raise StageRefused(f"REFUSING: publish '{release}' writes Qdrant collection "
                           f"'{row['qdrant_collection']}', not '{qdrant_collection}'")
    merged = sorted(set(row["collections"]) | set(collections))
    await conn.execute(
        """UPDATE corpus_publishes SET collections = $2::text[], staged_at = NULL,
           report_sha256 = NULL WHERE id = $1""", release, merged)
    return dict(row)


class StageRunner:
    """Stages collections for one release. Every dependency is injected, so tests run it
    against a local PostgreSQL and an in-memory Qdrant."""

    def __init__(
        self,
        *,
        connect: Callable,                 # async () -> asyncpg.Connection
        qdrant: Callable,                  # () -> AsyncQdrantClient
        cache: Callable,                   # () -> cache.Cache-like
        write_guard: Callable[[str, str], None] | None = None,   # (collection, release)
        source_adapters: Mapping[str, SourceAdapter] = SOURCE_ADAPTERS,
        embed: Callable | None = None,     # async (texts) -> vectors; OpenAI when None
        registry: reg.WorkRegistry | None = None,
        live_alias: str | None = None,
        qdrant_collection: str | None = None,
    ) -> None:
        self._connect = connect
        self._qdrant = qdrant
        self._cache = cache
        self._write_guard = write_guard
        self._source_adapters = source_adapters
        self._embed = embed
        self._registry = registry
        self._live_alias = live_alias
        self._qdrant_collection = qdrant_collection

    async def stage(self, request: StageRequest) -> StageResult:
        from config import settings
        from qdrant_schema import create_chunks_collection
        from writers import qdrant as qd
        from writers.search_writer import VectorSource, write_document

        collections = list(request.collections)
        for c in collections:
            if c not in self._source_adapters:
                raise ValueError(f"unknown collection: {c}")
        if self._write_guard is not None:
            label = "all" if set(collections) == set(SOURCE_ADAPTERS) else None
            for c in [label] if label else collections:
                self._write_guard(c, request.release)

        # Build and check everything before any store is opened: a refusal writes nothing.
        documents: list[Document] = []
        new_ids: list[str] = []
        for c in collections:
            built, fresh = prepare(build(c, source_adapters=self._source_adapters,
                                         registry=self._registry), self._registry)
            documents += built
            new_ids += fresh
        registry = self._registry or reg.current()

        alias = self._live_alias or settings.QDRANT_LIVE_ALIAS
        name = self._qdrant_collection or staging_collection_name(request.release)
        client = self._qdrant()
        conn = await self._connect()
        try:
            live = await qd.alias_target(client, alias)
            if live is None:
                raise StageRefused(
                    f"REFUSING: there is no Qdrant alias '{alias}'. Create it on the "
                    "collection users search (2.2b's ops step) before staging; a stage "
                    "copies vectors and untouched collections from its target")
            if name in (live, alias, qd.PRE_ALIAS_COLLECTION):
                raise StageRefused(f"REFUSING: '{name}' is what users search")

            # Decide whether the Qdrant collection is ours before anything is written: a
            # refused stage must leave no publish row that a retry would read as proof.
            exists = await client.collection_exists(name)
            if exists:
                owner = await conn.fetchval(
                    "SELECT qdrant_collection FROM corpus_publishes WHERE id = $1",
                    request.release)
                if owner != name:
                    raise StageRefused(f"REFUSING: Qdrant collection '{name}' exists and "
                                       f"belongs to no earlier stage of '{request.release}'")

            at = datetime.now(timezone.utc)
            async with conn.transaction():
                # Live rows still filed under an old key of a staged collection are
                # part of it (5.1b.3): compared by ID, never retired for the rename.
                live_scope = collection_keys.live_keys(collections)
                await refuse_moves_out_of_scope(conn, documents, live_scope)
                await begin_publish(conn, request.release, collections, name)
                await reader_writer.ensure_staging(conn)
                await reader_writer.clear_staged_collections(conn, live_scope)
                for d in documents:
                    await reader_writer.write_staged_document(conn, d)
                await reader_writer.copy_live_annotations(conn, collections)
                live_passages, live_documents = await live_rows(conn, live_scope)
                found = retirements.compute(
                    live_passages, live_documents, documents, registry,
                    release=request.release, at=at,
                    live_anchor_redirects=await live_anchor_redirects(conn))
                if found.problems:
                    raise StageRefused(
                        f"REFUSING: {len(found.problems)} live IDs the build drops are "
                        "unexplained (D4): " + "; ".join(found.problems[:10]))
                await reader_writer.write_staged_retirements(conn, found.tombstones,
                                                             found.redirects)
                publish_collections = (await conn.fetchval(
                    "SELECT collections FROM corpus_publishes WHERE id = $1",
                    request.release))

            # Qdrant: the publish's own collection, never one users search.
            if exists:
                await qd.check_vectors(client, name)
            else:
                await create_chunks_collection(client, name)
            for c in collections:
                await qd.clear_staged_points(client, name, c, alias=alias)
            vectors = VectorSource(client, self._cache(), reuse_from=live, embed=self._embed)
            for d in documents:
                await write_document(client, d, collection_name=name, vectors=vectors)

            # Every collection not staged keeps its live points, under the key they are
            # stored with: until 5.1b.3's publish, that is the old key. The old keys of a
            # staged collection are staged with it, so none of their points is copied.
            copied = {}
            unstaged = sorted(set(self._source_adapters) - set(publish_collections))
            for c in collection_keys.live_keys(unstaged):
                if collection_keys.canonical(c) in publish_collections:
                    continue
                # Always copied afresh: a count alone cannot show that live changed.
                copied[c] = await qd.count_points(client, live, c)
                await qd.clear_staged_points(client, name, c, alias=alias)
                await qd.copy_points(client, live, name, c)

            await check_point_counts(conn, client, name, publish_collections, copied)
            await conn.execute(
                """UPDATE corpus_publishes SET staged_at = now(), embed_model = $2,
                   embed_dimensions = $3 WHERE id = $1""",
                request.release, vectors.model, vectors.dimensions)
        finally:
            await conn.close()
            await client.close()

        kinds: dict[str, int] = {}
        for r in found.redirects:
            kinds[r["entity"]] = kinds.get(r["entity"], 0) + 1
        return StageResult(
            release=request.release, qdrant_collection=name, documents=len(documents),
            passages=sum(len(d.passages) for d in documents), new_ids=new_ids,
            tombstones=len(found.tombstones), redirects=kinds, moved=len(found.moved),
            copied=copied, vectors=dict(vectors.counts))


async def refuse_moves_out_of_scope(conn: asyncpg.Connection, documents: list[Document],
                                    live_scope: list[str]) -> None:
    """Refuse a build that holds a document live files under a collection this stage
    does not cover. Its live rows would not be compared, so it would look new here and
    unexplained to the next publish of its live collection. 5.1b.3 moves Boethius from
    the medieval collection to the Fathers: until that publish is applied, stage
    `church-fathers` with `theologians`."""
    elsewhere = await conn.fetch(
        """SELECT id::text AS id, collection, title FROM public.documents
           WHERE id = ANY($1::uuid[]) AND retired_at IS NULL
             AND NOT (collection = ANY($2::text[]))""",
        [d.id for d in documents], live_scope)
    if elsewhere:
        where = "; ".join(f"{r['title']!r} is live in {r['collection']!r}" for r in elsewhere[:5])
        needed = sorted({collection_keys.canonical(r["collection"]) for r in elsewhere})
        raise StageRefused(f"REFUSING: the build moves {len(elsewhere)} live documents from a "
                           f"collection this stage does not cover ({where}); stage "
                           f"{', '.join(needed)} with it")


async def check_point_counts(conn: asyncpg.Connection, client, name: str,
                             staged: list[str], copied: dict[str, int]) -> None:
    """Stage step 7: each staged collection's points equal its staged passages, each
    copied collection's equal its source count, and the total is their sum."""
    from writers.qdrant import count_points

    problems = []
    total = 0
    for c in staged:
        want = await conn.fetchval(
            """SELECT count(*) FROM staging.chunks s JOIN staging.documents d
               ON d.id = s.document_id WHERE d.collection = $1""", c)
        got = await count_points(client, name, c)
        total += want
        if got != want:
            problems.append(f"{c}: {got} points, {want} staged passages")
    for c, want in copied.items():
        got = await count_points(client, name, c)
        total += want
        if got != want:
            problems.append(f"{c}: {got} points, {want} in the collection users search")
    got = await count_points(client, name)
    if got != total:
        problems.append(f"total: {got} points, expected {total}")
    if problems:
        raise StageRefused("REFUSING: point counts do not match: " + "; ".join(problems))


# --------------------------------------------------------------------------- production

def publish_lock_guard(step: str, lock_path=None) -> Callable[[str, str], None]:
    """Refuse unless PUBLISH_LOCK.json approves `step` for the collection and release
    (item 0.4); local rehearsals pass by the lock's loopback rule."""
    from publish_lock import DEFAULT_PATH, assert_live_write_allowed, load_lock

    def guard(collection: str, release: str) -> None:
        assert_live_write_allowed(f"publish {step} {collection}", collection, release, step,
                                  lock=load_lock(lock_path or DEFAULT_PATH))

    return guard


def production_stage_runner(lock_path=None) -> StageRunner:
    from cache import Cache
    from config import settings
    from writers.qdrant import get_client

    async def connect():
        # statement_cache_size=0: the Supabase pooler does not keep prepared statements.
        return await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)

    def cache():
        c = Cache(CACHE_PATH)
        c.init_schema()
        return c

    return StageRunner(connect=connect, qdrant=get_client, cache=cache,
                       write_guard=publish_lock_guard("stage", lock_path))

