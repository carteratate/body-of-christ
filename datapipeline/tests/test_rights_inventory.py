"""The tracked rights inventory, rights_inventory.json (item 0.2)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import rights_inventory as R

ENTRIES = R.load()
# md5 of the sorted document IDs of a master build, joined with commas: the 421 live
# documents as of 0.2. A PR that changes the published document set updates it on purpose.
LIVE_DOCUMENT_IDS_MD5 = "2dc20fef77f1ebd5eb49224a4ea2813d"   # 437: 5.6b adds Teresa's Interior Castle and Life


def test_every_entry_has_required_fields_and_known_status():
    for entry in ENTRIES:
        # A closed set: an extra field is where reasoning would creep in.
        assert sorted(set(entry) - set(R.OPTIONAL_FIELDS)) == sorted(R.REQUIRED_FIELDS), \
            R.key(entry)
        assert entry["status"] in R.STATUSES, f"{R.key(entry)}: status {entry['status']!r}"


def test_other_editions_record_the_same_facts_and_a_known_status():
    rows = [e for e in ENTRIES if "also_from" in e]
    assert rows, "Lyons I lists Giles's Matthew Paris"
    for entry in rows:
        assert entry["also_from"] and entry["document_id"], R.key(entry)
        for edition in entry["also_from"]:
            assert sorted(edition) == sorted(R.ALSO_FROM_FIELDS), R.key(entry)
            assert edition["status"] in R.STATUSES, R.key(entry)
            assert edition["status"] != "pd-us-non-renewal" or all(
                (edition["renewal_search"] or {}).get(f) for f in R.RENEWAL_SEARCH_FIELDS)
            assert bool(edition["checked_by"]) == bool(edition["checked_on"]), R.key(entry)
            assert (R.SOURCES / edition["source_path"]).is_dir() or not R.SOURCES.is_dir()


def test_reader_access_takes_the_strictest_edition():
    from reader_access import EXCERPT, FULL, access_by_id

    row = {"document_id": "d", "status": "pd-us-pre-1931"}
    assert access_by_id([row]) == {"d": FULL}
    assert access_by_id([{**row, "also_from": [{"status": "pd-us-pre-1931"}]}]) == {"d": FULL}
    assert access_by_id([{**row, "also_from": [{"status": "in-copyright"}]}]) == {"d": EXCERPT}


def test_keys_unique_and_sorted():
    keys = [R.key(e) for e in ENTRIES]
    assert len(keys) == len(set(keys))
    sort_key = [(c, p, w, a or "") for c, p, w, a in keys]
    assert sort_key == sorted(sort_key)


def test_non_renewal_entries_record_a_complete_search():
    for entry in ENTRIES:
        if entry["status"] != "pd-us-non-renewal":
            continue
        search = entry["renewal_search"] or {}
        empty = [f for f in R.RENEWAL_SEARCH_FIELDS if not search.get(f)]
        assert not empty, f"{R.key(entry)}: renewal_search lacks {empty}"
        extra = set(search) - set(R.RENEWAL_SEARCH_FIELDS) - set(R.RENEWAL_SEARCH_OPTIONAL)
        assert not extra, f"{R.key(entry)}: renewal_search has {extra}"


def test_in_copyright_entries_name_the_rights_holder():
    for entry in ENTRIES:
        if entry["status"] == "in-copyright":
            assert entry["rights_holder"], f"{R.key(entry)}: no rights_holder"


# A corpus-cleanup item ID such as "1.2c", "5.4" or "5.1b.4".
PLANNED_FOR_ID = re.compile(r"^\d\.\d+[a-z]?(\.\d+)?$")


def test_planned_rows_name_the_ingesting_item():
    # A planned work (R6) names the corpus-cleanup item that will ingest it; a built
    # work has null.
    for entry in ENTRIES:
        planned = entry["planned_for"]
        assert planned is None or (
            isinstance(planned, str) and PLANNED_FOR_ID.match(planned)
        ), f"{R.key(entry)}: planned_for {planned!r}"


@pytest.mark.parametrize("value,ok", [("1.2c", True), ("5.4", True), ("5.1b.4", True),
                                      ("", False), (" 5.4", False), ("R6", False), ("5.6c-x", False)])
def test_planned_for_id_pattern(value, ok):
    assert bool(PLANNED_FOR_ID.match(value)) == ok


UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_built_rows_have_a_unique_document_id_and_planned_rows_none():
    # Rows are matched to documents by ID (reader_access), never by their labels.
    for entry in ENTRIES:
        if entry["planned_for"] is None:
            assert UUID.match(entry["document_id"] or ""), R.key(entry)
        else:
            assert entry["document_id"] is None, R.key(entry)
    ids = [e["document_id"] for e in ENTRIES if e["document_id"]]
    assert len(ids) == len(set(ids))


def test_approval_is_all_or_nothing():
    for entry in ENTRIES:
        assert bool(entry["checked_by"]) == bool(entry["checked_on"]), R.key(entry)


@pytest.mark.skipif(not (R.SOURCES / "bible").is_dir(),
                    reason="needs the gitignored datapipeline/sources/")
def test_inventory_matches_the_built_works_exactly():
    import hashlib

    from publication import SOURCE_ADAPTERS

    documents = {c: SOURCE_ADAPTERS[c]() for c in SOURCE_ADAPTERS}
    # The built document IDs (0.2 acceptance: the 421 live ones, and 1.8b's 14 new works):
    # the built inputs are the ones in use.
    ids = sorted(d.id for docs in documents.values() for d in docs)
    # A document held for permission (1.3d, ADR 0001) builds nothing; it is still live
    # until the apply, and its row stays for its return.
    import registry
    held = registry.removed_document_ids()
    assert hashlib.md5(",".join(sorted(set(ids) | held)).encode()).hexdigest() \
        == LIVE_DOCUMENT_IDS_MD5
    rows = R.by_document_id(ENTRIES)
    # Planned rows (R6) describe works not built yet and have no ID; the PR that builds
    # one clears its planned_for and fills in its document_id.
    assert sorted(set(ids) - set(rows)) == [], "built works with no inventory entry"
    # A registered work whose every passage the removal registry retires builds no
    # document until a later item restores its text (Asterius Urbanus: 1.8a removed its
    # one passage, an Elucidation; 1.8c parses his text). Its row stays.
    reg = registry.load_registry()
    by_doc: dict[str, set[str]] = {}
    for r in reg.passages:
        by_doc.setdefault(r["document_id"], set()).add(r["status"])
    emptied = {d for d, statuses in by_doc.items() if "active" not in statuses
               and "retired" in statuses}
    assert sorted(set(rows) - set(ids) - emptied - held) == [], \
        "inventory entries for works no longer built"
    # The readable fields follow the build, so a relabel updates its row in the same PR.
    built = {d.id: k for c, docs in documents.items()
             for d, k in zip(docs, R.work_keys({c: docs}))}
    stale = sorted((R.key(rows[i]), k) for i, k in built.items() if R.key(rows[i]) != k)
    assert stale == [], "inventory labels that differ from the build"
    assert len(set(built.values())) == len(built), "two built works share an inventory key"


def test_excerpt_basis_records_the_statement_and_its_conditions():
    rows = [e for e in ENTRIES if "excerpt_basis" in e]
    assert len(rows) >= 23, "1.3c's LEV rows carry the first basis"
    for entry in rows:
        basis = entry["excerpt_basis"]
        assert sorted(basis) == sorted(R.EXCERPT_BASIS_FIELDS), R.key(entry)
        # Excerpt-only: a cleared row needs no basis, and a basis is no clearance.
        assert entry["status"] == "in-copyright", R.key(entry)
        assert basis["statement"] and basis["wording"] and basis["conditions"], R.key(entry)
        assert basis["url"].startswith("https://"), R.key(entry)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", basis["read_on"]), R.key(entry)
        assert basis["word_limit"] is None or basis["word_limit"] > 0, R.key(entry)


def test_lev_rows_were_taken_from_vatican_va():
    # Decision log "LEV texts from vatican.va": the text is taken from vatican.va.
    for entry in ENTRIES:
        basis = entry.get("excerpt_basis") or {}
        if "Santa Sede" in basis.get("wording", ""):
            assert basis["source_host"] == "www.vatican.va", R.key(entry)
            assert entry["source_url"].startswith("https://www.vatican.va/"), R.key(entry)
            assert entry["rights_holder"] == "Libreria Editrice Vaticana", R.key(entry)


def test_excerpt_failures_hold_a_document_to_its_basis():
    from model import Document, Passage

    def doc(url, words):
        passage = Passage(content=" ".join(["word"] * words), reference="r", anchor="d/1",
                          chapter_key="d/c", chapter_label="c", position=0)
        return Document(id="d", collection="encyclicals", title="T", author="A",
                        metadata={"url": url}, passages=[passage])

    basis = {"word_limit": 100, "source_host": "www.vatican.va"}
    rows = [{"document_id": "d", "excerpt_basis": basis}]
    assert R.excerpt_failures([doc("https://www.vatican.va/x", 100)], rows) == []
    over = R.excerpt_failures([doc("https://www.vatican.va/x", 101)], rows)
    assert [(p.anchor, d) for _, p, d in over] == [("d/1", "101 words, over the basis's limit of 100")]
    elsewhere = R.excerpt_failures([doc("https://www.papalencyclicals.net/x", 5)], rows)
    assert [p for _, p, _ in elsewhere] == [None]
    assert R.excerpt_failures([doc("https://example.org/x", 500)],
                              [{"document_id": "d", "status": "unknown"}]) == []
