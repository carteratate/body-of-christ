from model import Passage, Document
from writers.search_writer import build_embedding_input, build_point


def _p(pos, content, anchor):
    return Passage(content=content, reference=f"r{pos}", anchor=anchor,
                   chapter_key="john/3", chapter_label="John 3", position=pos)


def test_embedding_input_adds_neighbor_context_within_chapter():
    ps = [_p(0, "Aaa.", "john/3/1"), _p(1, "Bbb.", "john/3/2"), _p(2, "Ccc.", "john/3/3")]
    out = build_embedding_input(ps, 1, k_prev=10, k_next=10, prefix="[John 3] ")
    assert out.startswith("[John 3] ")
    assert "Bbb." in out and "Aaa." in out and "Ccc." in out


def test_embedding_input_does_not_cross_chapter():
    a = _p(0, "Aaa.", "john/3/1")
    b = Passage(content="Bbb.", reference="r", anchor="john/4/1",
                chapter_key="john/4", chapter_label="John 4", position=1)
    out = build_embedding_input([a, b], 1, k_prev=50, k_next=50, prefix="")
    assert "Aaa." not in out  # previous passage is a different chapter


def test_build_point_uses_a_bare_vector_for_the_deployed_collection():
    """services/api queries without `using=`, so a named vector is unreachable there."""
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses")
    p = Passage(content="x", reference="Gen 1:1", anchor="genesis/1/1",
                chapter_key="genesis/1", chapter_label="Genesis 1", position=0)

    pt = build_point(doc, p, [0.1, 0.2, 0.3])

    assert pt.vector == [0.1, 0.2, 0.3]
    assert pt.payload["collection"] == "bible"
    assert pt.payload["content"] == "x"


def test_build_point_carries_the_fields_the_pipeline_reads():
    """`reconcile_qdrant_payloads` added chapter_key and unit_label to 53,747 live points
    because this writer omitted them — so re-ingesting a collection silently undid that
    repair, which is exactly what the canon-law run did.

    `fetch_positions` backfills both from Postgres, but only on the healthy path: it is
    skipped when the pipeline degrades, and `unit_label` is what tells the reranker a
    Summa passage is an objection Aquinas refutes rather than his own teaching.
    """
    doc = Document(id="d1", collection="summa", title="Summa", author="Aquinas")
    p = Passage(content="x", reference="ST I q1 a1", anchor="summa/q1/a1/0",
                chapter_key="summa/q1/a1", chapter_label="Q1 A1", position=0,
                unit_label="Objection 1")

    payload = build_point(doc, p, [0.1]).payload

    assert payload["chapter_key"] == "summa/q1/a1"
    assert payload["unit_label"] == "Objection 1"


# --------------------------------------------------------------------------- 2.2w

from model import Work  # noqa: E402
from writers import search_writer  # noqa: E402


def test_neighbour_window_skips_unsearchable():
    """C-21 (index.no_unsearchable_neighbour_text): a current passage between a history
    passage and a Latin canon is embedded with neither's text, and takes the nearest
    searchable neighbour in its chapter instead."""
    history = _p(1, "OLD TEXT 1983", "c/1/history-1983")
    history.searchable = False
    latin = _p(3, "CANON LATINE", "c/2")
    latin.searchable = False
    ps = [_p(0, "Before.", "c/0"), history, _p(2, "Current.", "c/1"), latin,
          _p(4, "After.", "c/3")]
    out = build_embedding_input(ps, 2, k_prev=50, k_next=50, prefix="")
    assert "OLD TEXT" not in out and "LATINE" not in out
    assert out == "Before. Current. After."
    alone = build_embedding_input([history, _p(2, "Current.", "c/1"), latin], 1,
                                  k_prev=50, k_next=50, prefix="")
    assert alone == "Current."


def test_embedding_prefix_uses_display_author():
    """C-15: a passage whose work is credited to Firmilian is embedded, and shown, with
    "Firmilian", not the document author."""
    doc = Document(id="d1", collection="church-fathers", title="Epistles", author="Cyprian",
                   works=[Work(work_key="ep-74", ordinal=1, title="Letter 74",
                               author="Firmilian")])
    p = Passage(content="x", reference="r", anchor="a", chapter_key="k", chapter_label="L",
                position=0, work_key="ep-74")
    assert search_writer.embedding_prefix(doc, p) == "Firmilian — Epistles, L"
    assert build_point(doc, p, [0.1]).payload["author"] == "Firmilian"
    p.passage_author = "Chrysostom"
    assert search_writer.display_author(doc, p) == "Chrysostom"
    p.passage_author, p.work_key = None, None
    assert search_writer.embedding_prefix(doc, p) == "Cyprian — Epistles, L"


def test_voice_and_facts_reach_the_payload():
    doc = Document(id="d1", collection="summa", title="Summa", author="Aquinas",
                   genre="treatise", issuer="thomas-aquinas")
    p = Passage(content="x", reference="r", anchor="a", chapter_key="k", chapter_label="L",
                position=0, voice="rejected", searchable=False, id="p1")
    payload = build_point(doc, p, [0.1], embed_sha256="abc", embed_model="m").payload
    assert (payload["genre"], payload["issuer"], payload["searchable"], payload["voice"],
            payload["embed_sha256"], payload["embed_model"]) == \
        ("treatise", "thomas-aquinas", False, "rejected", "abc", "m")
    assert build_point(doc, p, [0.1]).id == "p1"


class _Cache:
    def __init__(self):
        self.rows, self.log = {}, []

    def get_embedding(self, h, model, dims):
        return self.rows.get((h, model, dims))

    def put_embedding(self, h, model, dims, vector):
        self.log.append(("put", h))
        self.rows[(h, model, dims)] = list(vector)


async def test_embedding_cache_hit_skips_openai():
    cache = _Cache()
    cache.put_embedding(search_writer.input_sha256("text"), "m", 2, [1.0, 0.0])
    calls = []

    async def embed(texts):
        calls.append(texts)
        return [[0.0, 1.0] for _ in texts]
    source = search_writer.VectorSource(None, cache, reuse_from=None, embed=embed,
                                        model="m", dimensions=2)
    assert await source.vectors(["p1"], ["text"]) == [[1.0, 0.0]]
    assert calls == [] and source.counts["cache"] == 1


async def test_cache_miss_is_written_to_cache_before_upsert():
    """An interrupted stage never pays twice: the vector is in the cache before the
    point is written."""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, VectorParams

    cache = _Cache()
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("chunks-r1", vectors_config=VectorParams(
        size=2, distance=Distance.COSINE))
    order = []

    async def embed(texts):
        return [[0.0, 1.0] for _ in texts]
    original = client.upsert

    async def upsert(**kwargs):
        order.append(("upsert", list(cache.log)))
        return await original(**kwargs)
    client.upsert = upsert
    doc = Document(id="d1", collection="medieval", title="T",
                   passages=[Passage(content="x", reference="r", anchor="a", chapter_key="k",
                                     chapter_label="L", position=0, id="00000000-0000-0000-0000-000000000001")])
    source = search_writer.VectorSource(client, cache, reuse_from=None, embed=embed,
                                        model="m", dimensions=2)
    await search_writer.write_document(client, doc, collection_name="chunks-r1",
                                       vectors=source)
    [(_, puts_before_upsert)] = order
    assert puts_before_upsert == [("put", search_writer.input_sha256(
        search_writer.embedding_inputs(doc)[0]))]
    assert source.counts["embedded"] == 1


async def test_unchanged_passage_copies_its_vector():
    """No embedding call for a passage whose live point has the same `embed_sha256`
    and model; the reused vector also fills the cache."""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("live", vectors_config=VectorParams(
        size=2, distance=Distance.COSINE))
    pid = "00000000-0000-0000-0000-000000000001"
    h = search_writer.input_sha256("text")
    await client.upsert("live", points=[PointStruct(id=pid, vector=[0.6, 0.8], payload={
        "embed_sha256": h, "embed_model": "m"})])

    async def embed(texts):
        raise AssertionError("no embedding call")
    cache = _Cache()
    source = search_writer.VectorSource(client, cache, reuse_from="live", embed=embed,
                                        model="m", dimensions=2)
    [vector] = await source.vectors([pid], ["text"])
    assert [round(x, 3) for x in vector] == [0.6, 0.8]
    assert source.counts["reused"] == 1 and cache.get_embedding(h, "m", 2) is not None
    # A different input or model does not reuse it.
    source.embed = lambda texts: _vectors(texts)
    await source.vectors([pid], ["changed"])
    assert source.counts["embedded"] == 1


async def _vectors(texts):
    return [[1.0, 0.0] for _ in texts]
