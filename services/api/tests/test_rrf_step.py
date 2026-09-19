import pytest
from app.config import Settings, settings
from app.rag.steps import rrf
from app.rag.steps.types import ChunkCandidate, RetrievalPath


def _make_row(chunk_id: str, content: str = "x") -> dict:
    return {
        "id": chunk_id,
        "content": content,
        "reference": None,
        "collection": "bible",
        "document_id": "doc1",
        "document_title": "Title",
        "author": None,
        "anchor": None,
        "position": None,
        "annotation": None,
    }


def test_rrf_shared_chunk_gets_higher_score():
    chunk_id = "00000000-0000-0000-0000-000000000001"
    vector_results = {"bible": [RetrievalPath("hyde", [_make_row(chunk_id)])]}
    fts_results = {"bible": [_make_row(chunk_id)]}
    merged = rrf.run(vector_results, fts_results, quota=4)
    assert "bible" in merged
    assert len(merged["bible"]) == 1
    assert merged["bible"][0].chunk_id == chunk_id
    assert merged["bible"][0].rrf_score > 1 / (settings.rrf_k + 1)  # higher than single-list score


def test_rrf_empty_inputs_returns_empty():
    merged = rrf.run({}, {}, quota=4)
    assert merged == {}


def test_rrf_returns_chunk_candidates():
    chunk_id = "00000000-0000-0000-0000-000000000002"
    vector_results = {"catechism": [RetrievalPath("hyde", [_make_row(chunk_id)])]}
    fts_results = {}
    merged = rrf.run(vector_results, fts_results, quota=4)
    assert isinstance(merged["catechism"][0], ChunkCandidate)


def test_bible_hyde_genres_share_one_best_rank_vote():
    shared = _make_row("shared")
    paths = [
        RetrievalPath("hyde", [shared]),
        RetrievalPath("hyde", [_make_row("other"), shared]),
        RetrievalPath("hyde", [shared]),
        RetrievalPath("query", [shared]),
    ]
    merged = rrf.run({"bible": paths}, {"bible": [shared]}, quota=4)
    assert merged["bible"][0].rrf_score == pytest.approx(3 / (settings.rrf_k + 1))


def test_bible_hyde_only_agreement_does_not_outrank_query_and_fts_agreement():
    hyde_only = _make_row("hyde-only")
    cross_family = _make_row("cross-family")
    paths = [
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("hyde", [hyde_only]),
        RetrievalPath("query", [cross_family]),
    ]
    merged = rrf.run({"bible": paths}, {"bible": [cross_family]}, quota=4)
    assert [row.chunk_id for row in merged["bible"]] == ["cross-family", "hyde-only"]
    assert merged["bible"][1].rrf_score == pytest.approx(1 / (settings.rrf_k + 1))


def _ranked(*, target: str, rank: int, depth: int = 30, tag: str = "f") -> list[dict]:
    """A ranked list `depth` long with `target` at 1-indexed `rank`."""
    rows = [_make_row(f"{tag}-filler-{i}") for i in range(depth)]
    rows[rank - 1] = _make_row(target)
    return rows


def test_a_single_path_top_hit_outranks_deep_agreement_below_the_crossover():
    """Two families at rank r beat one family at rank 1 only while r < k + 2.

    This is the property k is chosen for, and the reason it is 20 rather than the
    conventional 60: at 60 the crossover sits at rank 62, past the end of every list
    `budget.retrieval_k` produces, so agreement always won and rank was a tiebreak.
    """
    crossover = settings.rrf_k + 2
    deep = crossover + 3          # below the crossover — agreement should lose
    shallow = max(1, crossover // 2)  # above it — agreement should win

    paths = [RetrievalPath("hyde", _ranked(target="solo-top", rank=1, tag="h"))]
    query_rows = _ranked(target="pair-deep", rank=deep, depth=deep + 5, tag="q")
    query_rows[shallow - 1] = _make_row("pair-shallow")
    fts_rows = _ranked(target="pair-deep", rank=deep, depth=deep + 5, tag="s")
    fts_rows[shallow - 1] = _make_row("pair-shallow")

    merged = rrf.run({"bible": paths + [RetrievalPath("query", query_rows)]},
                     {"bible": fts_rows}, quota=4, top_n=200)
    scores = {c.chunk_id: c.rrf_score for c in merged["bible"]}

    assert scores["solo-top"] == pytest.approx(1 / (settings.rrf_k + 1))
    assert scores["pair-deep"] == pytest.approx(2 / (settings.rrf_k + deep))
    assert scores["pair-shallow"] == pytest.approx(2 / (settings.rrf_k + shallow))

    # Agreement inside the crossover still wins; agreement below it does not.
    assert scores["pair-shallow"] > scores["solo-top"] > scores["pair-deep"]


def test_rrf_k_is_tuned_to_our_list_depth_not_the_conventional_default():
    """The shipped default of 20 is a deliberate deviation from the near-universal 60.

    60 traces to Cormack et al. (2009) on TREC runs 1000 deep and is what
    Elasticsearch, Weaviate, Vespa and LangChain all ship. Our lists are
    `budget.retrieval_k` deep — 50 in production, `quota * candidate_multiplier`
    in the `llm_only` ablations — so 60 put the agreement/rank crossover at rank
    62, past the end of every list, and rank never influenced the merge.

    Pinned against the field default rather than `settings.rrf_k` so a local
    `RRF_K` override does not read as a regression: this guards the value we
    ship, not the value this machine happens to run.

    If you are changing this, that is fine, but change it on evidence —
    `hyde_luna_rrf60` exists so `compare/` can measure the alternative.
    """
    assert Settings.model_fields["rrf_k"].default == 20


def test_rrf_k_comes_from_the_caller_not_module_scope():
    """A caller-supplied k changes the score, so pipelines can pin their own.

    Fails before `k` is a parameter: run() ignores the argument and scores with
    the module constant.
    """
    row = _make_row("solo")
    merged = rrf.run({"bible": [RetrievalPath("hyde", [row])]}, {}, quota=4, k=60)
    assert merged["bible"][0].rrf_score == pytest.approx(1 / (60 + 1))


def test_rrf_k_defaults_to_the_configured_setting():
    """Omitting k reproduces production scoring from settings, not a literal."""
    row = _make_row("solo")
    merged = rrf.run({"bible": [RetrievalPath("hyde", [row])]}, {}, quota=4)
    assert merged["bible"][0].rrf_score == pytest.approx(1 / (settings.rrf_k + 1))
