"""The publish lock: no datapipeline command writes to the live corpus without a reviewed entry.

`PUBLISH_LOCK.json` lists the releases a reviewed PR has approved, one entry per
collection and release, naming the steps it allows (`stage`, `apply`, `rollback`,
`repair`). Every command that can write to the reader tables or Qdrant calls
`assert_live_write_allowed` before it opens a connection. It passes only when both
write targets are on this machine (a rehearsal against a restored dump and a local
Qdrant) or when an entry matches the collection, the release and the step. There is
no flag, setting or environment variable that skips it.

See docs/corpus-cleanup/P0-checks-identity-research.md, item 0.4, and the plan's D2,
D7 and D11.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_PATH = Path(__file__).resolve().parent / "PUBLISH_LOCK.json"

STEPS = frozenset({"stage", "apply", "rollback", "repair"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_DEFAULT_REASON = (
    "Live writes only for a collection and release listed in PUBLISH_LOCK.json, "
    "added in a reviewed PR."
)


class PublishLocked(ValueError):
    """A live write the lock does not allow. A ValueError, so CLIs report it like
    any other refusal (argparse error, exit code 2)."""


@dataclass(frozen=True)
class LockEntry:
    collection: str
    release: str
    steps: frozenset[str]


@dataclass(frozen=True)
class PublishLock:
    reason: str
    entries: tuple[LockEntry, ...]


@dataclass(frozen=True)
class WriteTargets:
    database_url: str
    qdrant_url: str


def load_lock(path: Path = DEFAULT_PATH) -> PublishLock:
    """Read the lock file. Anything missing or malformed counts as an empty list
    (fail closed): an entry that cannot be read approves nothing."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PublishLock(reason=_DEFAULT_REASON, entries=())
    if not isinstance(data, dict) or not isinstance(data.get("approved_applies"), list):
        return PublishLock(reason=_DEFAULT_REASON, entries=())

    reason = data.get("reason") if isinstance(data.get("reason"), str) else _DEFAULT_REASON
    entries = []
    for item in data["approved_applies"]:
        if not isinstance(item, dict):
            continue
        collection, release, steps = item.get("collection"), item.get("release"), item.get("steps")
        if not (isinstance(collection, str) and collection
                and isinstance(release, str) and release
                and isinstance(steps, list)):
            continue
        entries.append(LockEntry(
            collection=collection,
            release=release,
            steps=frozenset(s for s in steps if s in STEPS),
        ))
    return PublishLock(reason=reason, entries=tuple(entries))


def settings_targets() -> WriteTargets:
    """The database and Qdrant a command would write to, from datapipeline settings.
    Imported lazily so a dry run or --help needs no credentials."""
    from config import settings

    return WriteTargets(database_url=settings.DATABASE_URL, qdrant_url=settings.QDRANT_URL)


def _is_loopback(url: str) -> bool:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return False
    return host is not None and host.lower() in _LOOPBACK_HOSTS


def assert_live_write_allowed(
    action: str,
    collection: str,
    release: str | None,
    step: str,
    lock: PublishLock | None = None,
    targets: WriteTargets | None = None,
) -> None:
    """Raise PublishLocked unless this write is a local rehearsal or is listed.

    A run passes when both the database and Qdrant URLs name a loopback host, or
    when `release` is non-empty and an entry has the same collection and release
    and names `step`. A run over every collection needs an entry for "all".
    """
    if step not in STEPS:
        raise ValueError(f"unknown publish-lock step: {step!r}")
    targets = targets or settings_targets()
    if _is_loopback(targets.database_url) and _is_loopback(targets.qdrant_url):
        return

    lock = lock or load_lock()
    if release and any(
        entry.collection == collection and entry.release == release and step in entry.steps
        for entry in lock.entries
    ):
        return

    raise PublishLocked(
        f"locked: refusing to {action} (step '{step}', collection '{collection}', "
        f"release {release!r}). {lock.reason} To approve it, add an entry for this "
        f"collection and release with step '{step}' to datapipeline/PUBLISH_LOCK.json "
        f"in a reviewed PR, then pass --collection {collection} --release <the same release>."
    )
