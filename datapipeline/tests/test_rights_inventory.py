"""The tracked rights inventory, rights_inventory.json (item 0.2)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import rights_inventory as R

ENTRIES = R.load()


def test_every_entry_has_required_fields_and_known_status():
    for entry in ENTRIES:
        missing = [f for f in R.REQUIRED_FIELDS if f not in entry]
        assert not missing, f"{R.key(entry)}: missing {missing}"
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


def test_in_copyright_entries_name_the_rights_holder():
    for entry in ENTRIES:
        if entry["status"] == "in-copyright":
            assert entry["rights_holder"], f"{R.key(entry)}: no rights_holder"


def test_approval_is_all_or_nothing():
    for entry in ENTRIES:
        assert bool(entry["checked_by"]) == bool(entry["checked_on"]), R.key(entry)


@pytest.mark.skipif(not (R.SOURCES / "bible").is_dir(),
                    reason="needs the gitignored datapipeline/sources/")
def test_every_built_work_has_an_entry():
    from publication import SOURCE_ADAPTERS

    built = R.work_keys({c: SOURCE_ADAPTERS[c]() for c in SOURCE_ADAPTERS})
    assert len(built) == len(set(built)), "two built works share an inventory key"
    listed = {R.key(e) for e in ENTRIES}
    assert sorted(set(built) - listed) == []
