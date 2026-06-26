from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChunkCandidate:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    rrf_score: float
    anchor: str | None = None
    position: int | None = None
    annotation: dict | None = None


@dataclass
class RankedChunk:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    reranker_score: float
    include: bool = True
    anchor: str | None = None
    position: int | None = None


@dataclass
class StepTiming:
    step: str
    duration_s: float


@dataclass
class PipelineResult:
    pipeline: str
    chunks: list[RankedChunk]
    step_timings: list[StepTiming]
    total_duration_s: float
    cost_breakdown: dict[str, float]
    total_cost: float
