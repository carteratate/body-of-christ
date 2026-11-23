import logging
import time
from typing import Any, Mapping

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.preferences import (
    DEFAULT_COLLECTIONS,
    DEFAULT_RESULT_CARD_STYLE,
    PreferencesResponse,
    PreferencesUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_PREFERENCES = PreferencesResponse(
    preferred_translation="CPDV",
    default_collections=DEFAULT_COLLECTIONS,
    default_quota=4,
    last_standard_quota=4,
    theme="dark",
    result_card_style=DEFAULT_RESULT_CARD_STYLE,
)

# `user_preferences.result_card_style` comes from 0046, which the API deploys before.
# A query that finds the column missing switches to the SQL without it, and the column
# is tried again after this long, so applying 0046 needs no restart.
_RECHECK_SECONDS = 300.0
_card_style_missing_until = 0.0


def _card_style_column() -> bool:
    return time.monotonic() >= _card_style_missing_until


def _card_style_missing() -> None:
    global _card_style_missing_until
    _card_style_missing_until = time.monotonic() + _RECHECK_SECONDS
    logger.warning("preferences: user_preferences.result_card_style is missing (0046 not applied)")


def _columns(with_card_style: bool) -> str:
    columns = "preferred_translation, default_collections, default_quota, last_standard_quota, theme"
    return columns + (", result_card_style" if with_card_style else "")


def _merge_preferences(body: PreferencesUpdate, current_row: Mapping[str, Any] | None) -> PreferencesResponse:
    # A stored key the API does not know is dropped only when the PUT keeps the stored
    # collections; replacing them makes the stored list irrelevant, quota included.
    if current_row is None:
        current = _DEFAULT_PREFERENCES.model_dump()
    elif body.default_collections is None:
        current = PreferencesResponse.from_stored(current_row).model_dump()
    else:
        current = dict(current_row)
    try:
        return PreferencesResponse(
            preferred_translation=(body.preferred_translation if body.preferred_translation is not None else current["preferred_translation"]),
            default_collections=(body.default_collections if body.default_collections is not None else list(current["default_collections"])),
            default_quota=(body.default_quota if body.default_quota is not None else current["default_quota"]),
            last_standard_quota=(body.last_standard_quota if body.last_standard_quota is not None else current["last_standard_quota"]),
            theme=(body.theme if body.theme is not None else current["theme"]),
            result_card_style=(body.result_card_style if body.result_card_style is not None
                               else current.get("result_card_style") or DEFAULT_RESULT_CARD_STYLE),
        )
    except ValueError as exc:
        message = exc.errors()[0]["msg"] if hasattr(exc, "errors") else str(exc)
        raise HTTPException(status_code=422, detail=message.removeprefix("Value error, ")) from exc


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    user: AuthUser = Depends(get_current_user),
) -> PreferencesResponse:
    """Return user preferences, falling back to defaults if none are set."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    return await _read_preferences(pool, user.user_id)


async def _read_preferences(pool, user_id: str) -> PreferencesResponse:
    with_card_style = _card_style_column()
    try:
        try:
            row = await pool.fetchrow(
                f"SELECT {_columns(with_card_style)} FROM user_preferences WHERE user_id = $1",
                user_id,
            )
        except asyncpg.UndefinedColumnError:
            if not with_card_style:
                raise
            _card_style_missing()
            with_card_style = False
            row = await pool.fetchrow(
                f"SELECT {_columns(False)} FROM user_preferences WHERE user_id = $1",
                user_id,
            )
    except Exception as exc:
        logger.error("get_preferences query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    preferences = _DEFAULT_PREFERENCES if row is None else PreferencesResponse.from_stored(row)
    if not with_card_style:
        preferences = preferences.model_copy(update={"result_card_style": None})
    return preferences


async def _upsert_preferences(pool, user_id: str, body: PreferencesUpdate, with_card_style: bool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"user-preferences:{user_id}",
            )
            current_row = await conn.fetchrow(
                f"SELECT {_columns(with_card_style)} FROM user_preferences WHERE user_id = $1",
                user_id,
            )
            merged = _merge_preferences(body, current_row)
            values = [
                user_id,
                merged.preferred_translation,
                merged.default_collections,
                merged.default_quota,
                merged.last_standard_quota,
                merged.theme,
            ]
            if with_card_style:
                values.append(merged.result_card_style)
            placeholders = ", ".join(f"${n}" for n in range(2, len(values) + 1))
            set_card_style = "result_card_style = EXCLUDED.result_card_style," if with_card_style else ""
            return await conn.fetchrow(
                f"""
                INSERT INTO user_preferences (user_id, {_columns(with_card_style)})
                VALUES ($1, {placeholders})
                ON CONFLICT (user_id) DO UPDATE SET
                    preferred_translation = EXCLUDED.preferred_translation,
                    default_collections = EXCLUDED.default_collections,
                    default_quota = EXCLUDED.default_quota,
                    last_standard_quota = EXCLUDED.last_standard_quota,
                    theme = EXCLUDED.theme,
                    {set_card_style}
                    updated_at = now()
                RETURNING {_columns(with_card_style)}
                """,
                *values,
            )


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: PreferencesUpdate,
    user: AuthUser = Depends(get_current_user),
) -> PreferencesResponse:
    """Upsert user preferences, merging with existing values."""
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    with_card_style = _card_style_column()
    try:
        row = None
        if with_card_style:
            try:
                row = await _upsert_preferences(pool, user.user_id, body, True)
            except asyncpg.UndefinedColumnError:
                # The failed statement aborted its transaction; any retry is a new one.
                _card_style_missing()
                with_card_style = False
        if not with_card_style:
            # Without 0046 a PUT of the card style alone has nothing to store: answer as
            # a read rather than rewrite the other preferences (or create a row).
            if not body.model_dump(exclude_none=True, exclude={"result_card_style"}):
                return await _read_preferences(pool, user.user_id)
            row = await _upsert_preferences(pool, user.user_id, body, False)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("update_preferences transaction failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return PreferencesResponse(
        preferred_translation=row["preferred_translation"],
        default_collections=list(row["default_collections"]),
        default_quota=row["default_quota"],
        last_standard_quota=row["last_standard_quota"],
        theme=row["theme"],
        result_card_style=row["result_card_style"] if with_card_style else None,
    )
