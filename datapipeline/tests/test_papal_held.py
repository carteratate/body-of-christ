"""1.3d: older papal documents held for permission (ADR 0001).

ADR 0001's table is the record of each document's outcome; the removal registry is the
machine record. These tests hold the two together.
"""
import json
import os
import re

import registry

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADR = os.path.join(_ROOT, "docs", "adr", "0001-retire-papal-documents-without-public-domain-english.md")
_ROW = re.compile(r"^\| (\d{4}) \| ([^|]+?) \| ([^|]+?) \| `([a-z0-9-]+)` \| (.+?) \|$", re.M)
HELD = "**Held for permission**"
TOMBSTONE = "This translation is not available on TheoCorpus at present."


def _adr_rows() -> dict[str, str]:
    with open(ADR, encoding="utf-8") as f:
        return {m.group(4): m.group(5) for m in _ROW.finditer(f.read())}


def _works() -> dict[str, dict]:
    return {w["work_id"].split("/", 1)[1]: w for w in registry.current().works
            if w["collection"] in ("encyclicals", "papal-documents", "apostolic-exhortations")}


def _held_entries() -> list[dict]:
    return [e for e in registry.open_removals(registry.current())
            if e["scope"] == "document" and e["reason"] == "awaiting-permission"
            and e["collection"] in ("encyclicals", "papal-documents", "apostolic-exhortations")]


def test_adr_table_has_every_document_once():
    rows = _adr_rows()
    assert len(rows) == 87     # R8's 85, with Haerent Animo and Menti Nostrae from 1.3c
    works = _works()
    assert set(rows) <= set(works), sorted(set(rows) - set(works))


def test_held_documents_are_exactly_the_document_entries():
    works = _works()
    held = {works[s]["document_id"] for s, outcome in _adr_rows().items() if outcome == HELD}
    entries = _held_entries()
    assert {e["document_id"] for e in entries} == held
    assert len(entries) == len(held)


def test_held_entries_carry_the_notice():
    for e in _held_entries():
        assert e["tombstone"] == TOMBSTONE, e["id"]
        assert e["added_by"] == "1.3d", e["id"]
        assert e["anchor"] is None and e["passage_id"] is None, e["id"]


def test_held_documents_keep_their_unknown_rights_rows():
    """The text can return unchanged on permission, so the row keeps its source (ADR 0001)."""
    path = os.path.join(_ROOT, "datapipeline", "rights_inventory.json")
    with open(path, encoding="utf-8") as f:
        rows = {r["document_id"]: r for r in json.load(f) if r.get("document_id")}
    for e in _held_entries():
        row = rows[e["document_id"]]
        assert row["status"] == "unknown", row["work"]
        assert "papalencyclicals.net" in row["source_url"], row["work"]
