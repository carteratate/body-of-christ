"""The tracked rights inventory: one entry per published or planned work, in
`rights_inventory.json`.

Each entry records public facts only: edition, translator, first publication, source
URL, rights status, renewal search and credit line. Reasoning and correspondence stay
in Carter's private memos (plan, Decision log "Rights review").

Until the 2.1 work registry exists, a work is keyed by (collection, source_path, work,
author): `work` is the built document's title, `source_path` the file it is read from,
relative to `sources/` (or the directory, for a work built from many files). The author
is part of the key because one file can hold two works with the same title: ANF volume 1
has both Polycarp's and Ignatius's "Epistle to the Philippians".

A planned work, not yet built, has `planned_for` set to the ID of the corpus-cleanup item
that will ingest it (for example "1.2c" or "5.6b"), and its `source_path` is where the file
will be vendored. `planned_for` is null for every built work. Planned rows come from R6.
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
    "work", "author", "collection", "source_path", "edition", "translator", "first_published",
    "source_url", "status", "rights_holder", "renewal_search", "credit_line",
    "checked_by", "checked_on", "planned_for",
)

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


def _manifest_files_by_url(sources: Path, collection: str) -> dict[str, str]:
    path = sources / collection / "manifest.json"
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {e["url"]: e["file"] for e in entries if e.get("url") and e.get("file")}


def work_keys(documents_by_collection: dict[str, list],
              sources: Path = SOURCES) -> list[tuple[str, str, str, str | None]]:
    """The inventory key of every built document. Raises when a document's source
    cannot be resolved, so a new adapter cannot silently escape the inventory."""
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
