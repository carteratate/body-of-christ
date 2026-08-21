"""Tests for the missing-vector backfill decision logic (pure, no live stores)."""
from __future__ import annotations

from backfill_vectors import (
    LIVE_EMBEDDING_DIMS, PAYLOAD_FIELDS, PassageRow, build_payload,
    legacy_prefix, missing_chunk_ids, to_passages,
)


def _row(chunk_id="c1", position=0, chapter_key="ck1", content="body",
         chapter_label="Paragraphs 1-10", unit_label=None):
    return PassageRow(
        chunk_id=chunk_id, document_id="d1", document_title="Rerum Novarum",
        author="Leo XIII", collection="encyclicals", content=content,
        reference="Rerum Novarum §1", anchor=f"a{position}",
        chapter_key=chapter_key, chapter_label=chapter_label,
        unit_label=unit_label, position=position,
    )


# ---------------------------------------------------------------------------
# missing_chunk_ids
# ---------------------------------------------------------------------------

def test_finds_ids_present_in_postgres_and_absent_from_qdrant():
    assert missing_chunk_ids({"a", "b", "c"}, {"b"}) == ["a", "c"]


def test_result_is_sorted_so_runs_are_deterministic():
    assert missing_chunk_ids({"z", "a", "m"}, set()) == ["a", "m", "z"]


def test_orphans_are_not_returned():
    """A Qdrant point with no chunks row needs a targeted DELETE, a different
    operation with different risks. This tool must never act on that direction."""
    assert missing_chunk_ids({"a"}, {"a", "ghost"}) == []


def test_fully_backfilled_collection_yields_nothing():
    assert missing_chunk_ids({"a", "b"}, {"a", "b"}) == []


# ---------------------------------------------------------------------------
# legacy_prefix — must match the writer that produced the LIVE vectors
# ---------------------------------------------------------------------------

def test_prefix_is_the_chapter_label_form():
    """The live vectors were built with f"[{chapter_label}] ". The CURRENT writer uses
    an author/title prefix instead; using that here would embed the backfilled points
    in a different frame from every point around them."""
    assert legacy_prefix(_row(chapter_label="Paragraphs 61-80")) == "[Paragraphs 61-80] "


def test_prefix_reproduces_the_original_none_rendering():
    """The original was an f-string over the attribute, so a null label rendered as the
    literal "None". Reproducing that beats "fixing" it: consistency with the existing
    vectors is the whole point of a repair tool."""
    assert legacy_prefix(_row(chapter_label=None)) == "[None] "


# ---------------------------------------------------------------------------
# to_passages — reuse of build_embedding_input, not reimplementation
# ---------------------------------------------------------------------------

def test_passages_preserve_order_and_chapter_grouping():
    rows = [_row("c1", 0, "ck1"), _row("c2", 1, "ck1"), _row("c3", 2, "ck2")]
    passages = to_passages(rows)
    assert [p.position for p in passages] == [0, 1, 2]
    assert [p.chapter_key for p in passages] == ["ck1", "ck1", "ck2"]


def test_neighbour_splicing_stops_at_a_chapter_boundary():
    """Verified through the REAL build_embedding_input, so this pins the actual
    behaviour rather than a restatement of it."""
    from writers.search_writer import build_embedding_input

    rows = [
        _row("c1", 0, "ck1", content="AAAA"),
        _row("c2", 1, "ck1", content="BBBB"),
        _row("c3", 2, "ck2", content="CCCC"),
    ]
    passages = to_passages(rows)

    middle = build_embedding_input(passages, 1, 4, 4, "[x] ")
    assert "AAAA" in middle          # previous passage, same chapter
    assert "CCCC" not in middle      # next passage, different chapter

    last = build_embedding_input(passages, 2, 4, 4, "[x] ")
    assert "BBBB" not in last        # previous passage is in another chapter


def test_embedding_input_carries_the_prefix_and_the_passage_text():
    from writers.search_writer import build_embedding_input

    rows = [_row("c1", 0, "ck1", content="the passage text")]
    text = build_embedding_input(to_passages(rows), 0, 250, 250,
                                 legacy_prefix(rows[0]))
    assert text.startswith("[Paragraphs 1-10]")
    assert "the passage text" in text


# ---------------------------------------------------------------------------
# build_payload
# ---------------------------------------------------------------------------

def test_payload_matches_the_shape_neighbours_already_carry():
    payload = build_payload(_row(unit_label="Objection 1"))
    assert set(payload) == set(PAYLOAD_FIELDS)


def test_payload_includes_the_fields_the_reconcile_added():
    """chapter_key and unit_label were written to all 53,747 existing points. A new
    point without them arrives already inconsistent with its neighbours."""
    payload = build_payload(_row(unit_label="Objection 1"))
    assert payload["chapter_key"] == "ck1"
    assert payload["unit_label"] == "Objection 1"


def test_payload_stores_clean_content_not_the_augmented_embedding_input():
    """The neighbour-augmented string exists to give the VECTOR context. Storing it
    would change what search displays — the same invariant build_point documents."""
    row = _row(content="just this passage")
    assert build_payload(row)["content"] == "just this passage"


def test_dimensionality_is_pinned_to_the_live_collection():
    """settings.EMBEDDING_DIMS is now 3072 for the V5 pipeline; the live collection is
    1536. Reading the setting here would emit vectors it cannot accept."""
    assert LIVE_EMBEDDING_DIMS == 1536


# ---------------------------------------------------------------------------
# CLI argument gates — reachable from tests, unlike inline __main__ validation.
# ---------------------------------------------------------------------------

import os as _os  # noqa: E402
import sys as _sys  # noqa: E402

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "scripts"))
from backfill_missing_vectors import ArgError, resolve_args  # noqa: E402

COLLECTIONS = {"encyclicals", "apostolic-exhortations", "papal-documents", "bible"}


def test_named_collection_resolves():
    assert resolve_args("encyclicals", 100, COLLECTIONS) == ["encyclicals"]


def test_all_expands_to_every_known_collection():
    assert resolve_args("all", 100, COLLECTIONS) == sorted(COLLECTIONS)


def test_unknown_collection_is_refused_not_silently_skipped():
    """A typo must not report 'nothing to do' and exit 0, leaving the operator
    believing a collection was repaired when nothing was read."""
    try:
        resolve_args("encyclical", 100, COLLECTIONS)
    except ArgError as exc:
        assert "unknown collection" in str(exc)
    else:
        raise AssertionError("typo'd collection was accepted")


def test_non_positive_batch_size_is_refused():
    for bad in (0, -1):
        try:
            resolve_args("bible", bad, COLLECTIONS)
        except ArgError as exc:
            assert "batch-size" in str(exc)
        else:
            raise AssertionError(f"--batch-size {bad} was accepted")


# ---------------------------------------------------------------------------
# The WIRING, not just the constants.
#
# A prior review mutated the CLI script eight ways — empty prefix, dropped
# `dimensions=`, named vector, random point id, disabled dry-run gate, neighbour
# context destroyed, k_prev/k_next swapped, index-by-position — and ALL EIGHT survived
# a fully passing suite. The constants were asserted; nothing asserted that the code
# consuming them was hooked up. These close that gap.
#
# `backfill_collection` already takes its client and connection as parameters, so a
# fake client plus a stubbed `_embed` exercises the real path with no network.
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

import backfill_missing_vectors as bf  # noqa: E402


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, _sql, _collection):
        return [dict(vars(row)) for row in self._rows]


class _FakeClient:
    """Records upserts; reports one existing point so exactly one row is missing."""

    def __init__(self, existing_ids):
        self.existing = list(existing_ids)
        self.upserted = []

    async def scroll(self, **kwargs):
        return [type("P", (), {"id": pid})() for pid in self.existing], None

    async def upsert(self, collection_name, points, wait):  # noqa: ARG002
        self.upserted.extend(points)


def _doc_rows(n=3):
    return [_row(f"c{i}", position=i, chapter_key="ck1", content=f"passage {i} text")
            for i in range(n)]


def _run_backfill(rows, existing_ids, apply=True, embed=None):
    client = _FakeClient(existing_ids)
    captured = {}

    async def _fake_embed(texts):
        captured["texts"] = list(texts)
        return (embed or (lambda t: [[0.1] * LIVE_EMBEDDING_DIMS for _ in t]))(texts)

    original = bf.embed_texts
    bf.embed_texts = _fake_embed
    try:
        asyncio.run(bf.backfill_collection(
            client, _FakeConn(rows), "encyclicals", apply, 100))
    finally:
        bf.embed_texts = original
    return client, captured


def test_dry_run_writes_nothing():
    """A disabled `if not apply` gate previously passed the whole suite."""
    client, captured = _run_backfill(_doc_rows(), ["c0", "c1"], apply=False)
    assert client.upserted == []
    assert "texts" not in captured, "dry run must not embed"


def test_apply_writes_only_the_missing_point():
    client, _ = _run_backfill(_doc_rows(), ["c0", "c1"], apply=True)
    assert [p.id for p in client.upserted] == ["c2"]


def test_written_point_id_is_the_postgres_chunk_id():
    """chunks.id == passage_id(document_id, anchor) == the Qdrant point id, verified
    across all 54,027 rows. A generated id would DUPLICATE rather than fill a gap."""
    client, _ = _run_backfill(_doc_rows(), ["c0", "c1"], apply=True)
    assert client.upserted[0].id == "c2"


def test_written_vector_is_unnamed():
    """The live collection has an unnamed vector; the current writer emits a named
    "dense" one, which this collection would reject."""
    client, _ = _run_backfill(_doc_rows(), ["c0", "c1"], apply=True)
    assert isinstance(client.upserted[0].vector, list)


def test_written_payload_matches_the_neighbour_shape():
    client, _ = _run_backfill(_doc_rows(), ["c0", "c1"], apply=True)
    assert set(client.upserted[0].payload) == set(PAYLOAD_FIELDS)


def test_embedding_input_carries_the_legacy_prefix():
    """An empty prefix previously passed. The live vectors were built with
    f"[{chapter_label}] "; without it a backfilled point sits in a different frame
    from every point around it."""
    _, captured = _run_backfill(_doc_rows(), ["c0", "c1"], apply=True)
    assert captured["texts"][0].startswith("[Paragraphs 1-10] ")


def test_embedding_input_keeps_full_document_neighbour_context():
    """Filtering the document down to the missing rows before embedding previously
    passed. The neighbour text is what makes the vector comparable to its siblings."""
    _, captured = _run_backfill(_doc_rows(), ["c0", "c1"], apply=True)
    assert "passage 1 text" in captured["texts"][0], "previous neighbour missing"


def test_embedding_asks_for_the_live_collection_dimensionality():
    """Dropping `dimensions=` yields 3072-dim vectors the collection cannot take."""
    import inspect

    source = inspect.getsource(bf.embed_texts)
    assert "dimensions=LIVE_EMBEDDING_DIMS" in source


def test_upsert_goes_through_the_retrying_helper():
    """client.upsert directly bypasses writers.qdrant.upsert_points, which retries 4x
    with backoff — the same helper the writer being replayed uses."""
    import inspect

    source = inspect.getsource(bf.backfill_collection)
    assert "upsert_points(" in source
    assert "client.upsert(" not in source


def test_non_contiguous_positions_are_refused():
    """List index is used as the passage position. A deleted chunks row would shift the
    neighbour window and produce a wrong-but-plausible embedding input."""
    rows = [_row("c0", position=0), _row("c1", position=2)]  # gap at 1
    try:
        bf.plan(rows, {"c1"})
    except RuntimeError as exc:
        assert "non-contiguous" in str(exc)
    else:
        raise AssertionError("a position gap was accepted")


def test_short_embedding_response_is_refused():
    """Vectors are paired to rows BY POSITION, so a short response would shift every
    later vector onto the wrong passage rather than merely dropping the tail."""
    rows = _doc_rows(4)
    try:
        _run_backfill(rows, ["c0"], apply=True, embed=lambda t: [[0.1] * 1536])
    except RuntimeError as exc:
        assert "positionally mismatched" in str(exc) or "vectors for" in str(exc)
    else:
        raise AssertionError("a short embedding response was accepted")


def test_neighbour_window_is_asymmetric_in_the_right_direction():
    """k_prev takes the PREVIOUS passage's TAIL, k_next the NEXT passage's HEAD.

    Swapping them survived an earlier suite because the fixture used equal windows.
    Asymmetric sizes and distinguishable head/tail text are what make the direction
    observable — and direction matters: a passage embedded with the wrong side of its
    neighbours is subtly misplaced against every correctly-written point around it.
    """
    from writers.search_writer import build_embedding_input

    rows = [
        _row("c0", position=0, chapter_key="ck1", content="PSTART" + "p" * 40 + "PTAIL"),
        _row("c1", position=1, chapter_key="ck1", content="middle"),
        _row("c2", position=2, chapter_key="ck1", content="NHEAD" + "n" * 40 + "NEND"),
    ]
    passages = to_passages(rows)

    text = build_embedding_input(passages, 1, 5, 5, "[x] ")
    assert "PTAIL" in text, "k_prev must take the previous passage's TAIL"
    assert "NHEAD" in text, "k_next must take the next passage's HEAD"
    assert "PSTART" not in text
    assert "NEND" not in text


def test_passage_is_embedded_against_its_own_neighbours_not_another_chapter():
    """Indexing by `row.position` instead of the list index survived an earlier suite
    because the fixture's positions happened to equal their indices. Here the document
    spans two chapters, so using the wrong index reaches across the boundary."""
    from writers.search_writer import build_embedding_input

    rows = [
        _row("c0", position=0, chapter_key="ckA", content="AAA chapter one"),
        _row("c1", position=1, chapter_key="ckA", content="BBB chapter one"),
        _row("c2", position=2, chapter_key="ckB", content="CCC chapter two"),
        _row("c3", position=3, chapter_key="ckB", content="DDD chapter two"),
    ]
    passages = to_passages(rows)

    # First passage of chapter two: its only same-chapter neighbour is the NEXT one.
    text = build_embedding_input(passages, 2, 200, 200, "[x] ")
    assert "CCC chapter two" in text
    assert "DDD chapter two" in text
    assert "BBB chapter one" not in text, "reached across a chapter boundary"


def test_plan_indexes_by_list_position_not_row_position():
    """Pins the call itself, so a swap to `row.position` fails even when the two
    coincide in the fixture."""
    import inspect

    source = inspect.getsource(bf.plan)
    assert "for index, row in enumerate(doc_rows)" in source
    assert "passages, index, k_prev, k_next" in source
    assert "row.position," not in source


def test_plan_passes_the_overlap_window_in_writer_order():
    import inspect

    source = inspect.getsource(bf.plan)
    assert "k_prev, k_next = settings.overlap_for(" in source
    assert "passages, index, k_prev, k_next" in source


# ---------------------------------------------------------------------------
# Multi-row pairing.
#
# Every fixture above has exactly ONE missing chunk, which makes mispairing
# structurally untestable: reversing the vector order, taking the payload from the
# wrong row, or writing the neighbour-augmented text as payload content all survive a
# single-row suite. Mispairing is precisely the harm the length guards were added to
# prevent — and a length check only catches a COUNT mismatch, never a wrong pairing.
# ---------------------------------------------------------------------------

def _run_multi(existing_ids, embed_fn):
    """Four-row document, two missing, with per-text distinguishable vectors."""
    rows = [
        _row(f"c{i}", position=i, chapter_key="ck1", content=f"passage {i} text")
        for i in range(4)
    ]
    client = _FakeClient(existing_ids)
    original = bf.embed_texts
    bf.embed_texts = embed_fn
    try:
        asyncio.run(bf.backfill_collection(client, _FakeConn(rows), "encyclicals", True, 100))
    finally:
        bf.embed_texts = original
    return rows, client


def _text_fingerprint(text: str) -> float:
    """A value that differs for texts of EQUAL LENGTH.

    Length alone is not enough: two adjacent passages in the fixture produce
    equal-length embedding inputs, so a length-based fingerprint cannot see a reversed
    pairing — which is exactly the defect this fixture exists to catch.
    """
    return float(sum((i + 1) * ord(ch) for i, ch in enumerate(text)) % 1_000_003)


async def _fingerprint_embed(texts):
    """A vector whose first component encodes its input, so pairing is observable."""
    return [[_text_fingerprint(text)] + [0.0] * (LIVE_EMBEDDING_DIMS - 1)
            for text in texts]


def test_each_vector_is_paired_with_the_row_it_was_built_from():
    """Reversing the pairing keeps counts equal and every assertion above green."""
    rows, client = _run_multi(["c0", "c3"], _fingerprint_embed)
    assert len(client.upserted) == 2

    expected = {row.chunk_id: _text_fingerprint(text)
                for row, text in bf.plan(rows, {"c1", "c2"})}
    for point in client.upserted:
        assert point.vector[0] == expected[point.id], (
            f"point {point.id} carries a vector built from another passage's text"
        )


def test_each_payload_comes_from_its_own_row():
    """Taking the payload from window[0] survives a single-row fixture."""
    rows, client = _run_multi(["c0", "c3"], _fingerprint_embed)
    by_id = {p.id: p.payload for p in client.upserted}
    assert by_id["c1"]["content"] == "passage 1 text"
    assert by_id["c2"]["content"] == "passage 2 text"


def test_payload_content_is_the_clean_passage_not_the_embedding_input():
    """The neighbour-augmented string exists to give the VECTOR context. Storing it
    would change what search displays — and with neighbours present it is strictly
    longer than the passage, so a single-row fixture can hide the swap."""
    rows, client = _run_multi(["c0", "c3"], _fingerprint_embed)
    texts = dict((r.chunk_id, t) for r, t in bf.plan(rows, {"c1", "c2"}))
    for point in client.upserted:
        assert not point.payload["content"].startswith("[")
        assert "passage" in point.payload["content"]
        assert point.payload["content"] != texts[point.id]


def test_payload_carries_document_metadata_for_every_written_point():
    """Dropping author/reference survives when only one point is ever written."""
    _, client = _run_multi(["c0", "c3"], _fingerprint_embed)
    for point in client.upserted:
        assert point.payload["author"] == "Leo XIII"
        assert point.payload["reference"] == "Rerum Novarum §1"
        assert point.payload["document_title"] == "Rerum Novarum"


def test_embedding_model_is_pinned_not_read_from_settings():
    """settings.EMBEDDING_MODEL is a moving target the V5 pipeline already drifted. A
    model swap would embed the backfill into a DIFFERENT vector space at the correct
    dimensionality — silently accepted by Qdrant, undetectable by any shape check."""
    import inspect

    source = inspect.getsource(bf.embed_texts)
    assert "model=LIVE_EMBEDDING_MODEL" in source
    assert "settings.EMBEDDING_MODEL" not in source


def test_position_guard_ignores_documents_with_nothing_missing():
    """An unrelated gap elsewhere in the collection must not abort a repair we can
    safely make."""
    rows = [
        _row("other0", position=0, chapter_key="ckA"),
        _row("other2", position=2, chapter_key="ckA"),   # gap, but nothing missing here
    ]
    rows[0] = PassageRow(**{**vars(rows[0]), "document_id": "other-doc"})
    rows[1] = PassageRow(**{**vars(rows[1]), "document_id": "other-doc"})
    rows += [_row("c0", position=0, chapter_key="ck1"),
             _row("c1", position=1, chapter_key="ck1")]

    work = bf.plan(rows, {"c1"})
    assert [row.chunk_id for row, _ in work] == ["c1"]


def test_pinned_model_value_is_the_one_that_produced_the_live_vectors():
    """The dims pin has a value assertion; the model pin did not — so mutating it to
    text-embedding-3-small survived a full suite. Same text under that model measures
    cosine -0.03 against the stored vector: a different space at the right shape, which
    Qdrant accepts silently and no shape check can detect.

    Verified two ways: `EMBEDDING_MODEL` has been this literal in every revision of
    config.py since the first commit, and re-embedding already-vectored chunks with it
    reproduces the stored vectors at cosine >= 0.9992.
    """
    from backfill_vectors import LIVE_EMBEDDING_MODEL

    assert LIVE_EMBEDDING_MODEL == "text-embedding-3-large"


def test_prefix_is_taken_per_row_not_from_the_first_row_of_the_document():
    """Every earlier fixture shared one chapter_label, so using doc_rows[0]'s prefix for
    the whole document survived. Real documents span many labels — one encyclical uses
    [Introduction], [III. The Crisis...], [IX. Beyond the Sun] within a single work."""
    rows = [
        _row("c0", position=0, chapter_key="ckA", chapter_label="Introduction"),
        _row("c1", position=1, chapter_key="ckB", chapter_label="III. The Crisis"),
        _row("c2", position=2, chapter_key="ckC", chapter_label="IX. Beyond the Sun"),
    ]
    work = dict((row.chunk_id, text) for row, text in bf.plan(rows, {"c1", "c2"}))
    assert work["c1"].startswith("[III. The Crisis] ")
    assert work["c2"].startswith("[IX. Beyond the Sun] ")
