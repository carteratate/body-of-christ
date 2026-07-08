"""Pydantic models for the two-call Opus enrichment (generation + classification)."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

CONFIDENCE_VALUES: tuple[str, ...] = ("explicit", "traditional", "inferential")
KIND_VALUES: tuple[str, ...] = (
    "doctrinal", "scriptural", "typological", "philosophical",
    "moral", "historical", "devotional",
)

Confidence = Literal["explicit", "traditional", "inferential"]
Kind = Literal[
    "doctrinal", "scriptural", "typological", "philosophical",
    "moral", "historical", "devotional",
]


class GenFacet(BaseModel):
    text: str = Field(description="2-4 sentence assertion; one angle only.")
    question: str = Field(description="The single canonical question this facet answers.")


class GenerationOutput(BaseModel):
    facets: list[GenFacet]
    annotation: str


class Label(BaseModel):
    confidence: Confidence
    kind: Kind


class ClassificationOutput(BaseModel):
    labels: list[Label]


class MergedFacet(BaseModel):
    confidence: Confidence
    kind: Kind
    text: str
    question: str


class MergedEnrichment(BaseModel):
    facets: list[MergedFacet]
    annotation: str


def generation_tool_schema() -> dict:
    return GenerationOutput.model_json_schema()


def classification_tool_schema() -> dict:
    return ClassificationOutput.model_json_schema()
