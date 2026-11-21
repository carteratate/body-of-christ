"""The one publish path (corpus-cleanup 2.2w, D2): stage, report, then apply.

    cd datapipeline
    python3 publish.py stage   --collection <name>|all --release <name>
    python3 publish.py report  --release <name> [--out <dir>] [--no-public]
    python3 publish.py status  [--release <name>]
    python3 publish.py discard --release <name>
    python3 publish.py apply   --release <name> [--no-switch]
    python3 publish.py apply   --retire-only --collection <name> --release <name>
    python3 publish.py switch  --release <name>
    python3 publish.py rollback --release <name>
    python3 publish.py cleanup --release <name>
    python3 publish.py purge-retired --release <name> [--execute --disk-free-gb <GB>]
    python3 publish.py drop-old-collection --release <name> [--execute --confirm <name>]

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

- `apply` writes the before-snapshot to `releases/snapshots/<release>-before/`, then in
  one transaction updates, inserts and retires (never deletes), writes tombstones and
  redirects, moves the user rows on redirected IDs (4.1a, `remap_user_data.py`), and
  refreshes outlines; then it switches the alias `chunks_live` to the publish's
  collection, unless `--no-switch`. The remap's private ledger joins the before-snapshot. `--retire-only` retires the documents an open
  `document` removal entry names in one collection, with nothing staged (D7's On the
  Incarnation exception).
- `switch` points the alias at the publish's collection (after `apply --no-switch`).
- `rollback` undoes an applied publish from its before-snapshot, in one transaction with
  4.1a's reverse remap, then points the alias back. It is the only rollback path (D11).
- `cleanup` drops the staging tables once the apply is checked; rollback still works.
- `purge-retired` and `drop-old-collection` are 4.1b step 13, after the rollback window
  (`retention.py`): delete the retired rows nothing points at, and the Qdrant collection
  the switch left. Each is a dry run unless `--execute`.

Every subcommand except `report` and `status` asks the publish lock (0.4) for its step:
`stage` for stage and discard, `apply` for apply, switch, cleanup and a live
purge-retired or drop-old-collection, `rollback` for rollback. A run whose database and Qdrant are both on this machine (a local rehearsal,
D8) passes without an entry.
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
    apply = sub.add_parser("apply", help="move a reported publish into live, then switch")
    apply.add_argument("--release", required=True, type=_release)
    apply.add_argument("--no-switch", action="store_true", help="leave the alias as it is")
    apply.add_argument("--retire-only", action="store_true",
                       help="retire one collection's removed documents; stage nothing")
    apply.add_argument("--collection", choices=sorted(SOURCE_ADAPTERS),
                       help="with --retire-only: the collection")
    for name, text in (("switch", "point the live alias at an applied publish"),
                       ("rollback", "undo an applied publish from its before-snapshot"),
                       ("cleanup", "drop the staging tables of an applied publish")):
        sub.add_parser(name, help=text).add_argument("--release", required=True, type=_release)
    purge = sub.add_parser("purge-retired",
                           help="delete retired rows nothing points at (4.1b step 13)")
    purge.add_argument("--release", required=True, type=_release)
    purge.add_argument("--execute", action="store_true",
                       help="delete; without it, a dry run that writes nothing")
    purge.add_argument("--disk-free-gb", type=float,
                       help="free space on the database disk, read from the Supabase "
                            "dashboard (Database -> Disk) just before; needed with --execute")
    drop = sub.add_parser("drop-old-collection",
                          help="delete the Qdrant collection the switch left (4.1b step 13)")
    drop.add_argument("--release", required=True, type=_release)
    drop.add_argument("--execute", action="store_true",
                      help="delete; without it, a dry run that changes nothing")
    drop.add_argument("--confirm", help="with --execute: the collection's name, typed out")
    return parser


def guard_publish(step: str, collections: Sequence[str], release: str, lock_path=None) -> None:
    """Ask the publish lock for `step` on each collection (one "all" entry for all)."""
    from publication import publish_lock_guard

    guard = publish_lock_guard(step, lock_path)
    for c in ["all"] if set(collections) == set(SOURCE_ADAPTERS) else collections:
        guard(c, release)


def _print_remap(title: str, counts: dict[str, int]) -> None:
    """4.1a's public ledger counts (per table and rule; no IDs) for the publish log."""
    print(f"{title}: " + (", ".join(f"{k} {n}" for k, n in counts.items()) or "none"))


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
    from publication import lock_publishes

    conn = await _connect()
    try:
        row = await _publish_row(conn, args.release)
        guard_publish("stage", row["collections"], args.release, lock_path)
        async with conn.transaction():
            # Validate under the lock: another discard or stage may have run since the
            # read above, and staging may now hold a different release.
            await lock_publishes(conn)
            row = await _publish_row(conn, args.release)
            for column in ("applied_at", "discarded_at", "cleaned_up_at"):
                if row[column] is not None:
                    raise ValueError(f"REFUSING: publish '{args.release}' was "
                                     f"{column.removesuffix('_at')}; only an unapplied "
                                     "publish is discarded")
            await conn.execute("SELECT public.drop_corpus_staging()")
            await conn.execute("UPDATE corpus_publishes SET discarded_at = now() WHERE id = $1",
                               args.release)
    finally:
        await conn.close()
    print(f"discarded {args.release}: staging tables dropped. Qdrant collection "
          f"'{row['qdrant_collection']}' is recorded on the publish for deletion, which is "
          "a separate ops step")
    return 0


async def apply(args, lock_path=None) -> int:
    from config import settings
    from remap_user_data import UserDataRemapImpl
    from writers import apply as A
    from writers.qdrant import get_client

    if args.retire_only:
        if not args.collection:
            raise ValueError("--retire-only needs --collection")
        guard_publish("apply", [args.collection], args.release, lock_path)
    elif args.collection:
        raise ValueError("--collection goes with --retire-only only")
    conn = await _connect()
    client = get_client()
    try:
        if args.retire_only:
            done = await A.retire_only(conn, client, args.release, args.collection,
                                       alias=settings.QDRANT_LIVE_ALIAS)
            print(f"retired {done['documents']} documents and {done['passages']} passages "
                  f"of {args.collection}; their points in {done['collection']} are marked "
                  "not searchable. Restart the API to clear the /sources cache.")
            return 0
        row = await _publish_row(conn, args.release)
        guard_publish("apply", row["collections"], args.release, lock_path)
        result = await A.apply(conn, args.release, remap=UserDataRemapImpl())
        print(f"applied {result.release}: {result.touched} documents touched, "
              f"{result.inserted} passages inserted, {result.retired_passages} passages and "
              f"{result.retired_documents} documents retired, {result.tombstones} tombstones, "
              f"{result.redirects} redirects")
        _print_remap("user rows moved", result.remap)
        if not args.no_switch:
            old, new = await A.switch(conn, client, args.release, settings.QDRANT_LIVE_ALIAS)
            print(f"switched {settings.QDRANT_LIVE_ALIAS}: {old} -> {new}")
    finally:
        await conn.close()
        await client.close()
    return 0


async def switch(args, lock_path=None) -> int:
    from config import settings
    from writers import apply as A
    from writers.qdrant import get_client

    conn = await _connect()
    client = get_client()
    try:
        row = await _publish_row(conn, args.release)
        guard_publish("apply", row["collections"], args.release, lock_path)
        old, new = await A.switch(conn, client, args.release, settings.QDRANT_LIVE_ALIAS)
    finally:
        await conn.close()
        await client.close()
    print(f"switched {settings.QDRANT_LIVE_ALIAS}: {old} -> {new}")
    return 0


async def rollback(args, lock_path=None) -> int:
    from config import settings
    from remap_user_data import UserDataRemapImpl
    from writers import apply as A
    from writers.qdrant import get_client

    conn = await _connect()
    client = get_client()
    try:
        row = await _publish_row(conn, args.release)
        guard_publish("rollback", row["collections"], args.release, lock_path)
        result = await A.rollback(conn, client, args.release, alias=settings.QDRANT_LIVE_ALIAS,
                                  remap=UserDataRemapImpl())
    finally:
        await conn.close()
        await client.close()
    print(f"rolled back {result.release}: {result.restored_passages} passages restored, "
          f"{result.retired_passages} passages the publish added retired as rolled back; "
          f"alias -> {result.alias or 'unchanged'}. Run cleanup, then restart the API.")
    _print_remap("user rows restored", result.remap)
    return 0


async def cleanup(args, lock_path=None) -> int:
    from writers import apply as A

    conn = await _connect()
    try:
        row = await _publish_row(conn, args.release)
        guard_publish("apply", row["collections"], args.release, lock_path)
        await A.cleanup(conn, args.release)
    finally:
        await conn.close()
    print(f"cleaned up {args.release}: staging tables dropped")
    return 0


async def purge_retired(args, lock_path=None) -> int:
    import retention

    if not args.execute and args.disk_free_gb is not None:
        raise ValueError("--disk-free-gb goes with --execute")
    conn = await _connect()
    try:
        if not args.execute:
            print("\n".join(retention.describe(await retention.read_plan(conn, args.release))))
            return 0
        await _publish_row(conn, args.release)
        # Corpus-wide, whatever the release published: only an "all" entry approves it.
        guard_publish("apply", sorted(SOURCE_ADAPTERS), args.release, lock_path)
        free = None if args.disk_free_gb is None else int(args.disk_free_gb * (1 << 30))
        result = await retention.execute(conn, args.release, disk_free_bytes=free)
    finally:
        await conn.close()
    print(f"purged {args.release}: {result.passages:,} passages and {result.documents:,} "
          f"documents deleted in {result.batches} batches, {result.outlines} outline "
          f"refreshes, {result.newly_kept} rows kept because someone pointed at them since "
          "the plan. Next: VACUUM (analyze) chunks, then measure the database size.")
    return 0


async def drop_old_collection(args, lock_path=None) -> int:
    import retention
    from config import settings
    from writers.qdrant import get_client

    if args.confirm and not args.execute:
        raise ValueError("--confirm goes with --execute")
    conn = await _connect()
    client = get_client()
    try:
        if not args.execute:
            async with conn.transaction(readonly=True):
                old = await retention.old_collection(conn, client, args.release,
                                                     settings.QDRANT_LIVE_ALIAS)
            print(f"drop-old-collection {args.release}: dry run, nothing changed")
            print(f"  would delete Qdrant collection '{old.name}' "
                  f"({'?' if old.points is None else f'{old.points:,}'} points). "
                  "It cannot be undone; the only copy after that is a snapshot, if one is kept.")
            print("  a live run now would refuse:" if old.problems else
                  "  a live run now would pass its checks (the lock is checked when it starts)")
            for problem in old.problems:
                print(f"  - {problem}")
            return 0
        await _publish_row(conn, args.release)
        # The old collection holds every collection's points: an "all" entry only.
        guard_publish("apply", sorted(SOURCE_ADAPTERS), args.release, lock_path)
        name, deleted = await retention.drop_old_collection(conn, client, args.release,
                                                   settings.QDRANT_LIVE_ALIAS, args.confirm)
    finally:
        await conn.close()
        await client.close()
    print(f"deleted Qdrant collection '{name}'" if deleted else
          f"Qdrant collection '{name}' was already absent; nothing to delete")
    return 0


COMMANDS = {"stage": stage, "report": report, "discard": discard, "apply": apply,
            "switch": switch, "rollback": rollback, "cleanup": cleanup,
            "purge-retired": purge_retired, "drop-old-collection": drop_old_collection}


def main(argv: Sequence[str] | None = None, *, lock_path=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            return asyncio.run(status(args))
        return asyncio.run(COMMANDS[args.command](args, lock_path))
    except ValueError as error:      # refusals, the lock (PublishLocked) included
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
