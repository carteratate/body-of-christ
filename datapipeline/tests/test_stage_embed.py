import pytest
from model import Document, Passage
from cache import Cache
from stages.embed import content_embedding_input, embed_chunk, EmbedDeps


class _StubEmbed:
    def __init__(self): self.calls = 0
    async def embed(self, texts):
        self.calls += 1
        return [[float(len(t))] * 1 for t in texts]  # deterministic, 1-dim for test


def _doc():
    ps = [Passage(content=f"content {i}", reference=f"r{i}", anchor=f"a{i}",
                  chapter_key="c", chapter_label="Chap", position=i) for i in range(2)]
    return Document(id="d1", collection="summa", title="Summa", author="Aquinas", passages=ps)


def test_content_input_has_prefix():
    doc = _doc()
    s = content_embedding_input(doc.passages, 0, doc)
    assert s.startswith("Aquinas — Summa, Chap")
    assert "content 0" in s


def test_content_input_no_author():
    ps = [Passage(content=f"content {i}", reference=f"r{i}", anchor=f"a{i}",
                  chapter_key="c", chapter_label="Chap", position=i) for i in range(2)]
    doc = Document(id="d1", collection="summa", title="Summa", author=None, passages=ps)
    s = content_embedding_input(doc.passages, 0, doc)
    assert s.startswith("Summa, Chap ")
    assert not s.startswith(" —")
    assert "  " not in s  # no double-spaces
    assert "content 0" in s


@pytest.mark.asyncio
async def test_embed_chunk_embeds_content_facets_questions(tmp_path):
    doc = _doc()
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    chunk_points, facet_points, question_points = [], [], []

    async def _upsert_chunk_point(pt):
        chunk_points.append(pt)

    async def _upsert_points_named(col, pts):
        (facet_points if col == "facets" else question_points).extend(pts)

    deps = EmbedDeps(
        cache=cache, embed_client=_StubEmbed(), qdrant=None,
        upsert_chunk_point=_upsert_chunk_point,
        upsert_points_named=_upsert_points_named,
    )
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?"},
              {"grounding": "settled", "evidence": "e1", "kind": "moral", "kind_secondary": "devotional",
               "text": "facet B", "question": "Q B?"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert len(chunk_points) == 1
    assert chunk_points[0].vector.keys() == {"dense"}     # named vector
    assert len(facet_points) == 2 and len(question_points) == 2
    assert facet_points[0].payload["kind"] == "doctrinal"
    assert facet_points[0].payload["grounding"] == "explicit"
    assert facet_points[0].payload["evidence"] == "e0"
    assert facet_points[1].payload["kind_secondary"] == "devotional"
    assert facet_points[0].payload["working_text"] is None  # not in PILOT_MODE
    assert question_points[0].payload["question"] == "Q A?"
    assert question_points[0].payload["facet_grounding"] == "explicit"
    assert question_points[1].payload["facet_kind_secondary"] == "devotional"
    # second run hits cache -> no new embed calls beyond first
    calls_after = deps.embed_client.calls
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert deps.embed_client.calls == calls_after


@pytest.mark.asyncio
async def test_embed_chunk_carries_working_text_when_present(tmp_path):
    doc = _doc()
    cache = Cache(str(tmp_path / "c.db")); cache.init_schema()
    facet_points = []

    async def _upsert_chunk_point(pt): pass

    async def _upsert_points_named(col, pts):
        if col == "facets":
            facet_points.extend(pts)

    deps = EmbedDeps(cache=cache, embed_client=_StubEmbed(), qdrant=None,
                     upsert_chunk_point=_upsert_chunk_point,
                     upsert_points_named=_upsert_points_named)
    merged = [{"grounding": "explicit", "evidence": "e0", "kind": "doctrinal", "kind_secondary": None,
               "text": "facet A", "question": "Q A?", "working_text": "the raw working treatment"}]
    await embed_chunk(doc, doc.passages, 0, merged, deps)
    assert facet_points[0].payload["working_text"] == "the raw working treatment"
