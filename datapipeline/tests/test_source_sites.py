"""About › Sources (corpus cleanup 4.4): its data is generated from the rights inventory."""
import json

import pytest

import registry
from scripts import source_sites


def _rows():
    with open(source_sites.INVENTORY, encoding="utf-8") as f:
        return json.load(f)


def test_the_web_json_is_what_the_script_writes():
    with open(source_sites.OUTPUT, encoding="utf-8") as f:
        assert f.read() == source_sites.render(), \
            "run python3 scripts/source_sites.py and commit apps/web/src/lib/source-sites.json"


def test_every_published_document_is_listed_under_its_site():
    held = registry.removed_document_ids()
    data = source_sites.build(_rows(), held)
    listed = {d["document_id"] for s in data["sites"] for d in s["documents"]}
    published = {r["document_id"] for r in _rows()
                 if not r["planned_for"] and r["document_id"] and r["document_id"] not in held}
    assert listed == published
    assert not listed & held


def test_the_sites_the_spec_names_are_listed():
    keys = [s["key"] for s in source_sites.build(_rows(), registry.removed_document_ids())["sites"]]
    assert set(keys) >= {"ccel", "ebible", "vatican", "papalencyclicals", "wikisource",
                         "archive", "usccb"}


def test_the_catechism_is_listed_under_the_usccb():
    data = source_sites.build(_rows(), registry.removed_document_ids())
    usccb = next(s for s in data["sites"] if s["key"] == "usccb")
    assert [d["title"] for d in usccb["documents"]] == ["Catechism of the Catholic Church"]


def test_a_site_or_status_with_no_wording_stops_the_build():
    row = {"work": "W", "collection": "c", "document_id": "d", "planned_for": None,
           "source_url": "https://example.org/x", "status": "pd-us-pre-1931"}
    with pytest.raises(ValueError, match="example.org"):
        source_sites.build([row], set())
    row = {**row, "source_url": "https://ccel.org/x", "status": "unknown"}
    with pytest.raises(ValueError, match="no Sources page basis"):
        source_sites.build([row], set())
