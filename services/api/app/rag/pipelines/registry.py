# services/api/app/rag/pipelines/registry.py
from __future__ import annotations
from dataclasses import dataclass
from types import ModuleType

from app.rag.steps import hyde_s25, hyde_none, rerank_haiku, rerank_cohere


@dataclass
class PipelineConfig:
    name: str
    hyde_module: ModuleType
    rerank_module: ModuleType


PIPELINES: dict[str, PipelineConfig] = {
    "s2_5_cohere": PipelineConfig("s2_5_cohere", hyde_s25, rerank_cohere),
    "s2_5_haiku":  PipelineConfig("s2_5_haiku",  hyde_s25, rerank_haiku),
    "s4_cohere":   PipelineConfig("s4_cohere",   hyde_none, rerank_cohere),
    "s4_haiku":    PipelineConfig("s4_haiku",    hyde_none, rerank_haiku),
}
