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
    assert RA.access_by_key(R.load())


def _entry(work, status, collection="encyclicals", source_path=None):
    return {"collection": collection, "work": work, "author": "Pope Leo XIII",
            "source_path": source_path or f"{collection}/{work.lower()}.html",
            "status": status}


def _table(*entries):
    return RA.access_by_key(list(entries))


def test_access_matches_on_identity_not_title():
    # Two works share a title; the source file tells them apart.
    table = _table(_entry("Ubi Primum", "unknown", source_path="encyclicals/a.html"),
                   _entry("Ubi Primum", "pd-us-pre-1931", source_path="encyclicals/b.html"))
    get = lambda f: RA.access_for("encyclicals", "Ubi Primum", "Pope Leo XIII",
                                  {"source_file": f}, table)
    assert get("a.html") == RA.EXCERPT
    assert get("b.html") == RA.FULL


def test_a_document_with_no_inventory_row_is_excerpt_only():
    assert RA.access_for("encyclicals", "Nowhere", "Pope Leo XIII",
                         {"source_file": "nowhere.html"}, _table()) == RA.EXCERPT


def test_an_unresolvable_source_is_excerpt_only():
    assert RA.resolve("encyclicals", "X", None, {}, _table()) == (RA.EXCERPT, RA.UNRESOLVED)


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
    return {"id": id, "collection": "encyclicals", "title": work, "author": "Pope Leo XIII",
            "metadata": f'{{"source_file": "{work.lower()}.html"}}', "reader_access": access}


def test_sync_dry_run_reports_without_writing():
    conn = FakeConn([_row("1", "Libertas", "full")])
    table = _table(_entry("Libertas", "in-copyright"))
    result = asyncio.run(RA.sync(conn, table, apply=False))
    assert [(c.before, c.after, c.reason) for c in result.changes] == [("full", "excerpt", "inventory")]
    assert result.totals == {"full": 0, "excerpt": 1}
    assert conn.updates == []


def test_a_status_change_flips_reader_access_on_the_next_sync():
    conn = FakeConn([_row("1", "Libertas", "full"), _row("2", "Rerum Novarum", "full")])
    blocked = _table(_entry("Libertas", "unknown"), _entry("Rerum Novarum", "pd-us-pre-1931"))
    asyncio.run(RA.sync(conn, blocked, apply=True))
    assert [r["reader_access"] for r in conn.rows] == ["excerpt", "full"]

    # Permission granted and recorded: the next sync reopens it, nothing else moves.
    granted = _table(_entry("Libertas", "permission"), _entry("Rerum Novarum", "pd-us-pre-1931"))
    result = asyncio.run(RA.sync(conn, granted, apply=True))
    assert [(c.title, c.after) for c in result.changes] == [("Libertas", "full")]
    assert [r["reader_access"] for r in conn.rows] == ["full", "full"]
    assert asyncio.run(RA.sync(conn, granted, apply=True)).changes == []


def test_apply_refuses_while_a_document_is_unmatched():
    # Without datapipeline/sources/, a document resolved through a manifest cannot be
    # matched; blocking it silently would close a public-domain text.
    conn = FakeConn([_row("1", "Libertas", "full"), _row("2", "Stray", "full")])
    table = _table(_entry("Libertas", "pd-us-pre-1931"))

    dry = asyncio.run(RA.sync(conn, table, apply=False))
    assert [(c.title, c.reason) for c in dry.unmatched] == [("Stray", "no-row")]
    with pytest.raises(RA.UnmatchedDocuments):
        asyncio.run(RA.sync(conn, table, apply=True))
    assert conn.updates == []

    asyncio.run(RA.sync(conn, table, apply=True, allow_unmatched=True))
    assert [r["reader_access"] for r in conn.rows] == ["full", "excerpt"]
