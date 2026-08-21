"""Tests for drift classification and the re-embed selection.

The tool's hardest job is saying NO: 26,581 Summa points differ from their Postgres row
only by a retained "Objection N" prefix. Their repair would be no larger than that of
the categories the tool DOES select — measured reproduction cosine 0.940-0.998 (median
0.977), against 0.943 for minor_text and ~0.930 for 86 of the label_drift points — but
it would cost 113x the writes. The refusal is about blast radius, not vector quality.
Most of what follows pins that refusal as tightly as it pins the 350 genuine repairs.

A prior review of the sibling backfill tool found that every mutation to the CLI script
survived a fully passing suite, because the tests asserted constants and never the code
consuming them. The wiring section at the bottom exists for that reason.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from backfill_vectors import LIVE_EMBEDDING_DIMS, PassageRow  # noqa: E402
from reembed import (  # noqa: E402
    BLANK_SOURCE, CONTENT_UNRELATED, DEFAULT_CATEGORIES, IN_SYNC, LABEL_DRIFT,
    MARKER_PREFIX, MINOR_TEXT, classify, needs_reembed,
)
import reembed_drifted_vectors as rd  # noqa: E402


# ---------------------------------------------------------------------------
# classify — the two drift axes
# ---------------------------------------------------------------------------

def test_identical_stores_are_in_sync():
    assert classify("body", "body", "Chapter 1", "Chapter 1") == IN_SYNC


def test_retained_marker_prefix_is_benign():
    """26,581 live points. Same passage; vector reproduces at 0.940-0.998 (med 0.977) —
    no worse than the categories that ARE selected, which is why the refusal rests on
    blast radius rather than on similarity."""
    assert classify(
        "It would seem that...", "Objection 1 It would seem that...",
        "Question 42", "Question 42",
    ) == MARKER_PREFIX


def test_every_dialectical_marker_is_recognised():
    for marker in ("Objection 3", "Reply to Objection 2", "I answer that",
                   "On the contrary"):
        assert classify("the text here and more", f"{marker} the text here and more",
                        "ch", "ch") == MARKER_PREFIX, marker


def test_unrelated_text_is_the_serious_case():
    """Gaudete in Domino: 78 points hold footnotes while Postgres holds paragraphs.
    Their vectors were built from the footnote, so only a re-embed repairs them."""
    assert classify(
        "Was it not an inner renewal of this kind that the recent Council...",
        "2 Cor. 11:28.", "V. A joy", "V. A joy",
    ) == CONTENT_UNRELATED


def test_trailing_boilerplate_removal_is_minor():
    assert classify(
        "The council declares.",
        "The council declares. Want to be automatically notified of new documents?",
        "ch", "ch",
    ) == MINOR_TEXT


def test_trailing_text_added_is_minor():
    assert classify("The council declares. NOTES", "The council declares.",
                    "ch", "ch") == MINOR_TEXT


def test_edited_text_sharing_most_words_is_minor():
    assert classify(
        "the quick brown fox jumps over the lazy dog today",
        "the quick brown fox jumps over the lazy dog", "ch", "ch",
    ) == MINOR_TEXT


def test_label_drift_alone_is_caught():
    """chapter_label is the embedding PREFIX, so a point whose text matches but whose
    label moved was still embedded behind a different heading. Measured 0.857-0.999,
    bimodal: ~0.994 for off-by-one range labels, ~0.930 for the 86 Evangelii Nuntiandi
    points whose stored label is a wholly different heading."""
    assert classify("body", "body", "Paragraphs 61-80", "Introduction") == LABEL_DRIFT


def test_marker_prefix_with_drifted_label_is_not_treated_as_benign():
    """The dangerous combination: filing this as marker_prefix would skip a point whose
    embedding prefix genuinely changed."""
    assert classify(
        "It would seem that...", "Objection 1 It would seem that...",
        "Question 42", "Question 7",
    ) == LABEL_DRIFT


def test_unrelated_content_outranks_label_drift():
    """Content is the more serious axis; a point built from other text is wrong
    whatever its prefix says."""
    assert classify("real paragraph text here", "2 Cor. 11:28.",
                    "A", "B") == CONTENT_UNRELATED


def test_empty_qdrant_content_is_unrelated_not_benign():
    assert classify("a real passage", "", "ch", "ch") == CONTENT_UNRELATED


def test_null_labels_on_both_sides_are_in_sync():
    """Defensive: no live row has a null chapter_label (verified across all 54,027), but
    absence on both sides must read as agreement rather than drift."""
    assert classify("body", "body", None, None) == IN_SYNC


# ---------------------------------------------------------------------------
# needs_reembed — the refusal
# ---------------------------------------------------------------------------

def test_marker_prefix_is_excluded_by_default():
    """The single most important assertion here: including it turns a 350-point repair
    into a 26,931-point full-collection rewrite for no larger a per-point gain."""
    assert MARKER_PREFIX not in DEFAULT_CATEGORIES
    assert not needs_reembed(MARKER_PREFIX)


def test_the_three_repair_categories_are_selected_by_default():
    for category in (CONTENT_UNRELATED, LABEL_DRIFT, MINOR_TEXT):
        assert needs_reembed(category), category


def test_in_sync_is_never_selected():
    assert not needs_reembed(IN_SYNC)
    assert not needs_reembed(IN_SYNC, rd.CATEGORY_SETS["all"])


def test_categories_all_does_include_marker_prefix():
    """The override exists; it must actually override."""
    assert needs_reembed(MARKER_PREFIX, rd.CATEGORY_SETS["all"])


def test_categories_unrelated_is_the_narrowest_selection():
    assert needs_reembed(CONTENT_UNRELATED, rd.CATEGORY_SETS["unrelated"])
    for category in (LABEL_DRIFT, MINOR_TEXT, MARKER_PREFIX):
        assert not needs_reembed(category, rd.CATEGORY_SETS["unrelated"]), category


# ---------------------------------------------------------------------------
# classify_rows
# ---------------------------------------------------------------------------

def _row(chunk_id="c1", position=0, content="body", chapter_label="Ch 1",
         chapter_key="ck1"):
    return PassageRow(
        chunk_id=chunk_id, document_id="d1", document_title="Rerum Novarum",
        author="Leo XIII", collection="encyclicals", content=content,
        reference="Rerum Novarum §1", anchor=f"a{position}", chapter_key=chapter_key,
        chapter_label=chapter_label, unit_label=None, position=position,
    )


def test_rows_without_a_qdrant_point_are_skipped_not_reported():
    """Creating missing points is the backfill's job. A tool that both created and
    overwrote would make an interrupted run much harder to reason about."""
    result = rd.classify_rows([_row("c1"), _row("c2", position=1)],
                              {"c1": {"content": "body", "chapter_label": "Ch 1"}})
    assert set(result) == {"c1"}


def test_each_row_is_classified_against_its_own_payload():
    rows = [_row("c1", 0, content="alpha"), _row("c2", 1, content="beta")]
    payloads = {
        "c1": {"content": "alpha", "chapter_label": "Ch 1"},
        "c2": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
    }
    result = rd.classify_rows(rows, payloads)
    assert result["c1"] == IN_SYNC
    assert result["c2"] == CONTENT_UNRELATED


# ---------------------------------------------------------------------------
# CLI gates
# ---------------------------------------------------------------------------

COLLECTIONS = {"summa", "encyclicals", "councils", "bible"}


def test_named_collection_and_default_categories_resolve():
    names, categories = rd.resolve_args("summa", "default", 100, COLLECTIONS)
    assert names == ["summa"]
    assert categories == DEFAULT_CATEGORIES


def test_all_expands_to_every_known_collection():
    names, _ = rd.resolve_args("all", "default", 100, COLLECTIONS)
    assert names == sorted(COLLECTIONS)


def test_unknown_collection_is_refused():
    try:
        rd.resolve_args("summma", "default", 100, COLLECTIONS)
    except rd.ArgError as exc:
        assert "unknown collection" in str(exc)
    else:
        raise AssertionError("a typo'd collection was accepted")


def test_unknown_category_set_is_refused():
    try:
        rd.resolve_args("summa", "everything", 100, COLLECTIONS)
    except rd.ArgError as exc:
        assert "category set" in str(exc)
    else:
        raise AssertionError("an unknown category set was accepted")


def test_non_positive_batch_size_is_refused():
    for bad in (0, -1):
        try:
            rd.resolve_args("summa", "default", bad, COLLECTIONS)
        except rd.ArgError as exc:
            assert "batch-size" in str(exc)
        else:
            raise AssertionError(f"--batch-size {bad} was accepted")


# ---------------------------------------------------------------------------
# Wiring — the selection must actually reach the write.
#
# Asserting DEFAULT_CATEGORIES excludes marker_prefix proves nothing if the code
# consuming it ignores the selection. These drive reembed_collection end to end.
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, _sql, _collection):
        return [dict(vars(row)) for row in self._rows]


class _FakeClient:
    """Records what was ASKED FOR, not just what was returned.

    A fake that swallows **kwargs and always hands back full payloads makes the read
    path invisible: dropping `chapter_label` from the scroll request would then pass
    every test while selecting the entire corpus in production.
    """

    def __init__(self, payloads, page_size=None):
        self._payloads = payloads
        self.upserted = []
        self.scroll_kwargs = []
        # Paginate like real Qdrant when asked. A fake that always returns everything on
        # one page hides a scroll loop that ignores `offset` — which in production would
        # read 1,000 of summa's 26,750 points and silently under-select while printing
        # success.
        self._page_size = page_size

    async def scroll(self, **kwargs):
        self.scroll_kwargs.append(kwargs)
        # A scroll loop that ignores `offset` would otherwise spin forever against a
        # paginating fake. Fail loudly instead: a hang in CI reads as infrastructure
        # trouble, not as the defect it actually is.
        if len(self.scroll_kwargs) > 50:
            raise AssertionError(
                "scroll() called >50 times — the paging loop is not advancing "
                "(is `offset` being passed through?)"
            )
        requested = kwargs.get("with_payload")
        items = list(self._payloads.items())
        if self._page_size is not None:
            start = kwargs.get("offset") or 0
            window = items[start:start + self._page_size]
            next_offset = (start + self._page_size
                           if start + self._page_size < len(items) else None)
        else:
            window, next_offset = items, None
        points = []
        for pid, payload in window:
            visible = ({k: v for k, v in payload.items() if k in requested}
                       if isinstance(requested, list) else payload)
            points.append(type("P", (), {"id": pid, "payload": visible})())
        return points, next_offset

    async def upsert(self, collection_name, points, wait):  # noqa: ARG002
        self.upserted.extend(points)


def _fingerprint(text: str) -> float:
    return float(sum((i + 1) * ord(ch) for i, ch in enumerate(text)) % 1_000_003)


async def _fake_embed(texts):
    return [[_fingerprint(t)] + [0.0] * (LIVE_EMBEDDING_DIMS - 1) for t in texts]


def _run(rows, payloads, categories=DEFAULT_CATEGORIES, apply=True):
    client = _FakeClient(payloads)
    original = rd.embed_texts
    rd.embed_texts = _fake_embed
    try:
        asyncio.run(rd.reembed_collection(
            client, _FakeConn(rows), "encyclicals", categories, apply, 100))
    finally:
        rd.embed_texts = original
    return client


def _three_rows():
    return [_row("c0", 0, content="alpha text"),
            _row("c1", 1, content="beta text"),
            _row("c2", 2, content="gamma text")]


def test_only_drifted_points_are_written():
    payloads = {
        "c0": {"content": "alpha text", "chapter_label": "Ch 1"},   # in sync
        "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},  # unrelated
        "c2": {"content": "gamma text", "chapter_label": "Ch 1"},   # in sync
    }
    client = _run(_three_rows(), payloads)
    assert [p.id for p in client.upserted] == ["c1"]


def test_marker_prefix_points_are_not_written_by_default():
    """The refusal, exercised through the real selection path rather than asserted
    against the constant."""
    rows = [_row("c0", 0, content="It would seem that x")]
    payloads = {"c0": {"content": "Objection 1 It would seem that x",
                       "chapter_label": "Ch 1"}}
    client = _run(rows, payloads)
    assert client.upserted == []


def test_categories_all_does_write_marker_prefix_points():
    rows = [_row("c0", 0, content="It would seem that x")]
    payloads = {"c0": {"content": "Objection 1 It would seem that x",
                       "chapter_label": "Ch 1"}}
    client = _run(rows, payloads, categories=rd.CATEGORY_SETS["all"])
    assert [p.id for p in client.upserted] == ["c0"]


def test_dry_run_writes_nothing():
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "gamma text", "chapter_label": "Ch 1"}}
    client = _run(_three_rows(), payloads, apply=False)
    assert client.upserted == []


def test_written_point_keeps_the_postgres_chunk_id():
    """Overwrite in place. A generated id would leave the broken point AND add a
    duplicate — strictly worse than doing nothing."""
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "gamma text", "chapter_label": "Ch 1"}}
    client = _run(_three_rows(), payloads)
    assert client.upserted[0].id == "c1"


def test_written_vector_is_unnamed_and_correctly_sized():
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "gamma text", "chapter_label": "Ch 1"}}
    client = _run(_three_rows(), payloads)
    vector = client.upserted[0].vector
    assert isinstance(vector, list)
    assert len(vector) == LIVE_EMBEDDING_DIMS


def test_written_payload_carries_the_postgres_text_not_the_stale_qdrant_text():
    """The point of the exercise: the repaired point must display its real passage."""
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "gamma text", "chapter_label": "Ch 1"}}
    client = _run(_three_rows(), payloads)
    assert client.upserted[0].payload["content"] == "beta text"


def test_each_vector_is_paired_with_the_row_it_was_built_from():
    """Two drifted rows, so a reversed pairing is observable — it is not with one."""
    rows = _three_rows()
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "Cf. Mk. 10:14.", "chapter_label": "Ch 1"}}
    client = _run(rows, payloads)
    assert len(client.upserted) == 2

    expected = {row.chunk_id: _fingerprint(text)
                for row, text in rd.plan(rows, {"c1", "c2"})}
    for point in client.upserted:
        assert point.vector[0] == expected[point.id], (
            f"{point.id} carries a vector built from another passage's text")


def test_embedding_input_uses_full_document_neighbour_context():
    """A drifted point must be embedded with its whole document present, or its vector
    sits in a different frame from the siblings that were written correctly."""
    rows = _three_rows()
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "gamma text", "chapter_label": "Ch 1"}}
    text = dict((r.chunk_id, t) for r, t in rd.plan(rows, {"c1"}))["c1"]
    assert "alpha text" in text
    assert "gamma text" in text
    assert text.startswith("[Ch 1] ")


# ---------------------------------------------------------------------------
# blank_source — unrepairable, and refused by every selection.
# ---------------------------------------------------------------------------

def test_blank_postgres_content_is_unrepairable():
    """21 live Summa chunks hold content='' from `_split_article`'s `else ""` branch
    while Qdrant holds usable text. Embedding a blank passage yields a vector of the
    bare prefix — worse than the stale-but-real vector already stored."""
    assert classify("", "Objection 4", "ch", "ch") == BLANK_SOURCE
    assert classify("   \n ", "Objection 4", "ch", "ch") == BLANK_SOURCE


def test_blank_source_is_refused_by_every_selection():
    """Including --categories all. No flag may opt into destroying a real vector."""
    assert not needs_reembed(BLANK_SOURCE)
    for name in ("default", "unrelated", "all"):
        assert not needs_reembed(BLANK_SOURCE, rd.CATEGORY_SETS[name]), name


def test_blank_source_points_are_never_written():
    rows = [_row("c0", 0, content="")]
    payloads = {"c0": {"content": "Objection 4", "chapter_label": "Ch 1"}}
    for name in ("default", "all"):
        client = _run(rows, payloads, categories=rd.CATEGORY_SETS[name])
        assert client.upserted == [], name


# ---------------------------------------------------------------------------
# Mutations that survived review round 1. Each of these failed to fail.
# ---------------------------------------------------------------------------

def test_blank_source_is_refused_even_if_explicitly_selected():
    """The guard itself, not the fact that no CATEGORY_SET happens to contain it.

    Round 1: mutating `needs_reembed` to drop BLANK_SOURCE survived the whole suite,
    because every other test only proved the second layer.
    """
    assert not needs_reembed(BLANK_SOURCE, frozenset({BLANK_SOURCE}))
    assert not needs_reembed(BLANK_SOURCE, frozenset({BLANK_SOURCE, CONTENT_UNRELATED}))


def test_no_category_set_offers_blank_source():
    """And the second layer, so both can't be deleted independently."""
    for name, categories in rd.CATEGORY_SETS.items():
        assert BLANK_SOURCE not in categories, name


def test_scroll_requests_chapter_label():
    """chapter_label is one of the two drift axes. Round 1: dropping it from the scroll
    request survived every test and moved live selection from 350 to 54,006, because
    every payload then read back label=None and looked drifted."""
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "gamma text", "chapter_label": "Ch 1"}}
    client = _run(_three_rows(), payloads)
    requested = client.scroll_kwargs[0]["with_payload"]
    assert "chapter_label" in requested
    assert "content" in requested


def test_each_payload_comes_from_its_own_row():
    """Round 1: `build_payload(window[0][0])` survived — it would stamp the first row's
    text onto every point in the batch, writing the exact corruption this tool repairs."""
    rows = _three_rows()
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "Cf. Mk. 10:14.", "chapter_label": "Ch 1"}}
    client = _run(rows, payloads)
    by_id = {p.id: p.payload for p in client.upserted}
    assert by_id["c1"]["content"] == "beta text"
    assert by_id["c2"]["content"] == "gamma text"
    assert by_id["c1"]["anchor"] != by_id["c2"]["anchor"]


def test_short_embedding_response_is_refused_at_the_pairing():
    """Vectors are paired to rows BY POSITION, so a short response shifts every later
    vector onto the wrong passage rather than dropping a tail."""
    rows = _three_rows()
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"},
                "c1": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
                "c2": {"content": "Cf. Mk. 10:14.", "chapter_label": "Ch 1"}}

    async def _short_embed(texts):
        return [[0.1] * LIVE_EMBEDDING_DIMS]

    client = _FakeClient(payloads)
    original = rd.embed_texts
    rd.embed_texts = _short_embed
    try:
        asyncio.run(rd.reembed_collection(
            client, _FakeConn(rows), "encyclicals", DEFAULT_CATEGORIES, True, 100))
    except RuntimeError as exc:
        assert "positionally mismatched" in str(exc)
    else:
        raise AssertionError("a short embedding response was accepted")
    finally:
        rd.embed_texts = original


def test_batch_size_is_honoured():
    """Round 1: ignoring batch_size survived. A single oversized request is a different
    failure mode against a real embedding API than several small ones."""
    rows = [_row(f"c{i}", i, content=f"passage {i} text") for i in range(5)]
    payloads = {f"c{i}": {"content": f"stale {i} unrelated words entirely",
                          "chapter_label": "Ch 1"} for i in range(5)}
    sizes = []

    async def _counting_embed(texts):
        sizes.append(len(texts))
        return [[0.1] * LIVE_EMBEDDING_DIMS for _ in texts]

    client = _FakeClient(payloads)
    original = rd.embed_texts
    rd.embed_texts = _counting_embed
    try:
        asyncio.run(rd.reembed_collection(
            client, _FakeConn(rows), "encyclicals", DEFAULT_CATEGORIES, True, 2))
    finally:
        rd.embed_texts = original

    assert sizes == [2, 2, 1], sizes
    assert len(client.upserted) == 5


# --- the overlap threshold, which nothing pinned ---

def test_overlap_below_the_threshold_is_unrelated():
    """~0.25 overlap. Lowering the threshold to 0.1 would call this the same passage."""
    pg = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    qd = "alpha beta gamma delta lambda mu nu xi omicron pi"
    assert classify(pg, qd, "ch", "ch") == CONTENT_UNRELATED


def test_overlap_above_the_threshold_is_the_same_passage():
    """~0.75 overlap, and neither is a prefix of the other, so only the overlap rule
    can reach it. Raising the threshold to 0.9 would call this a different passage."""
    pg = "alpha beta gamma delta epsilon zeta eta"
    qd = "alpha beta gamma delta epsilon zeta theta"
    assert classify(pg, qd, "ch", "ch") == MINOR_TEXT


def test_marker_strip_requires_more_than_a_shared_opening():
    """A 40-character prefix match alone would file an older revision that merely shares
    an opening sentence as MARKER_PREFIX — and REFUSE it."""
    pg = ("The passion of anger, like all other movements of the sensitive appetite, "
          "follows an apprehension of the senses.")
    qd = ("Objection 1 The passion of anger, like all other movements of the "
          "wholly different continuation that shares nothing further at all here.")
    assert classify(pg, qd, "ch", "ch") == CONTENT_UNRELATED


def test_scroll_pages_through_every_point():
    """Round 2: ignoring `offset` survived the suite. In production that reads 1,000 of
    summa's 26,750 points and silently under-selects while reporting success."""
    rows = [_row(f"c{i}", i, content=f"passage {i} text") for i in range(5)]
    payloads = {f"c{i}": {"content": f"stale {i} entirely different words here",
                          "chapter_label": "Ch 1"} for i in range(5)}

    client = _FakeClient(payloads, page_size=2)
    original = rd.embed_texts
    rd.embed_texts = _fake_embed
    try:
        asyncio.run(rd.reembed_collection(
            client, _FakeConn(rows), "encyclicals", DEFAULT_CATEGORIES, True, 100))
    finally:
        rd.embed_texts = original

    assert len(client.scroll_kwargs) == 3, "did not page to exhaustion"
    assert len(client.upserted) == 5, "points beyond the first page were missed"


def test_scroll_is_filtered_to_the_requested_collection():
    """Without the filter every collection reads the whole corpus — 10x the work and a
    classification against rows from other collections."""
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Ch 1"}}
    client = _run([_row("c0", 0, content="alpha text")], payloads)
    assert client.scroll_kwargs[0].get("scroll_filter") is not None


def test_upsert_goes_through_the_retrying_helper():
    """`client.upsert` directly bypasses writers.qdrant.upsert_points and its 4x
    backoff — the helper the original writer uses."""
    import inspect

    source = inspect.getsource(rd.reembed_collection)
    assert "upsert_points(" in source
    assert "client.upsert(" not in source


def test_trailing_text_added_is_minor_via_the_prefix_rule():
    """Round 2 found the existing same-named test passed through the OVERLAP rule, so
    the `pg.startswith(qd)` branch was unpinned. This text shares too few words to
    reach the overlap threshold, so only the prefix rule can classify it."""
    pg = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    qd = "alpha beta"
    assert classify(pg, qd, "ch", "ch") == MINOR_TEXT


def test_label_drifted_points_are_written():
    """235 of the 350 selected points are label_drift — the largest category, and the
    only one this tool can repair at all (the payload reconcile never syncs
    chapter_label). Round 3: skipping LABEL_DRIFT in the selection loop survived the
    whole suite, because every wiring fixture used a matching label."""
    rows = [_row("c0", 0, content="alpha text", chapter_label="Paragraphs 61-80")]
    payloads = {"c0": {"content": "alpha text", "chapter_label": "Introduction"}}
    client = _run(rows, payloads)
    assert [p.id for p in client.upserted] == ["c0"]
    assert client.upserted[0].payload["chapter_label"] == "Paragraphs 61-80"


def test_minor_text_points_are_written():
    """29 selected. Round 3: skipping MINOR_TEXT also survived the suite."""
    rows = [_row("c0", 0, content="The council declares.")]
    payloads = {"c0": {"content": "The council declares. Want to be notified of new "
                                  "documents?", "chapter_label": "Ch 1"}}
    client = _run(rows, payloads)
    assert [p.id for p in client.upserted] == ["c0"]
    assert client.upserted[0].payload["content"] == "The council declares."


def test_every_selected_category_reaches_the_write():
    """One fixture per repair category, so dropping any single one from the selection
    loop fails here rather than silently shrinking the live repair."""
    rows = [
        _row("c0", 0, content="alpha text"),                                  # unrelated
        _row("c1", 1, content="beta text", chapter_label="Paragraphs 61-80"),  # label
        _row("c2", 2, content="The council declares."),                        # minor
        _row("c3", 3, content="gamma text"),                                   # in sync
    ]
    payloads = {
        "c0": {"content": "2 Cor. 11:28.", "chapter_label": "Ch 1"},
        "c1": {"content": "beta text", "chapter_label": "Introduction"},
        "c2": {"content": "The council declares. NOTES", "chapter_label": "Ch 1"},
        "c3": {"content": "gamma text", "chapter_label": "Ch 1"},
    }
    client = _run(rows, payloads)
    assert sorted(p.id for p in client.upserted) == ["c0", "c1", "c2"]


def test_blank_source_operator_warning_is_emitted(capsys):
    """The refusal is well covered; the message telling the operator WHY was not, so
    deleting it survived the suite."""
    rows = [_row("c0", 0, content="")]
    payloads = {"c0": {"content": "Objection 4", "chapter_label": "Ch 1"}}
    _run(rows, payloads)
    out = capsys.readouterr().out
    assert "BLANK Postgres passage" in out
    assert "never" in out


def test_marker_prefix_refusal_is_explained_to_the_operator(capsys):
    """The tool's most consequential operator-facing statement: why 26,581 points were
    skipped. Round 4: deleting the message survived the suite, the same gap D5 closed
    for blank_source. A silent refusal reads as a bug."""
    rows = [_row("c0", 0, content="It would seem that x")]
    payloads = {"c0": {"content": "Objection 1 It would seem that x",
                       "chapter_label": "Ch 1"}}
    _run(rows, payloads)
    out = capsys.readouterr().out
    assert "marker_prefix" in out
    assert "--categories all" in out
