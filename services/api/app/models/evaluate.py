from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class CollectionScore(BaseModel):
    collection: str
    score: float


class EvaluateResponse(BaseModel):
    query: str
    remaining: int
    scores: list[CollectionScore]


class ScoreItem(BaseModel):
    collection: str
    score: float = Field(ge=0.0, le=1.0)


class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    scores: list[ScoreItem] = Field(..., min_length=1, max_length=15)
