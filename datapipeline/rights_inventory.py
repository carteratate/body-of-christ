"""The tracked rights inventory: one entry per published or planned work, in
`rights_inventory.json`.

Each entry records public facts only: edition, translator, first publication, source
URL, rights status, renewal search and credit line. Reasoning and correspondence stay
in Carter's private memos (plan, Decision log "Rights review").

A built work is found by `document_id`, its frozen document ID from the 2.1 registry,
which is the same in the live corpus and in every build. Labels change between releases
(1.10a trims "Methodius." to "Methodius"; 1.8c renames container authors), and the live
rows keep the old ones until the next publish, so matching on them would lose a work on
one side or the other (decided by Carter on 31 Oct 2026). `work` (the built document's
title), `author` and `source_path` (the file it is read from, relative to `sources/`, or
the directory for a work built from many files) stay for people to read, and a test
keeps them equal to the build. (collection, source_path, work, author) is still each
row's unique, sorted key: the author is part of it because one file can hold two works
with the same title (ANF volume 1 has Polycarp's and Ignatius's "Epistle to the
Philippians").

A planned work, not yet built, has `planned_for` set to the ID of the corpus-cleanup item
that will ingest it (for example "1.2c" or "5.6b"), its `source_path` is where the file
will be vendored, and its `document_id` is null until that PR builds it and fills it in.
`planned_for` is null for every built work. Planned rows come from R6.
Until its ingesting PR, an approved download sits at `sources/_incoming/<source_path>`;
the PR moves it there unchanged, so the row's `source_path` never changes.

Item 0.2 in docs/corpus-cleanup/P0-checks-identity-research.md.
"""
from __future__ import annotations

import json
from pathlib import Path

DATAPIPELINE = Path(__file__).resolve().parent
INVENTORY_PATH = DATAPIPELINE / "rights_inventory.json"
SOURCES = DATAPIPELINE / "sources"

STATUSES = (
    "pd-us-pre-1931",
    "pd-us-non-renewal",
    "pd-us-government",
    "pd-dedicated",
    "in-copyright",
    "permission",
    "licence",
    "unknown",
)

REQUIRED_FIELDS = (
    "work", "author", "collection", "source_path", "document_id", "edition", "translator", "first_published",
    "source_url", "status", "rights_holder", "renewal_search", "credit_line",
    "checked_by", "checked_on", "planned_for",
)

# Optional. A work whose document also holds texts from another edition lists each such
# edition here, with its own rights facts (Carter, 9 Nov 2026: Lyons I's bull and I 7 come
# from Giles's Matthew Paris, the rest from Schroeder). The row's own fields describe the
# edition most of the document comes from.
OPTIONAL_FIELDS = ("also_from", "excerpt_basis")
ALSO_FROM_FIELDS = (
    "texts", "edition", "translator", "first_published", "source_path", "source_url",
    "status", "renewal_search", "credit_line", "checked_by", "checked_on",
)

# Optional, on an excerpt-only (`in-copyright`) row: the published statement that allows
# the use without permission, and every condition or limit it sets (5.2; Decision log
# "Excerpt-only needs an allowed-use basis"). `word_limit` caps every passage's words and
# `source_host` names the site the text must be taken from; the release report checks
# both (`excerpt_failures`). The other conditions are kept as the statement words them.
# 1.3c records the first, for the LEV texts taken from vatican.va.
EXCERPT_BASIS_FIELDS = ("statement", "url", "wording", "read_on", "conditions", "word_limit",
                        "source_host")

RENEWAL_SEARCH_FIELDS = ("date", "where", "query", "result")
# Who ran the search, when it was not Carter. Optional.
RENEWAL_SEARCH_OPTIONAL = ("searched_by",)

# Works built from a whole directory, or from a file the document metadata does not name.
_COLLECTION_SOURCE = {
    "bible": "bible/eng-web-c_usfm/",
    "canon-law": "canon-law/",
    "catechism": "catechism/ccc.json",
}


def load(path: Path = INVENTORY_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def key(entry: dict) -> tuple[str, str, str, str | None]:
    return entry["collection"], entry["source_path"], entry["work"], entry["author"]


def statuses(entry: dict) -> list[str]:
    """The rights status of every edition a work's document draws on."""
    return [entry["status"]] + [e["status"] for e in entry.get("also_from", [])]


def by_document_id(entries: list[dict]) -> dict[str, dict]:
    """The built works' rows by document ID. Planned rows have none."""
    return {e["document_id"]: e for e in entries if e["document_id"]}


def _manifest_files_by_url(sources: Path, collection: str) -> dict[str, str]:
    path = sources / collection / "manifest.json"
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {e["url"]: e["file"] for e in entries if e.get("url") and e.get("file")}


def work_keys(documents_by_collection: dict[str, list],
              sources: Path = SOURCES) -> list[tuple[str, str, str, str | None]]:
    """The inventory key of every built document, which its row's labels must equal.
    Raises when a document's source cannot be resolved, so a new adapter cannot
    silently escape the inventory."""
    keys = []
    for collection, documents in sorted(documents_by_collection.items()):
        by_url = _manifest_files_by_url(sources, collection)
        for doc in documents:
            meta = doc.metadata or {}
            if meta.get("source_file"):
                path = f"{collection}/{meta['source_file']}"
            elif meta.get("url") in by_url:
                path = f"{collection}/{by_url[meta['url']]}"
            elif collection in _COLLECTION_SOURCE:
                path = _COLLECTION_SOURCE[collection]
            else:
                raise ValueError(f"{collection}: cannot resolve the source of {doc.title!r}")
            keys.append((collection, path, doc.title, doc.author))
    return keys


def excerpt_failures(documents: list, entries: list[dict]) -> list[tuple]:
    """(document, passage or None, detail) for each built document that breaks a limit
    of its row's `excerpt_basis`: a passage over `word_limit` words, or text taken from
    another site than `source_host`."""
    from urllib.parse import urlparse

    rows = by_document_id(entries)
    out = []
    for doc in documents:
        basis = (rows.get(doc.id) or {}).get("excerpt_basis")
        if not basis:
            continue
        host = basis.get("source_host")
        url = (doc.metadata or {}).get("url") or ""
        if host and urlparse(url).hostname != host:
            out.append((doc, None, f"its text is from {url or 'no URL'}, not {host}"))
        limit = basis.get("word_limit")
        if limit:
            longest = max(doc.passages, key=lambda p: len(p.content.split()), default=None)
            if longest is not None and len(longest.content.split()) > limit:
                out.append((doc, longest, f"{len(longest.content.split())} words, over the "
                                          f"basis's limit of {limit}"))
    return out
