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


_HELD_PART = re.compile(r";\s*(?:the (?P<parts>introduction and closing)|(?P<address>the address)?"
                        r"(?: and |, )?(?:paragraphs? (?P<numbers>[\d–, and]+?))?) held for permission$")


def _numbers(text: str) -> list[str]:
    out = []
    for part in re.split(r",\s*|\s+and\s+", text.strip()):
        if "–" in part:
            a, b = part.split("–")
            out += [str(n) for n in range(int(a), int(b) + 1)]
        elif part:
            out.append(part)
    return out


def test_extracts_hold_exactly_what_the_adr_names():
    """A "Partial only" or "Abridged only" row names what is held; the registry holds
    exactly those passages, one `passage`-scope entry each (1.3d step 6)."""
    from ingest import papal_common

    works = _works()
    entries = [e for e in registry.open_removals(registry.current())
               if e["scope"] == "passage" and e["reason"] == "awaiting-permission"]
    rows = {s: o for s, o in _adr_rows().items() if o.startswith(("Partial only", "Abridged only"))}
    assert len(rows) == 11
    for slug, outcome in rows.items():
        held = {e["anchor"].split("/", 1)[1] for e in entries
                if e["document_id"] == works[slug]["document_id"]}
        assert held, slug
        for e in entries:
            if e["document_id"] == works[slug]["document_id"]:
                assert e["tombstone"] == TOMBSTONE and e["added_by"] == "1.3d", e["id"]
        m = _HELD_PART.search(outcome)
        assert m, slug
        if m.group("parts"):      # Exsurge Domine: every passage but the 41 propositions
            assert not any(a.isdigit() for a in held), slug
            continue
        expected = ({"preamble"} if m.group("address") else set()) | {
            papal_common._anchor(slug, n).split("/", 1)[1] for n in _numbers(m.group("numbers") or "")}
        assert {a.split("/")[0] for a in held} == expected, slug


def test_exsurge_domine_propositions_are_labelled_rejected():
    """Exsurge Domine is published only in its 41 condemned propositions, which are
    Deferrari's translation (R9): each row keeps its ID and says whose words they are."""
    doc = _works()["exsurge-domine"]["document_id"]
    rows = {r["anchor"]: r for r in registry.current().passages if r["document_id"] == doc}
    for n in range(1, 42):
        row = rows[f"exsurge-domine/{n}"]
        assert row["status"] == "active" and row.get("voice") == "rejected", n
        assert row.get("note", "").startswith("Propositions of Martin Luther that the bull "
                                              "condemned"), n
