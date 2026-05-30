import logging

from fastapi import Depends, HTTPException

from app.config import settings
from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)


async def check_rate_limit(
    user: AuthUser = Depends(get_current_user),
) -> None:
    """Enforce per-minute rate limit and daily message quota.

    Atomically increments both counters and raises 429 if either limit
    is exceeded. Must be declared as a dependency on chat endpoints only.
    """
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            insert into user_usage (user_id, rate_window_start, rate_count, quota_date, quota_count)
            values ($1, now(), 1, current_date, 1)
            on conflict (user_id) do update set
                rate_window_start = case
                    when now() - user_usage.rate_window_start >= interval '60 seconds'
                    then now()
                    else user_usage.rate_window_start
                end,
                rate_count = case
                    when now() - user_usage.rate_window_start >= interval '60 seconds'
                    then 1
                    else user_usage.rate_count + 1
                end,
                quota_date = current_date,
                quota_count = case
                    when user_usage.quota_date < current_date
                    then 1
                    else user_usage.quota_count + 1
                end
            returning rate_count, quota_count
            """,
            user.user_id,
        )
    except Exception as exc:
        logger.error("rate_limit check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row["rate_count"] > settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again in a moment.",
        )

    if row["quota_count"] > settings.daily_message_quota:
        raise HTTPException(
            status_code=429,
            detail="Daily message limit reached. Try again tomorrow.",
        )
