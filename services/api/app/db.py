import asyncpg
import json

from app.config import settings

_pool: asyncpg.Pool | None = None


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


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=10,
        statement_cache_size=0,
        init=_init_connection,
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    return _pool
