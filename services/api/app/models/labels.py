from pydantic import BaseModel, ConfigDict
from typing import Literal


class RetrievalLabelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    search_id: str
    label: Literal["up", "down"]


class RetrievalLabelResponse(BaseModel):
    label_id: str
