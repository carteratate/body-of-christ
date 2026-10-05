"""The tracked rights inventory, rights_inventory.json (item 0.2)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import rights_inventory as R

ENTRIES = R.load()
# md5 of the sorted document IDs of a master build, joined with commas: the 421 live
# documents as of 0.2. A PR that changes the published document set updates it on purpose.
LIVE_DOCUMENT_IDS_MD5 = "851d07063f85e4c612be1b2d44b695fb"


def test_every_entry_has_required_fields_and_known_status():
    for entry in ENTRIES:
        # A closed set: an extra field is where reasoning would creep in.
        assert sorted(entry) == sorted(R.REQUIRED_FIELDS), R.key(entry)
        assert entry["status"] in R.STATUSES, f"{R.key(entry)}: status {entry['status']!r}"


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


def test_planned_rows_name_the_ingesting_item():
    # A planned work (R6) names the corpus-cleanup item that will ingest it; a built
    # work has null.
    for entry in ENTRIES:
        planned = entry["planned_for"]
        assert planned is None or (isinstance(planned, str) and planned.strip()), R.key(entry)


def test_approval_is_all_or_nothing():
    for entry in ENTRIES:
        assert bool(entry["checked_by"]) == bool(entry["checked_on"]), R.key(entry)


@pytest.mark.skipif(not (R.SOURCES / "bible").is_dir(),
                    reason="needs the gitignored datapipeline/sources/")
def test_inventory_matches_the_built_works_exactly():
    import hashlib

    from publication import SOURCE_ADAPTERS

    documents = {c: SOURCE_ADAPTERS[c]() for c in SOURCE_ADAPTERS}
    # The 421 live document IDs (0.2 acceptance): the built inputs are the ones in use.
    ids = sorted(d.id for docs in documents.values() for d in docs)
    assert hashlib.md5(",".join(ids).encode()).hexdigest() == LIVE_DOCUMENT_IDS_MD5
    built = R.work_keys(documents)
    assert len(built) == len(set(built)), "two built works share an inventory key"
    listed = {R.key(e) for e in ENTRIES}
    assert sorted(set(built) - listed) == [], "built works with no inventory entry"
    # Planned rows (R6) describe works not built yet, so only built-work rows can be stale.
    listed_built = {R.key(e) for e in ENTRIES if e["planned_for"] is None}
    assert sorted(listed_built - set(built)) == [], "inventory entries for works no longer built"
    # The PR that builds a planned work clears its planned_for.
    assert sorted(set(built) - listed_built) == [], "built works whose entry is still planned"
