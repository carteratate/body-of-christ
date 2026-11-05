from dataclasses import replace

import pytest

from config import settings
import writers.qdrant as qd
from writers.qdrant import collection_filter


def test_collection_filter_targets_payload_collection():
    f = collection_filter("church-fathers")
    cond = f.must[0]
    assert cond.key == "collection"
    assert cond.match.value == "church-fathers"


def test_constants():
    assert settings.EMBEDDING_DIMS == 1536
    assert settings.QDRANT_LIVE_ALIAS == "chunks_live"


def test_write_collection_has_no_default(monkeypatch):
    monkeypatch.setattr(qd, "settings", replace(settings, QDRANT_WRITE_COLLECTION=None))
    with pytest.raises(SystemExit, match="QDRANT_WRITE_COLLECTION"):
        qd.write_collection()


def test_write_collection_is_the_one_named(monkeypatch):
    monkeypatch.setattr(qd, "settings", replace(settings, QDRANT_WRITE_COLLECTION="chunks-r1"))
    assert qd.write_collection() == "chunks-r1"
    assert qd.scan_collection() == "chunks-r1"


def test_a_dry_run_reads_what_users_search_when_nothing_is_named(monkeypatch):
    monkeypatch.setattr(qd, "settings", replace(settings, QDRANT_WRITE_COLLECTION=None))
    assert qd.scan_collection() == "chunks_live"
