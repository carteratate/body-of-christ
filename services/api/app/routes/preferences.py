import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.preferences import PreferencesResponse, PreferencesUpdate
from app.rag.constants import VALID_COLLECTIONS as _VALID_COLLECTIONS

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_TRANSLATIONS = {"CPDV", "douay-rheims"}

_DEFAULT_PREFERENCES = PreferencesResponse(
    preferred_translation="CPDV",
    default_collections=["bible", "catechism", "church-fathers", "encyclicals", "canon-law", "summa"],
    default_quota=4,
)


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
            "SELECT preferred_translation, default_collections, default_quota FROM user_preferences WHERE user_id = $1",
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
    )


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: PreferencesUpdate,
    user: AuthUser = Depends(get_current_user),
) -> PreferencesResponse:
    """Upsert user preferences, merging with existing values."""
    # Validate preferred_translation if provided — reject any unknown values
    if body.preferred_translation is not None:
        if body.preferred_translation not in _VALID_TRANSLATIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown translation: {body.preferred_translation!r}. Valid values: {sorted(_VALID_TRANSLATIONS)}",
            )

    # Validate default_collections if provided — reject any unknown values
    if body.default_collections is not None:
        invalid = [c for c in body.default_collections if c not in _VALID_COLLECTIONS]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown collections: {invalid}. Valid values: {sorted(_VALID_COLLECTIONS)}",
            )
        if not body.default_collections:
            raise HTTPException(
                status_code=422,
                detail=f"At least one collection is required. Valid values: {sorted(_VALID_COLLECTIONS)}",
            )
        body = PreferencesUpdate(
            preferred_translation=body.preferred_translation,
            default_collections=body.default_collections,
            default_quota=body.default_quota,
        )

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Fetch current preferences to merge with the incoming update
    try:
        current_row = await pool.fetchrow(
            "SELECT preferred_translation, default_collections, default_quota FROM user_preferences WHERE user_id = $1",
            user.user_id,
        )
    except Exception as exc:
        logger.error("update_preferences fetch current failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if current_row is not None:
        merged_translation = body.preferred_translation if body.preferred_translation is not None else current_row["preferred_translation"]
        merged_collections = body.default_collections if body.default_collections is not None else list(current_row["default_collections"])
        merged_quota = body.default_quota if body.default_quota is not None else current_row["default_quota"]
    else:
        merged_translation = body.preferred_translation if body.preferred_translation is not None else _DEFAULT_PREFERENCES.preferred_translation
        merged_collections = body.default_collections if body.default_collections is not None else list(_DEFAULT_PREFERENCES.default_collections)
        merged_quota = body.default_quota if body.default_quota is not None else _DEFAULT_PREFERENCES.default_quota

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO user_preferences (user_id, preferred_translation, default_collections, default_quota)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
                preferred_translation = EXCLUDED.preferred_translation,
                default_collections = EXCLUDED.default_collections,
                default_quota = EXCLUDED.default_quota,
                updated_at = now()
            RETURNING preferred_translation, default_collections, default_quota
            """,
            user.user_id,
            merged_translation,
            merged_collections,
            merged_quota,
        )
    except Exception as exc:
        logger.error("update_preferences upsert failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return PreferencesResponse(
        preferred_translation=row["preferred_translation"],
        default_collections=list(row["default_collections"]),
        default_quota=row["default_quota"],
    )
