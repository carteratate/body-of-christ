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
