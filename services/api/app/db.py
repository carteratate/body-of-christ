import asyncpg
import json

from app.config import settings

_pool: asyncpg.Pool | None = None

# How long a request waits for a free pool connection. asyncpg waits indefinitely by
# default, so when the database stalls every request queues silently until its query
# finally runs into command_timeout. Where it is used, a stall fails fast and shows
# up in logs: full-text search drops that collection's lexical path, and the reader
# and /sources return a retryable 503. Other queries still wait without a bound.
# asyncpg also applies the same bound to releasing that connection (its reset query),
# so a release that stalls past it fails the request the same way.
POOL_ACQUIRE_TIMEOUT_SECONDS = 5.0

# Connection settings for each CORPUS_READ_SCHEMA other than `public`. The tables in
# `staging` have the live names, so unqualified queries read the staged corpus, user
# tables still resolve to `public`, and the session cannot write anything.
_READ_OVERRIDE = {
    "staging": {"search_path": "staging, public", "default_transaction_read_only": "on"},
}


def _read_override() -> dict[str, str] | None:
    schema = settings.corpus_read_schema
    if schema == "public":
        return None
    if schema not in _READ_OVERRIDE:
        raise RuntimeError(f"CORPUS_READ_SCHEMA must be public or staging, got {schema!r}")
    return _READ_OVERRIDE[schema]


async def _check_read_override(conn: asyncpg.Connection, override: dict[str, str]) -> None:
    """Refuse a connection that would read live while looking like a staging run.

    A pooler can drop startup settings without saying so, and with no staged tables
    `search_path` falls through to `public`. Either way every query would still succeed.
    """
    for name, expected in override.items():
        actual = await conn.fetchval("SELECT current_setting($1)", name)
        if actual != expected:
            raise RuntimeError(f"CORPUS_READ_SCHEMA did not reach the connection: "
                               f"{name} is {actual!r}, expected {expected!r}")
    if await conn.fetchval("SELECT to_regclass('staging.chunks')") is None:
        raise RuntimeError("CORPUS_READ_SCHEMA is staging but there is no staged corpus")


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs so asyncpg returns dicts instead of strings.

    Required when statement_cache_size=0 (Supabase pooler) disables type
    inference from prepared statements.
    """
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )
    override = _read_override()
    if override is not None:
        await _check_read_override(conn, override)


async def init_pool() -> None:
    global _pool
    override = _read_override()
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=10,
        statement_cache_size=0,
        # Supabase's transaction pooler may retire an idle upstream socket while a
        # long LLM call is running. Retire our idle connections first so the next
        # search opens a fresh socket instead of discovering the stale one mid-query.
        max_inactive_connection_lifetime=60.0,
        command_timeout=30.0,
        init=_init_connection,
        **({"server_settings": override} if override is not None else {}),
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    return _pool
