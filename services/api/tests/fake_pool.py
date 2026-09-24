"""An asyncpg-pool stand-in for code that borrows a connection with pool.acquire()."""

from unittest.mock import AsyncMock, MagicMock


class FakePool:
    """Hands out one connection mock, recording each acquire's timeout and release.

    Configure queries on `conn`, e.g. `pool.conn.fetch.side_effect = [...]`. Pass
    `acquire_error` to make every acquire raise it, as an exhausted pool does, or
    `acquire_errors` to fail successive acquires in turn (None succeeds).
    """

    def __init__(self, conn=None, acquire_error: BaseException | None = None,
                 acquire_errors: list[BaseException | None] | None = None):
        self.conn = conn if conn is not None else MagicMock(
            fetch=AsyncMock(), fetchrow=AsyncMock(), fetchval=AsyncMock(),
        )
        self.acquire_error = acquire_error
        self._acquire_errors = list(acquire_errors or [])
        self.acquire_timeouts: list[float | None] = []
        self.released = 0

    def acquire(self, *, timeout=None):
        self.acquire_timeouts.append(timeout)
        pool = self

        class _Borrowed:
            def __await__(self):
                return self.__aenter__().__await__()

            async def __aenter__(self):
                error = pool._acquire_errors.pop(0) if pool._acquire_errors else pool.acquire_error
                if error is not None:
                    raise error
                return pool.conn

            async def __aexit__(self, *exc):
                pool.released += 1
                return False

        return _Borrowed()

    async def release(self, conn):
        assert conn is self.conn
        self.released += 1
