from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class CollectionScore(BaseModel):
    collection: str
    score: float
    explanation: str


class EvaluateResponse(BaseModel):
    query: str
    remaining: int
    scores: list[CollectionScore]
