"""Tests for collection_guarantee — injects a per-collection result and keeps
the list score-sorted (quota_cap and the streamed/persisted order depend on it).
The slot is per collection, never per genre (corpus cleanup 5.1c)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.rag import qdrant_client
from app.rag.search_plan import resolve_search_plan
from app.rag.steps import retrieve_vector
from app.rag.steps.collection_guarantee import run as guarantee
from app.rag.steps.types import RankedChunk


def _rc(cid: str, collection: str, score: float) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid,
        content="content",
        reference="ref",
        collection=collection,
        document_id=cid,
        document_title="title",
        author=None,
        reranker_score=score,
    )


def test_injects_absent_collection_and_resorts():
    """An injected chunk must be merged in score order, not appended last."""
    deduped = [_rc("a", "bible", 0.9), _rc("b", "bible", 0.3)]
    all_scored = [
        _rc("a", "bible", 0.9),
        _rc("c", "catechism", 0.8),  # absent collection, high score
        _rc("b", "bible", 0.3),
    ]
    result = guarantee(deduped, all_scored, ["bible", "catechism"])

    scores = [r.reranker_score for r in result]
    assert scores == sorted(scores, reverse=True), "result must stay score-descending"
    # 0.8 catechism chunk must sit between the 0.9 and 0.3 bible chunks, not at the end
    assert [r.chunk_id for r in result] == ["a", "c", "b"]


def test_noop_when_all_collections_represented():
    deduped = [_rc("a", "bible", 0.9), _rc("c", "catechism", 0.8)]
    result = guarantee(deduped, list(deduped), ["bible", "catechism"])
    assert [r.chunk_id for r in result] == ["a", "c"]


def test_skips_injection_below_min_score():
    """A collection whose best candidate is below the 0.25 floor is not injected."""
    deduped = [_rc("a", "bible", 0.9)]
    all_scored = [_rc("a", "bible", 0.9), _rc("c", "catechism", 0.1)]
    result = guarantee(deduped, all_scored, ["bible", "catechism"])
    assert [r.chunk_id for r in result] == ["a"]


# --- One slot per collection, never per genre (corpus cleanup 5.1c) -------------------
#
# A genre selection (5.1a) narrows a collection at retrieval; the guarantee keys on
# the collection alone. These run the real runner over an in-memory Qdrant, so the
# candidates the guarantee chooses from are filtered by the plan's scopes exactly as
# in production. Rerank is stubbed: it scores each document by SCORES and ranks only
# RANKED, so a collection outside RANKED is absent after dedup and needs its slot.

THREE_GENRES = ["encyclical", "apostolic-letter", "apostolic-constitution"]

# document_id -> (collection, genre)
DOCUMENTS = {
    "enc-encyclical": ("encyclicals", "encyclical"),
    "enc-letter": ("encyclicals", "apostolic-letter"),
    "enc-constitution": ("encyclicals", "apostolic-constitution"),
    "enc-motu-proprio": ("encyclicals", "motu-proprio"),
    "enc-exhortation": ("encyclicals", "apostolic-exhortation"),
    "pd-letter": ("papal-documents", "apostolic-letter"),
    "pd-motu-proprio": ("papal-documents", "motu-proprio"),
    "ccc-1": ("catechism", None),
    "ccc-2": ("catechism", None),
}
# Every candidate clears guarantee_min_score, and the excluded genres score highest,
# so a leaked one would be the passage the guarantee picks.
SCORES = {
    "enc-motu-proprio": 0.99, "enc-exhortation": 0.98,
    "enc-encyclical": 0.70, "enc-letter": 0.65, "enc-constitution": 0.60,
    "pd-motu-proprio": 0.97, "pd-letter": 0.55,
    "ccc-1": 0.90, "ccc-2": 0.85,
}


@pytest.fixture()
async def corpus(monkeypatch):
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("chunks", vectors_config=VectorParams(
        size=4, distance=Distance.COSINE))
    points = []
    for n, (doc, (collection, genre)) in enumerate(DOCUMENTS.items(), start=1):
        payload = {"collection": collection, "document_id": doc,
                   "document_title": doc, "content": f"passage of {doc}"}
        if genre is not None:
            payload.update(genre=genre, issuer="pope-leo-xiii")
        points.append(PointStruct(id=str(uuid.UUID(int=n)),
                                  vector=[1.0, 0.0, 0.0, 0.0], payload=payload))
    await client.upsert("chunks", points=points, wait=True)
    monkeypatch.setattr(settings, "qdrant_read_collection", "chunks")
    monkeypatch.setattr(qdrant_client, "_searchable_indexed", False)
    monkeypatch.setattr(qdrant_client, "_searchable_checked_at", float("inf"))
    with patch.object(retrieve_vector, "get_qdrant_client", return_value=client):
        yield client
    await client.close()


async def _search(collections: list[str], quota: int, scopes: dict | None,
                  ranked_docs: set[str]) -> tuple[list[RankedChunk], list[RankedChunk]]:
    """The runner's final results and the scored pool the guarantee chose from."""
    from app.rag.pipelines import runner
    from app.rag.pipelines.registry import PIPELINES

    pool: list[RankedChunk] = []

    async def rerank(_config, candidates, _query, _quota, _tracker):
        scored = sorted(
            (
                RankedChunk(
                    chunk_id=c.chunk_id, content=c.content, reference=c.reference,
                    collection=c.collection, document_id=c.document_id,
                    document_title=c.document_title, author=c.author,
                    reranker_score=SCORES[c.document_id],
                )
                for chunks in candidates.values() for c in chunks
            ),
            key=lambda r: r.reranker_score, reverse=True,
        )
        pool.extend(scored)
        return [r for r in scored if r.document_id in ranked_docs], scored

    plan = resolve_search_plan(collections, quota, scopes)
    with (
        patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])),
        patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_fts.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.fetch_positions.run", new=AsyncMock(side_effect=lambda c: c)),
        patch("app.rag.steps.rerank.run", new=rerank),
    ):
        result = await runner.run(PIPELINES["hyde_cohere_luna_seats10t80_ftsminmatch"],
                                  "grace", collections, quota, search_plan=plan)
    return result.chunks, pool


def _genre(chunk: RankedChunk) -> str | None:
    return DOCUMENTS[chunk.document_id][1]


async def test_three_genres_in_one_collection_get_one_slot(corpus):
    """Each selected genre has an above-threshold candidate; still one injected passage."""
    final, pool = await _search(
        ["encyclicals"], 4, {"encyclicals": {"genres": THREE_GENRES}}, ranked_docs=set())

    assert {_genre(c) for c in pool} == set(THREE_GENRES), "every selected genre was a candidate"
    assert [c.document_id for c in final] == ["enc-encyclical"]


async def test_an_injected_passage_never_has_an_excluded_genre(corpus):
    """The excluded genres score highest in the corpus, and none is injected."""
    final, pool = await _search(
        ["encyclicals", "papal-documents", "catechism"], 5,
        {"encyclicals": {"genres": THREE_GENRES},
         "papal-documents": {"genres": ["apostolic-letter"]}},
        ranked_docs={"ccc-1", "ccc-2"},
    )

    assert {c.document_id for c in pool}.isdisjoint(
        {"enc-motu-proprio", "enc-exhortation", "pd-motu-proprio"})
    injected = [c for c in final if c.collection != "catechism"]
    assert [c.document_id for c in injected] == ["enc-encyclical", "pd-letter"]
    assert _genre(injected[0]) in THREE_GENRES
    assert _genre(injected[1]) == "apostolic-letter"


async def test_several_collections_get_one_slot_each(corpus):
    """Two absent collections with several candidates each gain one slot apiece; the
    represented one gains none."""
    final, _ = await _search(
        ["encyclicals", "papal-documents", "catechism"], 5, None,
        ranked_docs={"ccc-1", "ccc-2"},
    )

    by_collection: dict[str, int] = {}
    for c in final:
        by_collection[c.collection] = by_collection.get(c.collection, 0) + 1
    assert by_collection == {"catechism": 2, "encyclicals": 1, "papal-documents": 1}
    # Unscoped, the guarantee takes each collection's best, whatever its genre.
    assert {c.document_id for c in final} == {
        "ccc-1", "ccc-2", "enc-motu-proprio", "pd-motu-proprio"}
