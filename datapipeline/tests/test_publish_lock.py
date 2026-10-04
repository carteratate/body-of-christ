import json

import pytest

from publish_lock import (
    DEFAULT_PATH,
    PublishLocked,
    WriteTargets,
    assert_live_write_allowed,
    load_lock,
)

REMOTE = WriteTargets(
    database_url="postgresql://user:pw@db.example.supabase.co:5432/postgres",
    qdrant_url="https://cluster.example.qdrant.io:6333",
)


def _lock_file(tmp_path, entries):
    path = tmp_path / "PUBLISH_LOCK.json"
    path.write_text(json.dumps({"since": "2026-10-04", "reason": "test lock",
                                "approved_applies": entries}))
    return path


def _entry(collection="councils", release="2026-11-cleanup", steps=("stage", "apply", "rollback")):
    return {"collection": collection, "release": release, "steps": list(steps),
            "reason": "test", "approved_by": "Carter", "pr": "1"}


def _check(lock_path, collection="councils", release="2026-11-cleanup", step="apply",
           targets=REMOTE):
    assert_live_write_allowed("publish councils to both", collection, release, step,
                              lock=load_lock(lock_path), targets=targets)


def test_missing_lock_file_counts_as_empty(tmp_path):
    assert load_lock(tmp_path / "absent.json").entries == ()
    with pytest.raises(PublishLocked):
        _check(tmp_path / "absent.json")


def test_unparsable_lock_file_counts_as_empty(tmp_path):
    path = tmp_path / "PUBLISH_LOCK.json"
    for text in ("{not json", "[]", '{"approved_applies": "councils"}', "{}"):
        path.write_text(text)
        assert load_lock(path).entries == ()
        with pytest.raises(PublishLocked):
            _check(path)


def test_empty_list_refuses_every_write_even_with_flags(tmp_path):
    path = _lock_file(tmp_path, [])
    for step in ("stage", "apply", "rollback", "repair"):
        for collection in ("councils", "all"):
            with pytest.raises(PublishLocked, match="locked"):
                _check(path, collection=collection, step=step)


def test_refuses_without_release(tmp_path):
    path = _lock_file(tmp_path, [_entry()])
    for release in (None, ""):
        with pytest.raises(PublishLocked):
            _check(path, release=release)


def test_refuses_wrong_release(tmp_path):
    path = _lock_file(tmp_path, [_entry()])
    with pytest.raises(PublishLocked):
        _check(path, release="2026-12-cleanup")


def test_listed_release_refuses_other_collection(tmp_path):
    path = _lock_file(tmp_path, [_entry()])
    with pytest.raises(PublishLocked):
        _check(path, collection="medieval")


def test_listed_entry_refuses_step_it_does_not_name(tmp_path):
    path = _lock_file(tmp_path, [_entry(steps=["stage"])])
    _check(path, step="stage")
    with pytest.raises(PublishLocked):
        _check(path, step="apply")


def test_matching_collection_release_and_step_pass(tmp_path):
    path = _lock_file(tmp_path, [_entry()])
    for step in ("stage", "apply", "rollback"):
        _check(path, step=step)


def test_all_entry_is_needed_for_all_collections(tmp_path):
    path = _lock_file(tmp_path, [_entry()])
    with pytest.raises(PublishLocked):
        _check(path, collection="all")
    _check(_lock_file(tmp_path, [_entry(collection="all")]), collection="all")


def test_rollback_step_is_its_own_permission(tmp_path):
    path = _lock_file(tmp_path, [_entry(steps=["stage", "apply"])])
    with pytest.raises(PublishLocked):
        _check(path, step="rollback")


def test_loopback_database_and_qdrant_pass_without_entry(tmp_path):
    path = _lock_file(tmp_path, [])
    for db, qdrant in [
        ("postgresql://postgres:pw@localhost:54322/postgres", "http://localhost:6333"),
        ("postgresql://postgres@127.0.0.1/postgres", "http://127.0.0.1:6333"),
        ("postgresql://postgres@[::1]:5432/postgres", "http://[::1]:6333"),
    ]:
        _check(path, release=None, targets=WriteTargets(db, qdrant))


def test_one_remote_target_is_refused(tmp_path):
    path = _lock_file(tmp_path, [])
    local_db = "postgresql://postgres@localhost/postgres"
    local_qdrant = "http://localhost:6333"
    for targets in (WriteTargets(local_db, REMOTE.qdrant_url),
                    WriteTargets(REMOTE.database_url, local_qdrant),
                    WriteTargets("", local_qdrant),
                    WriteTargets("postgresql:///postgres?host=/tmp", local_qdrant),
                    WriteTargets("postgresql://u:p@[::1]:5432,db.example.supabase.co:5432/postgres",
                                 local_qdrant),
                    WriteTargets("postgresql://u:p@localhost:5432,db.example.com:5432/postgres",
                                 local_qdrant),
                    WriteTargets("postgresql://localhost/postgres?host=db.example.com", local_qdrant),
                    WriteTargets("postgresql://localhost/postgres?hostaddr=10.0.0.5", local_qdrant),
                    WriteTargets(local_db, "http://localhost:6333,q.example.qdrant.io:6333")):
        with pytest.raises(PublishLocked):
            _check(path, targets=targets)


def test_no_environment_bypass(tmp_path, monkeypatch):
    path = _lock_file(tmp_path, [])
    for name in ("PUBLISH_LOCK", "PUBLISH_LOCK_BYPASS", "FORCE", "CI",
                 "ALLOW_LIVE_WRITES", "DATAPIPELINE_UNLOCK"):
        monkeypatch.setenv(name, "1")
    with pytest.raises(PublishLocked):
        _check(path)


def test_unknown_step_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown publish-lock step"):
        _check(_lock_file(tmp_path, [_entry()]), step="publish")


def test_repository_ships_with_no_approved_applies():
    data = json.loads(DEFAULT_PATH.read_text())
    assert data["approved_applies"] == []
    assert load_lock().entries == ()
