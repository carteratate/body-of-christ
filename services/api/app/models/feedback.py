from pydantic import BaseModel
from typing import Literal, Optional


class FeedbackCreate(BaseModel):
    chunk_id: str
    feedback: Literal["up", "down"]
    search_id: Optional[str] = None


class FeedbackResponse(BaseModel):
    feedback_id: str
