from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductFeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["bug", "content", "feature", "general"]
    message: str = Field(..., min_length=10, max_length=5000)
    contact_allowed: bool = False
    route: Optional[str] = Field(default=None, min_length=1, max_length=200)
    viewport_width: Optional[int] = Field(default=None, ge=200, le=10000)
    viewport_height: Optional[int] = Field(default=None, ge=200, le=10000)
    search_id: Optional[str] = None
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    error_code: Optional[Literal[
        "auth_error", "network_error", "rate_limit", "restore_unavailable",
        "server_error", "stream_interrupted", "unknown",
    ]] = None

    @field_validator("message")
    @classmethod
    def message_must_have_content(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("message must contain at least 10 non-whitespace characters")
        return stripped

    @model_validator(mode="after")
    def validate_context_combinations(self):
        if self.search_id and self.document_id and not self.chunk_id:
            raise ValueError("chunk_id is required when search_id and document_id are both supplied")
        return self


class ProductFeedbackResponse(BaseModel):
    feedback_id: str
