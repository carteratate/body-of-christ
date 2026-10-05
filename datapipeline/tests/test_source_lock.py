"""source_lock.py against a temporary sources tree (item 0.2)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

import source_lock

COLLECTIONS = ["encyclicals", "summa"]


@pytest.fixture
def tree(tmp_path):
    sources = tmp_path / "sources"
    enc = sources / "encyclicals"
    enc.mkdir(parents=True)
    (enc / "rerum-novarum.html").write_text("<p>Rerum novarum</p>", encoding="utf-8")
    (enc / "humanae-vitae.html").write_text("<p>Humanae vitae</p>", encoding="utf-8")
    (enc / "stray.html").write_text("<p>not in the manifest</p>", encoding="utf-8")
    (enc / "manifest.json").write_text(json.dumps([
        {"file": "rerum-novarum.html", "url": "https://example.org/rn"},
        {"file": "humanae-vitae.html", "url": "https://example.org/hv"},
    ]), encoding="utf-8")
    (sources / "summa").mkdir()
    (sources / "summa" / "summa.xml").write_text("<ThML/>", encoding="utf-8")
    return sources, tmp_path / "source_lock.json"


def run(mode, sources, lock, *extra):
    return source_lock.main([mode, *extra], sources=sources, lock_path=lock,
                            collections=COLLECTIONS)


def test_write_then_verify_passes(tree, capsys):
    sources, lock = tree
    assert run("--write", sources, lock) == 0
    assert run("--verify", sources, lock) == 0
    out = capsys.readouterr().out
    assert "encyclicals: ok" in out and "summa: ok" in out


def test_roles_and_urls(tree):
    sources, lock = tree
    run("--write", sources, lock)
    by_path = {e["path"]: e for e in json.loads(lock.read_text())}
    assert by_path["encyclicals/rerum-novarum.html"]["role"] == "adapter-input"
    assert by_path["encyclicals/rerum-novarum.html"]["url"] == "https://example.org/rn"
    assert by_path["encyclicals/manifest.json"]["role"] == "adapter-auxiliary"
    stray = by_path["encyclicals/stray.html"]
    assert stray["role"] == "vendored-unregistered" and stray["note"]
    assert by_path["summa/summa.xml"]["role"] == "adapter-input"


def test_changed_byte_fails(tree, capsys):
    sources, lock = tree
    run("--write", sources, lock)
    path = sources / "encyclicals" / "rerum-novarum.html"
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(bytes(data))
    assert run("--verify", sources, lock) == 1
    assert "rerum-novarum.html: content differs" in capsys.readouterr().out


def test_deleted_file_fails(tree, capsys):
    sources, lock = tree
    run("--write", sources, lock)
    (sources / "summa" / "summa.xml").unlink()
    assert run("--verify", sources, lock) == 1
    assert "summa/summa.xml: locked, missing on disk" in capsys.readouterr().out


def test_unlocked_file_fails(tree, capsys):
    sources, lock = tree
    run("--write", sources, lock)
    (sources / "encyclicals" / "new.html").write_text("<p>new</p>", encoding="utf-8")
    assert run("--verify", sources, lock) == 1
    assert "encyclicals/new.html: on disk, not in source_lock.json" in capsys.readouterr().out


def test_output_sorted_and_stable(tree):
    sources, lock = tree
    run("--write", sources, lock)
    first = lock.read_bytes()
    run("--write", sources, lock)
    assert lock.read_bytes() == first
    entries = json.loads(first)
    keys = [(e["collection"], e["path"]) for e in entries]
    assert keys == sorted(keys)


def test_collection_write_keeps_other_collections(tree):
    sources, lock = tree
    run("--write", sources, lock)
    (sources / "summa" / "summa.xml").write_text("<ThML>changed</ThML>", encoding="utf-8")
    run("--write", sources, lock, "--collection", "encyclicals")
    summa = [e for e in json.loads(lock.read_text()) if e["collection"] == "summa"]
    assert len(summa) == 1
    assert run("--verify", sources, lock, "--collection", "encyclicals") == 0
    assert run("--verify", sources, lock, "--collection", "summa") == 1


def test_url_and_acquired_survive_rewrite(tree):
    sources, lock = tree
    run("--write", sources, lock)
    entries = json.loads(lock.read_text())
    for e in entries:
        if e["path"] == "summa/summa.xml":
            e["url"] = "https://example.org/summa"
            e["acquired"] = "2026-10-01"
    lock.write_text(json.dumps(entries), encoding="utf-8")
    run("--write", sources, lock)
    summa = next(e for e in json.loads(lock.read_text()) if e["path"] == "summa/summa.xml")
    assert summa["url"] == "https://example.org/summa"
    assert summa["acquired"] == "2026-10-01"


def test_vendor_manifest_write_updates_the_lock(tree, monkeypatch):
    import vendor_sources

    sources, lock = tree
    monkeypatch.setattr(source_lock, "SOURCES", sources)
    monkeypatch.setattr(source_lock, "LOCK_PATH", lock)
    monkeypatch.setattr(source_lock, "registered_collections", lambda: COLLECTIONS)
    vendor_sources._write_manifest(str(sources / "encyclicals"), [
        {"file": "rerum-novarum.html", "url": "https://example.org/rn"},
        {"file": "humanae-vitae.html", "url": "https://example.org/hv"},
    ])
    paths = {e["path"] for e in json.loads(lock.read_text())}
    assert "encyclicals/rerum-novarum.html" in paths
    assert not any(p.startswith("summa/") for p in paths)
    assert run("--verify", sources, lock, "--collection", "encyclicals") == 0


def by_path(lock):
    return {e["path"]: e for e in json.loads(lock.read_text())}


def test_hashed_on_kept_for_unchanged_files_only(tree):
    sources, lock = tree
    source_lock.write(sources, lock, COLLECTIONS, None, "2026-01-01")
    (sources / "summa" / "summa.xml").write_text("<ThML>v2</ThML>", encoding="utf-8")
    source_lock.write(sources, lock, COLLECTIONS, None, "2026-02-01")
    entries = by_path(lock)
    assert entries["encyclicals/rerum-novarum.html"]["hashed_on"] == "2026-01-01"
    assert entries["summa/summa.xml"]["hashed_on"] == "2026-02-01"


def test_acquired_for_new_and_changed_files(tree):
    sources, lock = tree
    source_lock.write(sources, lock, COLLECTIONS, None, "2026-01-01")
    assert by_path(lock)["summa/summa.xml"]["acquired"] == "unknown-before-2026-01-01"
    (sources / "encyclicals" / "rerum-novarum.html").write_text("<p>refetched</p>")
    source_lock.write(sources, lock, COLLECTIONS, "encyclicals", "2026-02-01", fetched=True)
    entries = by_path(lock)
    assert entries["encyclicals/rerum-novarum.html"]["acquired"] == "2026-02-01"
    assert entries["encyclicals/humanae-vitae.html"]["acquired"] == "unknown-before-2026-01-01"


def test_manifest_url_wins_over_the_old_lock(tree):
    sources, lock = tree
    run("--write", sources, lock)
    manifest = sources / "encyclicals" / "manifest.json"
    entries = json.loads(manifest.read_text())
    entries[0]["url"] = "https://example.org/new"
    manifest.write_text(json.dumps(entries))
    run("--write", sources, lock)
    assert by_path(lock)["encyclicals/rerum-novarum.html"]["url"] == "https://example.org/new"


def test_unregistered_directory_is_locked_and_checked(tree, capsys):
    sources, lock = tree
    (sources / "parked").mkdir()
    (sources / "parked" / "a.html").write_text("<p>a</p>")
    run("--write", sources, lock)
    entry = by_path(lock)["parked/a.html"]
    assert entry["role"] == "vendored-unregistered" and entry["note"]
    (sources / "parked" / "b.html").write_text("<p>b</p>")
    assert run("--verify", sources, lock) == 1
    assert "parked/b.html: on disk, not in source_lock.json" in capsys.readouterr().out


def test_new_unlocked_directory_fails_verify(tree, capsys):
    sources, lock = tree
    run("--write", sources, lock)
    (sources / "newdir").mkdir()
    (sources / "newdir" / "x.txt").write_text("x")
    assert run("--verify", sources, lock) == 1
    assert "newdir/x.txt: on disk, not in source_lock.json" in capsys.readouterr().out


def test_vanished_directory_fails_verify_and_write_drops_it(tree, capsys):
    sources, lock = tree
    (sources / "parked").mkdir()
    (sources / "parked" / "a.html").write_text("<p>a</p>")
    run("--write", sources, lock)
    (sources / "parked" / "a.html").unlink()
    (sources / "parked").rmdir()
    assert run("--verify", sources, lock) == 1
    assert "parked/a.html: locked, missing on disk" in capsys.readouterr().out
    run("--write", sources, lock)
    assert not any(p.startswith("parked/") for p in by_path(lock))


def test_unknown_collection_is_an_error(tree):
    sources, lock = tree
    with pytest.raises(SystemExit):
        run("--verify", sources, lock, "--collection", "nope")
