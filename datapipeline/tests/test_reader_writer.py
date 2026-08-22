import asyncio
from model import Passage, Document
from writers import reader_writer


class FakeConn:
    def __init__(self):
        self.calls = []
        self.fetchval_result = None
    async def execute(self, sql, *args):
        self.calls.append((sql, args))
    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return self.fetchval_result


class FakePool:
    def __init__(self, conn): self._c = conn
    def acquire(self):
        pool = self
        class _Ctx:
            async def __aenter__(self): return pool._c
            async def __aexit__(self, *a): return False
        return _Ctx()


def test_write_document_inserts_doc_and_passages():
    conn = FakeConn()
    pool = FakePool(conn)
    doc = Document(
        id="11111111-1111-1111-1111-111111111111", collection="bible",
        title="John", translation="WEB-C",
        passages=[Passage(content="x", reference="John 3:16", anchor="john/3/16",
                          chapter_key="john/3", chapter_label="John 3", position=0,
                          unit_label="16")],
    )
    asyncio.run(reader_writer.write_document(pool, doc))
    joined = " ".join(sql for sql, _ in conn.calls)
    assert "INSERT INTO documents" in joined
    assert "INSERT INTO chunks" in joined
    chunk_args = [args for sql, args in conn.calls if "INSERT INTO chunks" in sql][0]
    assert "john/3/16" in chunk_args
    assert "john/3" in chunk_args


# ---------------------------------------------------------------------------
# Re-ingest must not destroy user data.
#
# `retrievals`, `bookmarks`, `reading_progress`, `chunk_feedback` and
# `guest_trial_retrievals` all reference `chunks.id` ON DELETE CASCADE. A rebuild
# produces byte-identical ids for anything it still emits, so deleting first throws
# away user data the re-insert cannot restore.
# ---------------------------------------------------------------------------

def _doc(*anchors):
    return Document(
        id="11111111-1111-1111-1111-111111111111", collection="medieval",
        title="On Loving God", translation="",
        passages=[Passage(content="x", reference="r", anchor=a, chapter_key="k",
                          chapter_label="l", position=i, unit_label=None)
                  for i, a in enumerate(anchors)],
    )


def test_prune_keeps_every_chunk_the_build_still_produces():
    """Only genuinely orphaned rows may be deleted — everything else keeps its id, and
    with it its bookmarks and search history."""
    from identity import passage_id

    conn = FakeConn()
    conn.fetchval_result = 0
    doc = _doc("a/1", "a/2")

    asyncio.run(reader_writer.prune_missing_chunks(conn, doc))

    sql, args = conn.calls[-1]
    assert "DELETE FROM chunks" in sql
    assert "NOT (id = ANY" in sql
    assert set(args[1]) == {passage_id(doc.id, "a/1"), passage_id(doc.id, "a/2")}


def test_prune_is_scoped_to_one_document():
    """A collection-wide delete would take other documents' chunks with it."""
    conn = FakeConn()
    conn.fetchval_result = 0
    asyncio.run(reader_writer.prune_missing_chunks(conn, _doc("a/1")))

    sql, args = conn.calls[-1]
    assert "document_id = $1" in sql
    assert args[0] == "11111111-1111-1111-1111-111111111111"


def test_reingest_does_not_wipe_the_reader_by_default():
    """The destructive path must be opt-in. Defaulting to it means an ordinary re-ingest
    silently cascades through user data."""
    import inspect

    import run_collection

    source = inspect.getsource(run_collection.run)
    body = source[source.index('if target in ("reader"'):]
    assert "if wipe:" in body
    assert "prune_missing_chunks" in body


def test_wipe_is_reachable_but_named_for_what_it_does():
    import inspect

    import run_collection

    assert "wipe" in inspect.signature(run_collection.run).parameters
    source = inspect.getsource(run_collection)
    assert "--wipe-reader" in source
    assert "cascade" in source.lower()


# ---------------------------------------------------------------------------
# Qdrant orphans and the collapse guard.
# ---------------------------------------------------------------------------

def test_qdrant_prune_deletes_only_points_the_build_no_longer_makes():
    """`search_writer.write_document` only upserts, so a renumbered or dropped passage
    leaves its point behind — still searchable, while the pipeline's Postgres lookup for
    that id returns nothing."""
    from writers import qdrant as qdrant_writer

    class FakePoint:
        def __init__(self, pid): self.id = pid

    class FakeQdrant:
        def __init__(self): self.deleted = None
        async def scroll(self, **kw):
            return [FakePoint("keep-1"), FakePoint("stale-1"), FakePoint("keep-2")], None
        async def delete(self, collection_name, points_selector, wait):
            self.deleted = points_selector

    client = FakeQdrant()
    removed = asyncio.run(
        qdrant_writer.prune_missing_points(client, "medieval", {"keep-1", "keep-2"}))

    assert removed == 1
    assert client.deleted == ["stale-1"]


def test_qdrant_prune_deletes_nothing_when_the_build_is_complete():
    from writers import qdrant as qdrant_writer

    class FakePoint:
        def __init__(self, pid): self.id = pid

    class FakeQdrant:
        def __init__(self): self.delete_called = False
        async def scroll(self, **kw):
            return [FakePoint("a"), FakePoint("b")], None
        async def delete(self, **kw):
            self.delete_called = True

    client = FakeQdrant()
    assert asyncio.run(qdrant_writer.prune_missing_points(client, "medieval", {"a", "b"})) == 0
    assert client.delete_called is False


def test_a_collapsed_build_is_refused_before_anything_is_written():
    """Pruning to match a broken build would delete the difference from both stores. The
    check runs before the first write, not after."""
    import pytest

    import run_collection

    class FakeConn:
        async def fetchval(self, sql, *args): return 1000

    with pytest.raises(SystemExit) as raised:
        asyncio.run(run_collection._refuse_if_build_collapsed(FakeConn(), "medieval", 500, None))

    assert "REFUSING" in str(raised.value)


def test_the_collapse_guard_runs_before_the_first_write():
    """A guard that fires after the writes have started is not a guard: by then the
    prune has already deleted rows and points."""
    import inspect

    import run_collection

    source = inspect.getsource(run_collection.run)
    guard = source.index("_refuse_if_build_collapsed")
    for writer in ("write_document", "prune_missing_chunks", "prune_missing_points",
                   "clear_collection"):
        assert guard < source.index(writer), f"{writer} runs before the guard"


def test_a_normal_rebuild_is_allowed_through():
    import run_collection

    class FakeConn:
        async def fetchval(self, sql, *args): return 434

    # 437 built against 434 live — the medieval rebuild's real shape.
    asyncio.run(run_collection._refuse_if_build_collapsed(FakeConn(), "medieval", 437, None))


def test_a_deliberate_partial_build_skips_the_check():
    import run_collection

    class FakeConn:
        async def fetchval(self, sql, *args):
            raise AssertionError("should not query when --limit is set")

    asyncio.run(run_collection._refuse_if_build_collapsed(FakeConn(), "medieval", 5, 5))


# ---------------------------------------------------------------------------
# The writer must produce what the deployed collection holds.
#
# Its absence is how the corpus and the code drifted apart: the writer was retargeted
# at the V5 schema (3072-dim named vectors) while the deployed collection stayed at
# 1536 unnamed, and nothing compared them until an ingest was attempted.
# ---------------------------------------------------------------------------

def test_the_writer_emits_an_unnamed_vector():
    """`services/api` queries without `using=`, so a named vector is unreachable."""
    from model import Document, Passage
    from writers.search_writer import build_point

    doc = Document(id="11111111-1111-1111-1111-111111111111", collection="medieval",
                   title="T", translation="", passages=[])
    passage = Passage(content="x", reference="r", anchor="a/1", chapter_key="k",
                      chapter_label="l", position=0, unit_label=None)

    point = build_point(doc, passage, [0.0] * 1536)

    assert isinstance(point.vector, list)


def test_the_writer_dimension_matches_what_the_api_queries():
    """The API sends 1536-dim query vectors. A corpus embedded at any other width cannot
    be searched at all."""
    from config import settings

    assert settings.EMBEDDING_DIMS == 1536


def test_the_embedding_call_pins_the_dimension():
    """text-embedding-3-large is natively 3072; omitting `dimensions=` silently yields
    vectors the live collection cannot store."""
    import inspect

    from writers import search_writer

    source = inspect.getsource(search_writer._embed)
    assert "dimensions=settings.EMBEDDING_DIMS" in source


def test_a_collection_the_writer_cannot_fill_is_refused():
    """Reshaping a live collection deletes every vector in it. An ingest run must not
    decide that as a side effect."""
    import pytest

    from writers import qdrant as qdrant_writer

    class V5Collection:
        class config:
            class params:
                from qdrant_client.models import VectorParams, Distance
                vectors = {"dense": VectorParams(size=3072, distance=Distance.COSINE)}

    class FakeClient:
        async def collection_exists(self, name): return True
        async def get_collection(self, name): return V5Collection()

    with pytest.raises(SystemExit) as raised:
        asyncio.run(qdrant_writer.ensure_collection(FakeClient()))

    assert "REFUSING" in str(raised.value)


def test_a_dimension_mismatch_alone_is_refused():
    """The two axes fail independently: an unnamed collection at the wrong width is just
    as unwritable as a named one, and is the likelier drift — a config change moves the
    dimension without touching the vector's shape."""
    import pytest
    from qdrant_client.models import Distance, VectorParams

    from writers import qdrant as qdrant_writer

    class WrongWidth:
        class config:
            class params:
                vectors = VectorParams(size=3072, distance=Distance.COSINE)

    class FakeClient:
        async def collection_exists(self, name): return True
        async def get_collection(self, name): return WrongWidth()

    with pytest.raises(SystemExit) as raised:
        asyncio.run(qdrant_writer.ensure_collection(FakeClient()))

    assert "3072" in str(raised.value)


def test_a_matching_collection_is_accepted():
    from qdrant_client.models import Distance, VectorParams

    from writers import qdrant as qdrant_writer

    class LiveCollection:
        class config:
            class params:
                vectors = VectorParams(size=1536, distance=Distance.COSINE)

    class FakeClient:
        async def collection_exists(self, name): return True
        async def get_collection(self, name): return LiveCollection()

    asyncio.run(qdrant_writer.ensure_collection(FakeClient()))
