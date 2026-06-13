from pydantic import BaseModel, Field
from typing import Optional


class PreferencesResponse(BaseModel):
    preferred_translation: str
    default_collections: list[str]
    default_quota: int
    theme: str


class PreferencesUpdate(BaseModel):
    preferred_translation: Optional[str] = None
    default_collections: Optional[list[str]] = None
    default_quota: Optional[int] = Field(default=None, ge=3, le=5)
    theme: Optional[str] = None
