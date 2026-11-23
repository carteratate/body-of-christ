import logging
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, field_validator, model_validator

from app.rag.constants import VALID_COLLECTIONS

logger = logging.getLogger(__name__)

DEFAULT_COLLECTIONS = ["bible", "catechism", "church-fathers", "papal", "church-law", "summa"]

StandardQuota = Literal[3, 4, 5]
PreferenceQuota = Literal[3, 4, 5, 10]
Theme = Literal["dark", "light"]
# How search result cards are drawn (0047): "tint" on the collection colour, "plain"
# like a saved passage.
ResultCardStyle = Literal["tint", "plain"]
DEFAULT_RESULT_CARD_STYLE: ResultCardStyle = "tint"
VALID_TRANSLATIONS = {"CPDV", "douay-rheims"}


class PreferenceValues(BaseModel):
    preferred_translation: str
    default_collections: list[str]
    default_quota: PreferenceQuota
    last_standard_quota: StandardQuota
    theme: Theme = "dark"

    @field_validator("preferred_translation")
    @classmethod
    def validate_translation(cls, value: str) -> str:
        if value not in VALID_TRANSLATIONS:
            raise ValueError(f"Unknown translation: {value!r}")
        return value

    @field_validator("default_collections")
    @classmethod
    def normalize_collections(cls, values: list[str]) -> list[str]:
        invalid = [value for value in values if value not in VALID_COLLECTIONS]
        if invalid:
            raise ValueError(f"Unknown collections: {invalid}")
        unique = list(dict.fromkeys(values))
        if not unique:
            raise ValueError("At least one collection is required")
        return unique

    @model_validator(mode="after")
    def validate_focused_quota(self) -> "PreferenceValues":
        if self.default_quota == 10 and len(self.default_collections) != 1:
            raise ValueError("Focused quota 10 requires exactly one collection")
        return self


class PreferencesResponse(PreferenceValues):
    # An account setting, not a guest draft's. None when the database has no 0047 column
    # yet: the client keeps its own choice.
    result_card_style: Optional[ResultCardStyle] = None

    @classmethod
    def from_stored(cls, row: Mapping[str, Any]) -> "PreferencesResponse":
        """Preferences as stored, tolerating collection keys this API does not know
        (5.1b.1): they are dropped, the defaults stand in if none remain, and a focused
        quota left without exactly one collection returns to the standard quota. A
        stored key the API stops accepting is then a changed default, not a 500. Only
        reads are tolerant; a PUT still refuses an unknown key."""
        stored = list(row["default_collections"] or [])
        collections = [c for c in dict.fromkeys(stored) if c in VALID_COLLECTIONS]
        unknown = [c for c in stored if c not in VALID_COLLECTIONS]
        if unknown:
            logger.warning(
                "preferences: dropped unknown stored collection keys",
                extra={"unknown_collection_keys": [str(c) for c in unknown]},
            )
        collections = collections or list(DEFAULT_COLLECTIONS)
        quota = row["default_quota"]
        if quota == 10 and len(collections) != 1:
            quota = row["last_standard_quota"]
        return cls(
            preferred_translation=row["preferred_translation"],
            default_collections=collections,
            default_quota=quota,
            last_standard_quota=row["last_standard_quota"],
            theme=row["theme"],
            result_card_style=row.get("result_card_style"),
        )


class GuestDraftPreferences(PreferenceValues):
    theme: Theme = "dark"


class PreferencesUpdate(BaseModel):
    preferred_translation: Optional[str] = None
    default_collections: Optional[list[str]] = None
    default_quota: Optional[PreferenceQuota] = None
    last_standard_quota: Optional[StandardQuota] = None
    theme: Optional[Theme] = None
    result_card_style: Optional[ResultCardStyle] = None

    @field_validator("preferred_translation")
    @classmethod
    def validate_translation(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_TRANSLATIONS:
            raise ValueError(f"Unknown translation: {value!r}")
        return value

    @field_validator("default_collections")
    @classmethod
    def normalize_collections(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        invalid = [value for value in values if value not in VALID_COLLECTIONS]
        if invalid:
            raise ValueError(f"Unknown collections: {invalid}")
        unique = list(dict.fromkeys(values))
        if not unique:
            raise ValueError("At least one collection is required")
        return unique
