import asyncio
from model import Passage, Document
from writers import reader_writer


class FakeConn:
    def __init__(self):
        self.calls = []
    async def execute(self, sql, *args):
        self.calls.append((sql, args))
    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return None


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
