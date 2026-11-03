"""The one publish path (corpus-cleanup 2.2w, D2): stage, report, then apply.

    cd datapipeline
    python3 publish.py stage   --collection <name>|all --release <name>
    python3 publish.py report  --release <name> [--out <dir>] [--no-public]
    python3 publish.py status  [--release <name>]
    python3 publish.py discard --release <name>

The release name is the publish ID: `corpus_publishes.id`, the `release` of the
PUBLISH_LOCK.json entry, and the suffix of the staging Qdrant collection
`chunks-<release>` (D11).

- `stage` builds the collections into the `staging` schema and a new Qdrant collection,
  and writes nothing users read.
- `report` writes the release report of the staged publish against live (read only,
  apart from recording its hash for `apply`).
- `status` shows each publish and where the live alias points.
- `discard` abandons a publish that was never applied: it drops the staging tables and
  records the publish as discarded. Its Qdrant collection is left for a separate ops
  step to delete.

`apply`, `switch`, `rollback` and `cleanup` arrive with 2.2w's second part. Until then no
command in the datapipeline writes the live corpus at all.

Every subcommand except `report` and `status` asks the publish lock (0.4) for its step:
`stage` for stage and discard. A run whose database and Qdrant are both on this machine
(a local rehearsal, D8) passes without an entry.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime

DATAPIPELINE = os.path.dirname(os.path.abspath(__file__))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

from publication import SOURCE_ADAPTERS  # noqa: E402

RELEASE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")   # corpus_publishes.id's CHECK


def _release(value: str) -> str:
    if not RELEASE.match(value):
        raise argparse.ArgumentTypeError(
            "a release is 3 to 63 lowercase letters, digits and hyphens, starting with a "
            "letter or digit")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage", help="build collections into staging and a new collection")
    stage.add_argument("--collection", required=True, choices=["all", *sorted(SOURCE_ADAPTERS)])
    stage.add_argument("--release", required=True, type=_release)
    report = sub.add_parser("report", help="the release report of a staged publish")
    report.add_argument("--release", required=True, type=_release)
    report.add_argument("--out", help="default releases/local/publish-<release>-<time>/")
    report.add_argument("--public", action=argparse.BooleanOptionalAction, default=True,
                        help="keep passage text out of report.md (default)")
    status = sub.add_parser("status", help="each publish, and where the live alias points")
    status.add_argument("--release", type=_release)
    discard = sub.add_parser("discard", help="abandon a publish that was never applied")
    discard.add_argument("--release", required=True, type=_release)
    return parser


def guard_publish(step: str, collections: Sequence[str], release: str, lock_path=None) -> None:
    """Ask the publish lock for `step` on each collection (one "all" entry for all)."""
    from publication import publish_lock_guard

    guard = publish_lock_guard(step, lock_path)
    for c in ["all"] if set(collections) == set(SOURCE_ADAPTERS) else collections:
        guard(c, release)


async def _connect():
    import asyncpg

    from config import settings

    # statement_cache_size=0: the Supabase pooler does not keep prepared statements.
    return await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)


async def _publish_row(conn, release: str):
    row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
    if row is None:
        raise ValueError(f"no publish named '{release}'")
    return row


async def stage(args, lock_path=None) -> int:
    from publication import StageRequest, production_stage_runner

    collections = sorted(SOURCE_ADAPTERS) if args.collection == "all" else [args.collection]
    result = await production_stage_runner(lock_path).stage(
        StageRequest(release=args.release, collections=tuple(collections)))
    print(f"staged {result.release}: {result.documents} documents, {result.passages} "
          f"passages into staging and Qdrant '{result.qdrant_collection}'")
    print(f"  new IDs {len(result.new_ids)}, tombstones {result.tombstones}, redirects "
          f"{result.redirects or 'none'}, passages moving document {result.moved}")
    print(f"  copied from live: {result.copied or 'none'}; vectors {result.vectors}")
    print(f"next: python3 publish.py report --release {result.release}")
    return 0


async def report(args, lock_path=None) -> int:
    from config import settings
    from release import staged
    from writers.qdrant import get_client

    out = args.out or os.path.join(DATAPIPELINE, "releases", "local",
                                   f"publish-{args.release}-{datetime.now():%Y%m%d-%H%M%S}")
    conn = await _connect()
    client = get_client()
    try:
        row = await _publish_row(conn, args.release)

        async def record(report_sha256: str) -> None:
            guard_publish("stage", row["collections"], args.release, lock_path)
            await conn.execute("UPDATE corpus_publishes SET report_sha256 = $2 WHERE id = $1",
                               args.release, report_sha256)

        code = await staged.run(conn, client, args.release, out, public=args.public,
                                live_alias=settings.QDRANT_LIVE_ALIAS, record=record)
    finally:
        await conn.close()
        await client.close()
    print(f"wrote {out}/report.md")
    return code


async def status(args) -> int:
    from config import settings
    from writers.qdrant import alias_target, get_client
    from writers.reader_writer import staging_exists

    conn = await _connect()
    client = get_client()
    try:
        rows = await conn.fetch(
            "SELECT * FROM corpus_publishes WHERE $1::text IS NULL OR id = $1 ORDER BY id",
            args.release)
        print(f"live alias {settings.QDRANT_LIVE_ALIAS} -> "
              f"{await alias_target(client, settings.QDRANT_LIVE_ALIAS)}")
        print(f"staging tables: {'present' if await staging_exists(conn) else 'absent'}")
        for r in rows:
            steps = [f"{c.removesuffix('_at')} {r[c]:%Y-%m-%d %H:%M}" for c in (
                "staged_at", "applied_at", "alias_switched_at", "rolled_back_at",
                "cleaned_up_at", "discarded_at") if r[c] is not None]
            print(f"{r['id']}: {', '.join(r['collections'])}; Qdrant {r['qdrant_collection']}; "
                  f"report {'recorded' if r['report_sha256'] else 'none'}; "
                  f"{'; '.join(steps) or 'not staged'}")
        if not rows:
            print("no publishes")
    finally:
        await conn.close()
        await client.close()
    return 0


async def discard(args, lock_path=None) -> int:
    conn = await _connect()
    try:
        row = await _publish_row(conn, args.release)
        guard_publish("stage", row["collections"], args.release, lock_path)
        for column in ("applied_at", "discarded_at", "cleaned_up_at"):
            if row[column] is not None:
                raise ValueError(f"REFUSING: publish '{args.release}' was "
                                 f"{column.removesuffix('_at')}; only an unapplied publish "
                                 "is discarded")
        async with conn.transaction():
            await conn.execute("SELECT public.drop_corpus_staging()")
            await conn.execute("UPDATE corpus_publishes SET discarded_at = now() WHERE id = $1",
                               args.release)
    finally:
        await conn.close()
    print(f"discarded {args.release}: staging tables dropped. Qdrant collection "
          f"'{row['qdrant_collection']}' is recorded on the publish for deletion, which is "
          "a separate ops step")
    return 0


def main(argv: Sequence[str] | None = None, *, lock_path=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            return asyncio.run(stage(args, lock_path))
        if args.command == "report":
            return asyncio.run(report(args, lock_path))
        if args.command == "status":
            return asyncio.run(status(args))
        return asyncio.run(discard(args, lock_path))
    except ValueError as error:      # refusals, the lock (PublishLocked) included
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
