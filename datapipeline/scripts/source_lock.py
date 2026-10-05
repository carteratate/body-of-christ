"""Pin every vendored source file by hash in the tracked `source_lock.json`.

The vendored files under `sources/` are gitignored, so without this a later build can
not prove it read the same inputs. `--write` hashes every file under each registered
collection's directory (and records unregistered vendored files as such); `--verify`
re-hashes and fails on a missing file, a changed hash, or a file the lock does not
list.

    python3 scripts/source_lock.py --verify
    python3 scripts/source_lock.py --write --collection encyclicals

Item 0.2 in docs/corpus-cleanup/P0-checks-identity-research.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

DATAPIPELINE = Path(__file__).resolve().parents[1]
SOURCES = DATAPIPELINE / "sources"
LOCK_PATH = DATAPIPELINE / "source_lock.json"

# Files vendored before this lock existed carry no fetch date.
UNKNOWN_ACQUIRED = "unknown-before-2026-09-29"

# Each collection's manifest, which also supplies URLs.
_MANIFESTS = {
    "apostolic-exhortations": "manifest.json",
    "canon-law": "pages.json",
    "church-fathers": "manifest.json",
    "councils": "manifest.json",
    "encyclicals": "manifest.json",
    "medieval": "manifest.json",
    "papal-documents": "manifest.json",
}

# Collections whose adapter selects files by globbing the directory, not by reading the
# manifest: `ingest/church_fathers.build_all()` builds every `*.xml` except a file named
# `summa.xml`. Its manifest is then only a record of URLs, and a file dropped from it is
# still published. Every other collection in `_MANIFESTS` builds exactly what its
# manifest names.
_GLOB_SELECTED = {
    "church-fathers": lambda name: name.endswith(".xml") and name != "summa.xml",
}

# Collections without a manifest: the provenance SOURCES.md records in prose.
_UNMANIFESTED_URLS = {
    "bible/eng-web-c_usfm/": "https://ebible.org/Scriptures/eng-web-c_usfm.zip",
    "catechism/ccc.json": "https://github.com/nossbigg/catechism-ccc-json",
    # Both confirmed on 4 Oct 2026 by downloading the URL and matching the locked sha256.
    "bible/PericopeGroupedKJVVerses.json":
        "https://huggingface.co/datasets/JWBickel/KJV_Pericopes/resolve/main/"
        "PericopeGroupedKJVVerses.json",
    "summa/summa.xml": "https://ccel.org/ccel/a/aquinas/summa.xml",
}

# Vendored files no registered adapter publishes, with the reason on record.
_UNREGISTERED_NOTES = {
    "apostolic-exhortations/a-new-hope-for-lebanon.html": "scheduled for PR 5.4",
    "papal-documents/ubicumque-et-semper.html": "scheduled for PR 5.4",
    "apostolic-exhortations/amoris-laetitia.html":
        "not published; scheduled for PR 5.4 (Carter, 4 Oct 2026)",
}
_UNREGISTERED_DIR_NOTES = {
    "roman-curia": "parked for 5.3 (branch feat/roman-curia-collection)",
}

ROLES = ("adapter-input", "adapter-auxiliary", "vendored-unregistered")


def registered_collections() -> list[str]:
    sys.path.insert(0, str(DATAPIPELINE))
    from publication import SOURCE_ADAPTERS

    return sorted(SOURCE_ADAPTERS)


def _sha256(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.name != ".DS_Store")


def _manifest_index(sources: Path, collection: str) -> tuple[str | None, dict[str, dict]]:
    name = _MANIFESTS.get(collection)
    if name is None:
        return None, {}
    path = sources / collection / name
    if not path.exists():
        return name, {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return name, {e["file"]: e for e in entries if isinstance(e, dict) and e.get("file")}


def _role_and_url(sources: Path, collection: str, rel: str,
                  manifest_name: str | None, named: dict[str, dict]) -> tuple[str, str | None]:
    """Classify one file of a registered collection."""
    file_in_collection = rel.split("/", 1)[1]
    selects = _GLOB_SELECTED.get(collection)
    if selects is not None:
        url = named.get(file_in_collection, {}).get("url")
        if file_in_collection == manifest_name:
            return "adapter-auxiliary", None
        if "/" not in file_in_collection and selects(file_in_collection):
            return "adapter-input", url
        return "vendored-unregistered", url
    if manifest_name is not None:
        if file_in_collection == manifest_name:
            return "adapter-auxiliary", None
        if file_in_collection in named:
            return "adapter-input", named[file_in_collection].get("url")
        return "vendored-unregistered", None
    if collection == "bible":
        url = (_UNMANIFESTED_URLS["bible/eng-web-c_usfm/"] if "/eng-web-c_usfm/" in rel
               else _UNMANIFESTED_URLS.get(rel))
        return ("adapter-input" if rel.endswith(".usfm") else "adapter-auxiliary"), url
    return "adapter-input", _UNMANIFESTED_URLS.get(rel)


def build_entries(sources: Path, registered: list[str], scope: set[str],
                  previous: dict[str, dict], today: str, fetched: bool = False) -> list[dict]:
    """One entry per file under each directory in `scope`: registered collections are
    classified by role, unregistered vendored directories recorded as such.

    A manifest URL wins over the previous lock's; the previous URL survives only where
    no manifest names one. `acquired` and `hashed_on` carry over for an unchanged file.
    A new or changed file was acquired today when `fetched` (vendor_sources just
    downloaded it), and at an unknown date before today otherwise."""
    entries: list[dict] = []
    for name in sorted(scope):
        directory = sources / name
        if not directory.is_dir():
            continue
        if name in registered:
            manifest_name, named = _manifest_index(sources, name)
        for path in _files(directory):
            rel = path.relative_to(sources).as_posix()
            if name in registered:
                role, url = _role_and_url(sources, name, rel, manifest_name, named)
                entries.append(_entry(name, rel, path, role, url, previous, today, fetched))
            else:
                entries.append(_entry(name, rel, path, "vendored-unregistered", None,
                                      previous, today, fetched,
                                      note=_UNREGISTERED_DIR_NOTES.get(name,
                                                                       "directory of no registered collection")))
    return sorted(entries, key=lambda e: (e["collection"], e["path"]))


def _entry(collection: str, rel: str, path: Path, role: str, url: str | None,
           previous: dict[str, dict], today: str, fetched: bool = False,
           note: str | None = None) -> dict:
    sha, size = _sha256(path)
    old = previous.get(rel, {})
    unchanged = old.get("sha256") == sha
    if unchanged:
        acquired = old.get("acquired") or UNKNOWN_ACQUIRED
    else:
        acquired = today if fetched else f"unknown-before-{today}"
    entry = {
        "collection": collection,
        "path": rel,
        "sha256": sha,
        "bytes": size,
        "url": url or old.get("url"),
        "acquired": acquired,
        "hashed_on": old.get("hashed_on") if unchanged else today,
        "role": role,
    }
    note = note or _UNREGISTERED_NOTES.get(rel)
    if role == "vendored-unregistered":
        entry["note"] = note or "on disk, not read by the collection's adapter"
    return entry


def load_lock(path: Path = LOCK_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_lock(entries: list[dict], path: Path = LOCK_PATH) -> None:
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _scope(sources: Path, registered: list[str], locked: list[dict],
           only: str | None) -> set[str]:
    """`only`, or else every directory under `sources/`, every registered collection and
    every collection the lock names, so neither a new directory nor a vanished one can
    pass unnoticed."""
    if only:
        return {only}
    on_disk = {p.name for p in sources.iterdir() if p.is_dir()} if sources.is_dir() else set()
    return on_disk | set(registered) | {e["collection"] for e in locked}


def write(sources: Path, lock_path: Path, registered: list[str], only: str | None,
          today: str, fetched: bool = False) -> list[dict]:
    existing = load_lock(lock_path)
    scope = _scope(sources, registered, existing, only)
    fresh = build_entries(sources, registered, scope, {e["path"]: e for e in existing},
                          today, fetched)
    kept = [e for e in existing if e["collection"] not in scope]
    merged = sorted(kept + fresh, key=lambda e: (e["collection"], e["path"]))
    write_lock(merged, lock_path)
    return merged


def verify(sources: Path, lock_path: Path, registered: list[str],
           only: str | None) -> dict[str, list[str]]:
    """Problems per collection: missing files, changed hashes, unlocked files."""
    lock = load_lock(lock_path)
    scope = _scope(sources, registered, lock, only)
    locked = [e for e in lock if e["collection"] in scope]
    problems: dict[str, list[str]] = {c: [] for c in sorted(scope)}
    for collection in sorted(scope):
        if collection in registered and not (sources / collection).is_dir():
            problems[collection].append(f"{collection}/: registered collection, no directory")
    by_path = {e["path"]: e for e in locked}
    for entry in locked:
        path = sources / entry["path"]
        if not path.is_file():
            problems[entry["collection"]].append(f"{entry['path']}: locked, missing on disk")
        elif _sha256(path)[0] != entry["sha256"]:
            problems[entry["collection"]].append(f"{entry['path']}: content differs from the lock")
    for collection in sorted(scope):
        directory = sources / collection
        if not directory.is_dir():
            continue
        for path in _files(directory):
            rel = path.relative_to(sources).as_posix()
            if rel not in by_path:
                problems[collection].append(f"{rel}: on disk, not in source_lock.json")
    return problems


def main(argv: list[str] | None = None, *, sources: Path = SOURCES,
         lock_path: Path = LOCK_PATH, collections: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="hash the files and rewrite the lock")
    mode.add_argument("--verify", action="store_true", help="re-hash and compare with the lock")
    ap.add_argument("--collection", help="limit to one collection directory")
    args = ap.parse_args(argv)
    collections = collections if collections is not None else registered_collections()
    known = _scope(sources, collections, load_lock(lock_path), None)
    if args.collection and args.collection not in known:
        ap.error(f"unknown collection {args.collection!r}; valid: {', '.join(sorted(known))}")

    if args.write:
        entries = write(sources, lock_path, collections, args.collection, date.today().isoformat())
        counts = {r: sum(1 for e in entries if e["role"] == r) for r in ROLES}
        print(f"source_lock.json: {len(entries)} entries "
              + ", ".join(f"{n} {r}" for r, n in counts.items()))
        return 0

    problems = verify(sources, lock_path, collections, args.collection)
    for collection, found in problems.items():
        if found:
            print(f"== {collection} ==")
            for problem in found:
                print(f"  ✗ {problem}")
        else:
            print(f"{collection}: ok")
    return 1 if any(problems.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
