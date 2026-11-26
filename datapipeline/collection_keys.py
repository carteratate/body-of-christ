"""Collection keys before and after corpus cleanup 5.1b.3 (issue #200).

The publish that carries 5.1b.3 writes the new keys into `documents.collection` and the
Qdrant payload. Until it is applied, live rows carry the old keys, so a stage, a release
report or an apply that covers a new key also reads the live rows filed under each old
key that becomes it, and reads them as the new key (`canonical`). The web's mirror,
kept for keys a browser still holds, is `LEGACY_COLLECTIONS` in
`apps/web/src/lib/collections.ts`, which also knows which genres each old papal key
read; here only the key matters. (The API's was removed in 5.1b.4.)

The work registry keeps the old keys: `works.json` and `passages/<key>.jsonl` file each
frozen ID under the collection it was frozen in (2.1), and adapters look IDs up there,
so no ID moves. Only the collection a document is published under changes.
"""
from __future__ import annotations

from collections.abc import Iterable

# Old key → new key. The three papal collections merge; the other two are renamed.
RENAMES: dict[str, str] = {
    "encyclicals": "papal",
    "apostolic-exhortations": "papal",
    "papal-documents": "papal",
    "canon-law": "church-law",
    "medieval": "theologians",
}


def canonical(key: str) -> str:
    """The key a collection is published under: an old key's new one, any other as is."""
    return RENAMES.get(key, key)


def live_keys(collections: Iterable[str]) -> list[str]:
    """The stored keys a publish of `collections` covers in live: each collection and
    every old key that becomes one of them, sorted."""
    wanted = set(collections)
    return sorted(wanted | {old for old, new in RENAMES.items() if new in wanted})


def old_keys(collection: str) -> list[str]:
    """The old keys that become `collection`, in a fixed order."""
    return [old for old, new in RENAMES.items() if new == collection]


def source_of(document_id: str, collection: str, registry=None) -> str:
    """The source a document is built from (`datapipeline/sources/<key>/`): the collection
    its registry entry was frozen under, which 5.1b.3 does not change, or its own
    collection when it is unregistered. Checks, known defects and the embedding overlap
    follow the source, so the rename changes no check id and no vector."""
    import registry as reg

    entry = (registry or reg.current()).entry_by_document.get(document_id)
    return entry["collection"] if entry else collection
