from pydantic import BaseModel, Field
from typing import Literal


class RetrievalLabelCreate(BaseModel):
    chunk_id: str
    search_id: str
    label: Literal["up", "down"]
    rank: int = Field(ge=1)


class RetrievalLabelResponse(BaseModel):
    label_id: str
