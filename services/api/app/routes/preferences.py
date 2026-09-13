import logging
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.preferences import PreferencesResponse, PreferencesUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_PREFERENCES = PreferencesResponse(
    preferred_translation="CPDV",
    default_collections=["bible", "catechism", "church-fathers", "encyclicals", "canon-law", "summa"],
    default_quota=4,
    last_standard_quota=4,
    theme="dark",
)


def _merge_preferences(body: PreferencesUpdate, current_row: Mapping[str, Any] | None) -> PreferencesResponse:
    current = current_row if current_row is not None else _DEFAULT_PREFERENCES.model_dump()
    try:
        return PreferencesResponse(
            preferred_translation=(body.preferred_translation if body.preferred_translation is not None else current["preferred_translation"]),
            default_collections=(body.default_collections if body.default_collections is not None else list(current["default_collections"])),
            default_quota=(body.default_quota if body.default_quota is not None else current["default_quota"]),
            last_standard_quota=(body.last_standard_quota if body.last_standard_quota is not None else current["last_standard_quota"]),
            theme=(body.theme if body.theme is not None else current["theme"]),
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

    try:
        row = await pool.fetchrow(
            "SELECT preferred_translation, default_collections, default_quota, last_standard_quota, theme FROM user_preferences WHERE user_id = $1",
            user.user_id,
        )
    except Exception as exc:
        logger.error("get_preferences query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row is None:
        return _DEFAULT_PREFERENCES

    return PreferencesResponse(
        preferred_translation=row["preferred_translation"],
        default_collections=list(row["default_collections"]),
        default_quota=row["default_quota"],
        last_standard_quota=row["last_standard_quota"],
        theme=row["theme"],
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

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"user-preferences:{user.user_id}",
                )
                current_row = await conn.fetchrow(
                    "SELECT preferred_translation, default_collections, default_quota, last_standard_quota, theme FROM user_preferences WHERE user_id = $1",
                    user.user_id,
                )
                merged = _merge_preferences(body, current_row)
                row = await conn.fetchrow(
                    """
                    INSERT INTO user_preferences (user_id, preferred_translation, default_collections, default_quota, last_standard_quota, theme)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_id) DO UPDATE SET
                        preferred_translation = EXCLUDED.preferred_translation,
                        default_collections = EXCLUDED.default_collections,
                        default_quota = EXCLUDED.default_quota,
                        last_standard_quota = EXCLUDED.last_standard_quota,
                        theme = EXCLUDED.theme,
                        updated_at = now()
                    RETURNING preferred_translation, default_collections, default_quota, last_standard_quota, theme
                    """,
                    user.user_id,
                    merged.preferred_translation,
                    merged.default_collections,
                    merged.default_quota,
                    merged.last_standard_quota,
                    merged.theme,
                )
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
    )
