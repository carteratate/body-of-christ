"""Delete the anchor redirects a restage wrote under the wrong old document (#439).

Before #439's fix, a stage after a publish that moved a passage to another document
wrote the passage's old anchor under its new document. 4.4's publish
(`card-notes-2026-11`, 22 Nov 2026) applied 623 such rows. No link reaches them: a
redirect is looked up by the document a link names, and the correct row, from the
document the passage moved out of, is live beside each one.

    cd datapipeline
    python3 scripts/delete_unreachable_redirects.py --release card-notes-2026-11
    python3 scripts/delete_unreachable_redirects.py --release card-notes-2026-11 \\
        --execute --expect 623

A row is deleted only when all of these hold: it is an `anchor` redirect the release
wrote; its old document is its new document; a live anchor redirect from another document
sends the same old anchor to the same place; and no live passage and no reading position
names its (old document, old anchor). The dry run, the default, lists them by document
and writes nothing. `--execute` needs the release's publish-lock entry with the `apply`
step for `all`, recounts inside one transaction under the publish lock, and refuses
unless the count equals `--expect`, the dry run's figure.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

# A condition on `r`, a row of public.corpus_redirects; $1 is the release. The match with
# the correct row is a join on (old anchor, new document, new anchor), which the planner
# hashes: as a correlated EXISTS it walked the index's whole anchor range once per row of
# the release (191 s on production, 22 Nov 2026).
UNREACHABLE = """
r.id IN (
    SELECT w.id FROM public.corpus_redirects w
    JOIN public.corpus_redirects o
      ON o.entity = 'anchor' AND o.old_anchor = w.old_anchor
     AND o.new_document_id = w.new_document_id AND o.new_anchor = w.new_anchor
     AND o.old_document_id <> w.old_document_id
    WHERE w.entity = 'anchor' AND w.publish_id = $1
      AND w.old_document_id = w.new_document_id)
AND NOT EXISTS (SELECT 1 FROM public.chunks c
                WHERE c.document_id = r.old_document_id AND c.anchor = r.old_anchor)
AND NOT EXISTS (SELECT 1 FROM public.reading_progress p
                WHERE p.document_id = r.old_document_id AND p.anchor = r.old_anchor)
"""


async def plan(conn, release: str) -> list[tuple[str, int]]:
    """(document title, rows) for every document the unreachable rows name."""
    rows = await conn.fetch(
        f"""SELECT coalesce(d.title, r.old_document_id::text) AS title, count(*) AS n
            FROM public.corpus_redirects r LEFT JOIN public.documents d ON d.id = r.old_document_id
            WHERE {UNREACHABLE} GROUP BY 1 ORDER BY 2 DESC, 1""", release)
    return [(r["title"], r["n"]) for r in rows]


async def execute(conn, release: str, expect: int) -> int:
    """Delete them in one transaction under the publish lock; return how many."""
    from publication import lock_publishes

    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '2s'")
        await lock_publishes(conn)
        found = await conn.fetchval(
            f"SELECT count(*) FROM public.corpus_redirects r WHERE {UNREACHABLE}", release)
        if found != expect:
            raise ValueError(f"REFUSING: {found} unreachable rows now, not the {expect} "
                             "expected; rerun the dry run")
        status = await conn.execute(
            f"DELETE FROM public.corpus_redirects r WHERE {UNREACHABLE}",
            release)
    return int(status.split()[-1])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--release", required=True, help="the publish that wrote them")
    parser.add_argument("--execute", action="store_true",
                        help="delete; without it, a dry run that writes nothing")
    parser.add_argument("--expect", type=int, help="with --execute: the dry run's count")
    return parser


async def main(argv=None, *, connect=None, lock_path=None) -> int:
    args = build_parser().parse_args(argv)
    if args.execute and args.expect is None:
        raise SystemExit("--execute needs --expect, the dry run's count")
    if connect is None:
        import asyncpg

        from config import settings

        async def connect():
            return await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
    if args.execute:
        from publication import publish_lock_guard

        publish_lock_guard("apply", lock_path)("all", args.release)
    conn = await connect()
    try:
        if not args.execute:
            async with conn.transaction(readonly=True):
                found = await plan(conn, args.release)
            print(f"dry run: {sum(n for _, n in found)} unreachable anchor redirects from "
                  f"'{args.release}', in {len(found)} documents; nothing changed")
            for title, n in found:
                print(f"  {n:>5}  {title}")
            return 0
        deleted = await execute(conn, args.release, args.expect)
    finally:
        await conn.close()
    print(f"deleted {deleted} unreachable anchor redirects from '{args.release}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
