"""Reader access: whether a document's full text is offered in the reader (issue #265).

`documents.reader_access` (migration 0041) is derived from the rights inventory and
never edited by hand:

  full     the work's status is a `pd-*` status, `permission` or `licence`
  excerpt  `in-copyright` or `unknown`, and any document with no inventory row

An excerpt-only document keeps its passages in search; the API refuses its reader and
contents, and the frontend links to the official source instead.

Two writers keep the column current. A publish's stage sets it from the inventory in
`staging.documents` (`reader_writer.write_staged_document`), so a republish cannot
reopen an uncleared text. `sync` resets every live
document from the inventory, which is how a document is unblocked without a republish:
record the new status (a public-domain source, or `permission` with grantor, date and
scope) in `rights_inventory.json`, then run

    python3 reader_access.py            # dry run: lists what would change, and totals
    python3 reader_access.py --apply    # writes the changes (live data)

Documents are matched to inventory rows by document ID, never by title or author, so a
relabel waiting for the next publish cannot unmatch a live document. `--apply` refuses
while any live document has no row: falling closed is right for a publish, but here it
would silently block a public-domain text.

A row describes the edition a build publishes, and the document ID outlives an edition: a
re-sourced work keeps its ID. So `sync` makes a document excerpt-only, whatever it is now,
when its live `metadata.url` differs from its row's `source_url`: the live text is still
the older edition, and its replacement's status does not cover it. Such a document is
listed as held and opens with the publish that brings the new edition. A rollback likewise
never leaves a document more open than its snapshot (`stricter`).

Plan decision D12 in docs/2026-09-28-corpus-cleanup-plan.md.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from functools import lru_cache

import rights_inventory

FULL = "full"
EXCERPT = "excerpt"

_FULL_STATUSES = frozenset({"permission", "licence"})
_EXCERPT_STATUSES = frozenset({"in-copyright", "unknown"})


def access_for_status(status: str) -> str:
    """The reader access a rights status grants. Raises on a status this module does
    not know, so a new status has to be classified here before it can be published."""
    if status.startswith("pd-") and status in rights_inventory.STATUSES:
        return FULL
    if status in _FULL_STATUSES:
        return FULL
    if status in _EXCERPT_STATUSES:
        return EXCERPT
    raise ValueError(f"unclassified rights status {status!r}")


def access_by_id(inventory: list[dict]) -> dict[str, str]:
    """Reader access by document ID, for every built work's row."""
    return {document_id: access_for_status(e["status"])
            for document_id, e in rights_inventory.by_document_id(inventory).items()}


@lru_cache(maxsize=1)
def _default_access_by_id() -> dict[str, str]:
    return access_by_id(rights_inventory.load())


# Why a document got its access: its inventory row decided, or it fell to excerpt
# because it has no row.
INVENTORY = "inventory"
NO_ROW = "no-row"
OTHER_EDITION = "other-edition"


def resolve(document_id: str, table: dict[str, str] | None = None) -> tuple[str, str]:
    """The reader access of one document and why. Fails closed: a document with no
    inventory row is excerpt-only."""
    table = _default_access_by_id() if table is None else table
    if document_id not in table:
        return EXCERPT, NO_ROW
    return table[document_id], INVENTORY


def access_for(document_id: str, table: dict[str, str] | None = None) -> str:
    return resolve(document_id, table)[0]


def access_for_document(doc) -> str:
    return access_for(doc.id)


def stricter(a: str, b: str) -> str:
    """The more closed of two reader access values."""
    return EXCERPT if EXCERPT in (a, b) else FULL


@lru_cache(maxsize=1)
def _default_source_urls() -> dict[str, str | None]:
    return {i: e["source_url"]
            for i, e in rights_inventory.by_document_id(rights_inventory.load()).items()}


def other_edition(document_id: str, live_url: str | None,
                  urls: dict[str, str | None] | None = None) -> bool:
    """Whether the live document is a different edition from the one its row describes.
    A document or row with no URL says nothing either way."""
    row_url = (_default_source_urls() if urls is None else urls).get(document_id)
    return bool(live_url and row_url and live_url != row_url)


@dataclass(frozen=True)
class Change:
    document_id: str
    collection: str
    title: str
    before: str
    after: str
    reason: str


@dataclass(frozen=True)
class Plan:
    changes: list[Change]
    # Documents the inventory did not decide (no row, or an unresolvable source). Each
    # reads as excerpt, which is safe for a publish but a wrong block for a document
    # that is really public domain, so `sync` refuses to apply while any exist.
    unmatched: list[Change]
    totals: dict[str, int]
    # Documents the inventory calls cleared, made excerpt-only: the live text is another
    # edition than the row's. Not an error: they open with the publish.
    held: list[Change] = field(default_factory=list)


class UnmatchedDocuments(RuntimeError):
    pass


_DOCUMENTS_SQL = ("SELECT id, collection, title, reader_access, metadata->>'url' AS url "
                  "FROM documents")


async def plan(conn, table: dict[str, str] | None = None,
               urls: dict[str, str | None] | None = None, *, lock: bool = False) -> Plan:
    """What a sync would do: every live document whose reader_access disagrees with the
    inventory, every document the inventory did not decide, every document held at
    excerpt because its live text is another edition, and the resulting totals. With
    `lock`, inside a transaction, the rows stay as read until it ends."""
    changes, unmatched, held = [], [], []
    totals = {FULL: 0, EXCERPT: 0}
    for row in await conn.fetch(_DOCUMENTS_SQL + (" FOR UPDATE" if lock else "")):
        after, reason = resolve(str(row["id"]), table)
        if after == FULL and other_edition(str(row["id"]), row.get("url"), urls):
            after, reason = EXCERPT, OTHER_EDITION
            held.append(Change(str(row["id"]), row["collection"], row["title"],
                               row["reader_access"], after, reason))
        totals[after] += 1
        entry = Change(str(row["id"]), row["collection"], row["title"],
                       row["reader_access"], after, reason)
        if reason == NO_ROW:
            unmatched.append(entry)
        if after != row["reader_access"]:
            changes.append(entry)
    order = lambda c: (c.collection, c.title, c.document_id)
    return Plan(sorted(changes, key=order), sorted(unmatched, key=order), totals,
                sorted(held, key=order))


async def sync(conn, table: dict[str, str] | None = None, *, apply: bool,
               allow_unmatched: bool = False,
               urls: dict[str, str | None] | None = None) -> Plan:
    """Bring every document's reader_access in line with the inventory. With
    apply=False this only reports; with apply=True it decides and writes in one
    transaction, with the rows locked so a rollback cannot change an edition between the
    two, and refuses while any document is unmatched unless allow_unmatched is set."""
    if not apply:
        return await plan(conn, table, urls)
    async with conn.transaction():
        result = await plan(conn, table, urls, lock=True)
        if result.unmatched and not allow_unmatched:
            raise UnmatchedDocuments(
                f"REFUSING: {len(result.unmatched)} live document(s) have no row in the "
                "rights inventory. Fix the inventory, or pass --allow-unmatched to block "
                "them deliberately."
            )
        if result.changes:
            for to in (FULL, EXCERPT):
                ids = [c.document_id for c in result.changes if c.after == to]
                if ids:
                    await conn.execute(
                        "UPDATE documents SET reader_access = $1 WHERE id = ANY($2::uuid[])",
                        to, ids,
                    )
    return result


async def _main(apply: bool, allow_unmatched: bool) -> None:
    import asyncpg

    from config import settings

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        result = await plan(conn)
        for c in result.changes:
            print(f"{c.before:>7} -> {c.after:<7} {c.collection:<24} {c.title}"
                  f"  [{c.reason}]  ({c.document_id})")
        for c in result.unmatched:
            print(f"UNMATCHED ({c.reason}): {c.collection} {c.title!r} ({c.document_id})")
        for c in result.held:
            print(f"HELD ({c.reason}): {c.collection} {c.title!r} ({c.document_id})")
        print(f"{len(result.changes)} document(s) would change. After the sync: "
              f"{result.totals[FULL]} full, {result.totals[EXCERPT]} excerpt; "
              f"{len(result.unmatched)} unmatched.")
        if apply:
            await sync(conn, apply=True, allow_unmatched=allow_unmatched)
            print("Applied.")
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: dry run)")
    parser.add_argument("--allow-unmatched", action="store_true",
                        help="apply even when documents are not matched to the inventory "
                             "(they are set to excerpt)")
    args = parser.parse_args(argv)
    asyncio.run(_main(args.apply, args.allow_unmatched))


if __name__ == "__main__":
    main()
