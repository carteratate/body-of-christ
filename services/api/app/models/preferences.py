from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

from app.rag.constants import VALID_COLLECTIONS


StandardQuota = Literal[3, 4, 5]
PreferenceQuota = Literal[3, 4, 5, 10]
Theme = Literal["dark", "light"]
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
    pass


class GuestDraftPreferences(PreferenceValues):
    theme: Theme = "dark"


class PreferencesUpdate(BaseModel):
    preferred_translation: Optional[str] = None
    default_collections: Optional[list[str]] = None
    default_quota: Optional[PreferenceQuota] = None
    last_standard_quota: Optional[StandardQuota] = None
    theme: Optional[Theme] = None

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
