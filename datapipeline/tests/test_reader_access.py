import asyncio

import pytest

import reader_access as RA
import rights_inventory as R


@pytest.mark.parametrize("status", R.STATUSES)
def test_every_inventory_status_is_classified(status):
    expected = RA.EXCERPT if status in ("in-copyright", "unknown") else RA.FULL
    assert RA.access_for_status(status) == expected


def test_an_unknown_status_is_refused():
    with pytest.raises(ValueError):
        RA.access_for_status("pd-made-up")
    with pytest.raises(ValueError):
        RA.access_for_status("cleared")


def test_the_real_inventory_classifies_without_error():
    assert RA.access_by_id(R.load())


def _entry(id, work, status, planned_for=None):
    return {"document_id": id, "collection": "encyclicals", "work": work,
            "author": "Pope Leo XIII", "source_path": f"encyclicals/{work.lower()}.html",
            "status": status, "planned_for": planned_for}


def _table(*entries):
    return RA.access_by_id(list(entries))


def test_access_matches_on_document_id_not_labels():
    # Two works share a title; their IDs tell them apart, and a relabel changes nothing.
    table = _table(_entry("a", "Ubi Primum", "unknown"),
                   _entry("b", "Ubi Primum", "pd-us-pre-1931"))
    assert RA.access_for("a", table) == RA.EXCERPT
    assert RA.access_for("b", table) == RA.FULL


def test_a_document_with_no_inventory_row_is_excerpt_only():
    assert RA.resolve("nowhere", _table()) == (RA.EXCERPT, RA.NO_ROW)


def test_a_planned_row_matches_no_document():
    table = _table(_entry(None, "Not Yet Built", "pd-us-pre-1931", planned_for="1.2c"))
    assert table == {}


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    async def fetch(self, sql, *args):
        return self.rows

    async def execute(self, sql, *args):
        self.updates.append(args)
        to, ids = args
        for r in self.rows:
            if str(r["id"]) in ids:
                r["reader_access"] = to

    def transaction(self):
        class _T:
            async def __aenter__(self): return None
            async def __aexit__(self, *a): return False
        return _T()


def _row(id, work, access):
    return {"id": id, "collection": "encyclicals", "title": work, "reader_access": access}


def test_sync_dry_run_reports_without_writing():
    conn = FakeConn([_row("1", "Libertas", "full")])
    table = _table(_entry("1", "Libertas", "in-copyright"))
    result = asyncio.run(RA.sync(conn, table, apply=False))
    assert [(c.before, c.after, c.reason) for c in result.changes] == [("full", "excerpt", "inventory")]
    assert result.totals == {"full": 0, "excerpt": 1}
    assert conn.updates == []


def test_a_status_change_flips_reader_access_on_the_next_sync():
    conn = FakeConn([_row("1", "Libertas", "full"), _row("2", "Rerum Novarum", "full")])
    blocked = _table(_entry("1", "Libertas", "unknown"),
                     _entry("2", "Rerum Novarum", "pd-us-pre-1931"))
    asyncio.run(RA.sync(conn, blocked, apply=True))
    assert [r["reader_access"] for r in conn.rows] == ["excerpt", "full"]

    # Permission granted and recorded: the next sync reopens it, nothing else moves.
    granted = _table(_entry("1", "Libertas", "permission"),
                     _entry("2", "Rerum Novarum", "pd-us-pre-1931"))
    result = asyncio.run(RA.sync(conn, granted, apply=True))
    assert [(c.title, c.after) for c in result.changes] == [("Libertas", "full")]
    assert [r["reader_access"] for r in conn.rows] == ["full", "full"]
    assert asyncio.run(RA.sync(conn, granted, apply=True)).changes == []


def test_sync_will_not_open_an_older_edition_under_its_replacements_row():
    # A re-sourced council keeps its ID; its row describes the new edition (1.2e).
    live = {**_row("1", "First Lateran Council", "excerpt"), "url": "https://old"}
    conn = FakeConn([live])
    table = _table(_entry("1", "First Lateran Council", "pd-us-non-renewal"))
    result = asyncio.run(RA.sync(conn, table, apply=True, urls={"1": "https://new"}))
    assert [(c.document_id, c.after, c.reason) for c in result.held] == \
        [("1", "excerpt", RA.OTHER_EDITION)]
    assert (result.changes, result.unmatched) == ([], [])
    assert result.totals == {"full": 0, "excerpt": 1}
    assert live["reader_access"] == "excerpt"


def test_sync_opens_the_new_edition_once_it_is_live():
    live = {**_row("1", "First Lateran Council", "excerpt"), "url": "https://new"}
    table = _table(_entry("1", "First Lateran Council", "pd-us-non-renewal"))
    result = asyncio.run(RA.sync(FakeConn([live]), table, apply=True,
                                 urls={"1": "https://new"}))
    assert result.held == [] and live["reader_access"] == "full"


def test_sync_closes_an_older_edition_already_open():
    live = {**_row("1", "First Lateran Council", "full"), "url": "https://old"}
    table = _table(_entry("1", "First Lateran Council", "pd-us-non-renewal"))
    result = asyncio.run(RA.sync(FakeConn([live]), table, apply=True, urls={"1": "https://new"}))
    assert [(c.before, c.after, c.reason) for c in result.changes] == \
        [("full", "excerpt", RA.OTHER_EDITION)]
    assert [c.document_id for c in result.held] == ["1"]
    assert result.unmatched == [] and live["reader_access"] == "excerpt"


def test_a_document_with_no_url_is_not_held():
    table = _table(_entry("1", "Isaiah", "pd-dedicated"))
    live = _row("1", "Isaiah", "excerpt")
    result = asyncio.run(RA.sync(FakeConn([live]), table, apply=True, urls={"1": "https://x"}))
    assert result.held == [] and live["reader_access"] == "full"


def test_a_closing_status_is_never_held():
    # The guard only stops an opening: an uncleared row still closes the live document.
    live = {**_row("1", "Libertas", "full"), "url": "https://old"}
    table = _table(_entry("1", "Libertas", "unknown"))
    asyncio.run(RA.sync(FakeConn([live]), table, apply=True, urls={"1": "https://new"}))
    assert live["reader_access"] == "excerpt"


@pytest.mark.parametrize("a,b,out", [("full", "full", "full"), ("full", "excerpt", "excerpt"),
                                     ("excerpt", "full", "excerpt"),
                                     ("excerpt", "excerpt", "excerpt")])
def test_stricter(a, b, out):
    assert RA.stricter(a, b) == out


def test_sync_keeps_a_relabelled_live_document_matched():
    # Live keeps a document's old label until the next publish; its row has the new one.
    conn = FakeConn([_row("1", "Fragments.", "full")])
    table = _table(_entry("1", "Fragments of Methodius", "pd-us-pre-1931"))
    result = asyncio.run(RA.sync(conn, table, apply=True))
    assert (result.changes, result.unmatched) == ([], [])


def test_apply_refuses_while_a_document_is_unmatched():
    # A live document with no row would be blocked silently, closing a public-domain text.
    conn = FakeConn([_row("1", "Libertas", "full"), _row("2", "Stray", "full")])
    table = _table(_entry("1", "Libertas", "pd-us-pre-1931"))

    dry = asyncio.run(RA.sync(conn, table, apply=False))
    assert [(c.title, c.reason) for c in dry.unmatched] == [("Stray", "no-row")]
    with pytest.raises(RA.UnmatchedDocuments):
        asyncio.run(RA.sync(conn, table, apply=True))
    assert conn.updates == []

    asyncio.run(RA.sync(conn, table, apply=True, allow_unmatched=True))
    assert [r["reader_access"] for r in conn.rows] == ["full", "excerpt"]
