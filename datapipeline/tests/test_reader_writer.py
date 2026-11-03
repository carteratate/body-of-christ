"""The staging writer's rows and the search writer's vector shape (2.2w).

The staging writer itself runs against a local PostgreSQL in test_stage_apply.py.
"""
import asyncio

from model import Document
from writers import reader_writer


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
        asyncio.run(qdrant_writer.check_vectors(FakeClient(), "chunks-r1"))

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
        asyncio.run(qdrant_writer.check_vectors(FakeClient(), "chunks-r1"))

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

    asyncio.run(qdrant_writer.check_vectors(FakeClient(), "chunks-r1"))


def _document_access(doc):
    """The reader_access the staging writer writes for `doc` (D12)."""
    return reader_writer.document_row(doc)[reader_writer.DOCUMENT_COLUMNS.index("reader_access")]


def test_the_staged_row_sets_reader_access_from_the_rights_inventory():
    """Issue #265: a publish writes the inventory's verdict, so it cannot reopen a text
    whose rights are not cleared, and keeps a public-domain one open. Rows are found by
    document ID, so a relabelled document keeps its row."""
    bible = Document(id="69468535-a61e-50c7-a341-e18b1dc1d1c6", collection="bible",
                     title="John (relabelled)", translation="WEB-C", passages=[])
    catechism = Document(id="9679c400-d314-5394-b916-f6fc27b50104", collection="catechism",
                         title="Catechism of the Catholic Church", author="Catholic Church",
                         passages=[])
    assert _document_access(bible) == "full"
    assert _document_access(catechism) == "excerpt"


def test_the_staged_row_fails_closed_for_a_work_missing_from_the_inventory():
    # A known title under an ID the inventory does not list.
    stray = Document(id="33333333-3333-3333-3333-333333333333", collection="bible",
                     title="John", translation="WEB-C", passages=[])
    assert _document_access(stray) == "excerpt"
