"""Tests for the Qdrant/Postgres payload diff (pure logic, no live stores)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

# Imported, never redefined: a local copy would keep passing if the real constant
# ever gained "content", which is the one invariant this file exists to pin. It lives
# in `reconcile` (which imports nothing) so this stays runnable without credentials.
from reconcile import RECONCILED_FIELDS, STRUCTURAL_FIELDS as STRUCTURAL, build_report, diff_point
from reconcile_qdrant_payloads import ArgError, resolve_args


def _row(cid="c1", content="body", unit_label="Objection 1", chapter_key="summa/q1/a1"):
    return {"id": cid, "content": content, "unit_label": unit_label,
            "chapter_key": chapter_key}


# ---------------------------------------------------------------------------
# diff_point
# ---------------------------------------------------------------------------

def test_identical_payload_produces_no_diff():
    """An already-reconciled point must produce zero writes, so re-running is a no-op."""
    row = _row()
    payload = {"content": "body", "unit_label": "Objection 1", "chapter_key": "summa/q1/a1"}
    assert diff_point(payload, row) is None


def test_missing_structural_fields_are_added():
    """The live state: every payload has content but no unit_label/chapter_key."""
    diff = diff_point({"content": "body"}, _row())
    assert diff is not None
    assert diff.changes == {"unit_label": "Objection 1", "chapter_key": "summa/q1/a1"}
    assert diff.reasons == ("field_missing",)


def test_content_drift_is_detected_and_labelled():
    """The summa case: Qdrant kept the inline marker, Postgres moved it to unit_label."""
    payload = {"content": "Objection 1 body", "unit_label": "Objection 1",
               "chapter_key": "summa/q1/a1"}
    diff = diff_point(payload, _row(content="body"))
    assert diff is not None
    assert diff.changes == {"content": "body"}
    assert diff.reasons == ("content_drift",)


def test_field_selection_limits_what_is_written():
    """--fields structural must not touch content, which is gated on step 3."""
    payload = {"content": "Objection 1 body"}
    diff = diff_point(payload, _row(content="body"), STRUCTURAL)
    assert diff is not None
    assert "content" not in diff.changes
    assert set(diff.changes) == {"unit_label", "chapter_key"}


def test_postgres_null_never_overwrites_a_present_payload_value():
    """A NULL means 'this collection does not populate that column', not 'delete it'.

    church-fathers and medieval have no unit_label at all; blanking their payloads
    would be a silent data loss disguised as a reconcile.
    """
    payload = {"content": "body", "unit_label": "keep me", "chapter_key": "ck"}
    row = _row(unit_label=None, chapter_key=None)
    assert diff_point(payload, row) is None


def test_both_reasons_reported_when_content_and_fields_both_drift():
    diff = diff_point({"content": "stale"}, _row(content="fresh"))
    assert diff is not None
    assert set(diff.reasons) == {"content_drift", "field_missing"}


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

def test_report_counts_each_category_once():
    rows = [
        _row("in-sync"),
        _row("drifted", content="fresh"),
        _row("needs-fields"),
    ]
    payloads = {
        "in-sync": {"content": "body", "unit_label": "Objection 1",
                    "chapter_key": "summa/q1/a1"},
        "drifted": {"content": "stale", "unit_label": "Objection 1",
                    "chapter_key": "summa/q1/a1"},
        "needs-fields": {"content": "body"},
    }
    report = build_report("summa", payloads, rows)

    assert report.in_sync == 1
    assert report.content_drift == 1
    assert report.fields_missing == 1
    assert len(report.diffs) == 2


def test_orphaned_points_are_reported_not_written():
    """A Qdrant point with no chunks row needs a DELETE, not a payload write.

    Writing it would leave a vector that breaks the reader and fails the retrievals
    FK; reporting it surfaces the broken ingest instead of papering over it.
    """
    report = build_report(
        "summa",
        {"ghost": {"content": "x"}, "real": {"content": "body"}},
        [_row("real")],
    )
    assert report.orphaned == ["ghost"]
    assert all(d.point_id != "ghost" for d in report.diffs)


def test_unvectorised_rows_are_reported_not_written():
    """The live encyclicals/apostolic-exhortations/papal-documents case: 280 rows
    exist in Postgres with no vector. They need an embed run, not a payload write."""
    report = build_report("encyclicals", {}, [_row("no-vector")])
    assert report.unvectorised == ["no-vector"]
    assert report.diffs == []


def test_fully_reconciled_collection_yields_no_diffs():
    rows = [_row(f"c{i}") for i in range(5)]
    payloads = {
        f"c{i}": {"content": "body", "unit_label": "Objection 1",
                  "chapter_key": "summa/q1/a1"}
        for i in range(5)
    }
    report = build_report("summa", payloads, rows)
    assert report.diffs == []
    assert report.in_sync == 5


def test_position_is_not_reconciled():
    """Populating `position` would stop fetch_positions querying Postgres, which is
    also what detects and drops orphaned Qdrant points."""
    assert "position" not in RECONCILED_FIELDS


# ---------------------------------------------------------------------------
# Safety invariants — these pin the constants the CLI's gating depends on.
# ---------------------------------------------------------------------------

def test_structural_field_set_never_includes_content():
    """The safety gate: --fields structural must be applicable without review.

    Syncing content strips the inline 'Objection N ' marker from summa payloads,
    which is currently the reranker's only objection signal. If content ever leaks
    into the structural set, the default invocation silently becomes the dangerous
    one.
    """
    assert "content" not in STRUCTURAL
    assert set(STRUCTURAL) == {"unit_label", "chapter_key"}


def test_blank_source_never_overwrites_populated_payload():
    """21 live summa chunks hold content='' while Qdrant holds usable text.

    retrieve_vector's completeness guard tests `is None`, so an empty string passes
    it and would reach the reranker and the UI as a blank card.
    """
    payload = {"content": "Objection 4", "unit_label": "Objection 4"}
    row = _row(content="", unit_label="Objection 4", chapter_key=None)
    assert diff_point(payload, row) is None


def test_whitespace_only_source_is_treated_as_blank():
    payload = {"content": "real text", "unit_label": "Objection 1",
               "chapter_key": "summa/q1/a1"}
    assert diff_point(payload, _row(content="   \n ")) is None


def test_blank_source_is_reported_so_the_ingest_defect_is_visible():
    report = build_report(
        "summa",
        {"c1": {"content": "Objection 4"}},
        [_row("c1", content="", unit_label=None, chapter_key=None)],
    )
    assert report.blank_in_source == {"content": ["c1"]}
    assert report.diffs == []


def test_blank_payload_and_blank_source_is_not_reported():
    """Only a blank source SHADOWING real payload text is a defect worth surfacing."""
    report = build_report(
        "summa",
        {"c1": {"content": ""}},
        [_row("c1", content="", unit_label=None, chapter_key=None)],
    )
    assert report.blank_in_source == {}


# ---------------------------------------------------------------------------
# Report arithmetic — mutation testing showed these were entirely uncovered.
# ---------------------------------------------------------------------------

def test_unvectorised_rows_are_not_counted_as_in_sync():
    report = build_report("encyclicals", {}, [_row("a"), _row("b")])
    assert report.in_sync == 0
    assert len(report.unvectorised) == 2


def test_header_counts_report_the_side_they_name():
    """qdrant_points counts payloads, postgres_rows counts rows — not swapped."""
    report = build_report(
        "summa",
        {"a": {"content": "x"}, "b": {"content": "y"}, "ghost": {"content": "z"}},
        [_row("a"), _row("b")],
    )
    assert report.qdrant_points == 3
    assert report.postgres_rows == 2


def test_categories_account_for_every_matched_row():
    """in_sync + len(diffs) must equal the rows that matched a payload."""
    rows = [_row("a"), _row("b", content="fresh"), _row("c"), _row("missing")]
    payloads = {
        "a": {"content": "body", "unit_label": "Objection 1", "chapter_key": "summa/q1/a1"},
        "b": {"content": "stale", "unit_label": "Objection 1", "chapter_key": "summa/q1/a1"},
        "c": {"content": "body"},
    }
    report = build_report("summa", payloads, rows)
    matched = len(rows) - len(report.unvectorised)
    assert report.in_sync + len(report.diffs) == matched


# ---------------------------------------------------------------------------
# CLI safety gates. These live in `resolve_args` rather than inline under
# `if __name__ == "__main__":` precisely so they are reachable from here — an
# unreachable gate is pinned by nothing, which is how the field-set invariant
# went unverified in the first place.
# ---------------------------------------------------------------------------

COLLECTIONS = {"summa", "catechism", "canon-law", "bible"}


def _resolve(fields="structural", collection="summa", apply=False,
             allow=False, batch=500):
    return resolve_args(fields, collection, apply, allow, batch, COLLECTIONS)


def test_structural_apply_needs_no_override():
    names, fields = _resolve(apply=True)
    assert names == ["summa"]
    assert fields == STRUCTURAL


def test_content_apply_is_refused_without_the_override():
    for fields_name in ("content", "all"):
        try:
            _resolve(fields=fields_name, apply=True)
        except ArgError as exc:
            assert "content" in str(exc)
        else:
            raise AssertionError(f"--fields {fields_name} --apply was not refused")


def test_content_dry_run_is_allowed_without_the_override():
    """Inspecting the drift must never require arming the dangerous flag."""
    _, fields = _resolve(fields="content", apply=False)
    assert fields == ("content",)


def test_content_apply_is_allowed_with_the_override():
    _, fields = _resolve(fields="all", apply=True, allow=True)
    assert fields == RECONCILED_FIELDS


def test_content_hazard_names_both_failure_modes():
    """The gate message must not describe only the summa marker: the re-chunked
    collections need a re-embed, which a payload sync cannot provide."""
    try:
        _resolve(fields="all", apply=True)
    except ArgError as exc:
        message = str(exc)
    else:
        raise AssertionError("--fields all --apply was not refused")
    assert "unit_label" in message
    assert "re-embed" in message
    assert "apostolic-exhortations" in message


def test_unknown_collection_is_refused_not_silently_skipped():
    try:
        _resolve(collection="sumaa")
    except ArgError as exc:
        assert "unknown collection" in str(exc)
    else:
        raise AssertionError("a typo'd collection was accepted")


def test_all_expands_to_every_known_collection():
    names, _ = _resolve(collection="all")
    assert names == sorted(COLLECTIONS)


def test_non_positive_batch_size_is_refused():
    for bad in (0, -1):
        try:
            _resolve(batch=bad)
        except ArgError as exc:
            assert "batch-size" in str(exc)
        else:
            raise AssertionError(f"--batch-size {bad} was accepted")


def test_unknown_field_set_raises_argerror_not_keyerror():
    """resolve_args is public and tested, so every rejection must be an ArgError."""
    try:
        _resolve(fields="structrual")
    except ArgError as exc:
        assert "field set" in str(exc)
    else:
        raise AssertionError("an unknown field set was accepted")


def test_collection_typo_is_reported_before_other_argument_errors():
    """A typo is the likeliest mistake; reporting batch-size or the content gate
    instead sends the operator chasing the wrong problem."""
    try:
        _resolve(collection="sumaa", fields="all", apply=True, batch=0)
    except ArgError as exc:
        assert "unknown collection" in str(exc)
    else:
        raise AssertionError("typo'd collection was accepted")


def test_content_hazard_does_not_misassign_the_re_embed_collections():
    """Councils/encyclicals/papal-documents drift by trailing-boilerplate strips —
    same passage, valid vector — so the message must not send them for a re-embed.
    Only apostolic-exhortations and summa hold points whose vector was embedded from
    unrelated text (78 + 8 = 86, classified against the live corpus 2026-08-19)."""
    try:
        _resolve(fields="content", apply=True)
    except ArgError as exc:
        message = str(exc)
    else:
        raise AssertionError("--fields content --apply was not refused")
    re_embed_clause = message.split("2.", 1)[1].split("The remaining", 1)[0]
    assert "apostolic-exhortations" in re_embed_clause
    assert "summa" in re_embed_clause
    for safe in ("councils", "encyclicals", "papal-documents"):
        assert safe not in re_embed_clause, f"{safe} wrongly sent for a re-embed"
