"""AsyncAnthropic wrapper for the three-pass enrichment (structured via tool-use).

Pass 1 (generation) and Passes 2/3 (classification, annotation assembly) use
separate EnrichmentClient instances so each can be pointed at its own model
(Opus for generation, Sonnet for classification/annotation) without disturbing
the shared retry/semaphore call machinery.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import anthropic
import pydantic

from config import settings
from enrichment.schema import (
    GenerationOutput, ClassificationOutput, AnnotationOutput,
    generation_tool_schema, classification_tool_schema, annotation_tool_schema,
)

_GEN_TOOL = "emit_enrichment"
_CLS_TOOL = "emit_labels"
_ANN_TOOL = "emit_annotation"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    def cost(self, input_per_m: float, output_per_m: float) -> float:
        return (self.input_tokens / 1_000_000) * input_per_m + \
               (self.output_tokens / 1_000_000) * output_per_m


class SchemaValidationError(Exception):
    """Raised when a Pass 2/3 tool-use response doesn't match its Pydantic schema
    (bad enum value, missing field, wrong type). Carries the raw tool-call dict
    and usage so the caller can retry and, on a second failure, persist the raw
    response for the classification_failed/annotation_failed record."""

    def __init__(self, raw: dict, usage: Usage, original: Exception) -> None:
        self.raw = raw
        self.usage = usage
        self.original = original
        super().__init__(str(original))


class EnrichmentClient:
    def __init__(self, api_key: str, model: str, concurrency: int) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._sem = asyncio.Semaphore(concurrency)

    async def close(self) -> None:
        await self._client.close()

    async def _call(self, system: str, user: str, tool_name: str, schema: dict) -> tuple[dict, Usage]:
        tool = {"name": tool_name, "description": "Emit the structured result.",
                "input_schema": schema}
        last_exc: Exception | None = None
        async with self._sem:
            for attempt in range(3):
                try:
                    resp = await self._client.messages.create(
                        model=self._model,
                        max_tokens=settings.OPUS_MAX_TOKENS,
                        system=system,
                        tools=[tool],
                        tool_choice={"type": "tool", "name": tool_name},
                        messages=[{"role": "user", "content": user}],
                    )
                    block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
                    usage = Usage(resp.usage.input_tokens, resp.usage.output_tokens)
                    return block.input, usage
                except anthropic.APIError as exc:  # transient — retry
                    last_exc = exc
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable") from last_exc

    async def generate(self, system: str, context: str,
                       retry_errors: str | None = None) -> tuple[GenerationOutput, Usage]:
        user = context
        if retry_errors:
            user = f"{user}\n\nYour previous response was invalid:\n{retry_errors}\nPlease correct it."
        data, usage = await self._call(system, user, _GEN_TOOL, generation_tool_schema())
        try:
            return GenerationOutput.model_validate(data), usage
        except pydantic.ValidationError as exc:
            raise SchemaValidationError(data, usage, exc) from exc

    async def classify(self, system: str, context: str,
                        facets: list[tuple[str, str]],
                        retry_errors: str | None = None) -> tuple[ClassificationOutput, Usage]:
        """`facets` is a list of (text, question) pairs, in order."""
        numbered = "\n".join(
            f"[{i}] {text}\n    QUESTION: {question}"
            for i, (text, question) in enumerate(facets)
        )
        user = f"{context}\n\nFACETS TO CLASSIFY (in order):\n{numbered}"
        if retry_errors:
            user = f"{user}\n\nYour previous response was invalid:\n{retry_errors}\nPlease correct it."
        data, usage = await self._call(system, user, _CLS_TOOL, classification_tool_schema())
        try:
            return ClassificationOutput.model_validate(data), usage
        except pydantic.ValidationError as exc:
            raise SchemaValidationError(data, usage, exc) from exc

    async def assemble_annotation(self, system: str, context: str,
                                   facets_with_labels: list[dict],
                                   retry_errors: str | None = None) -> tuple[AnnotationOutput, Usage]:
        """`facets_with_labels` is a list of dicts with facet text/question plus
        their final Pass 2 labels (grounding, evidence, kind, kind_secondary)."""
        numbered = "\n".join(
            f"[{i}] {f['text']}\n    QUESTION: {f['question']}\n"
            f"    LABEL: {f['kind']}"
            f"{'/' + f['kind_secondary'] if f.get('kind_secondary') else ''} | {f['grounding']}"
            for i, f in enumerate(facets_with_labels)
        )
        user = f"{context}\n\nFACETS WITH FINAL LABELS (in order):\n{numbered}"
        if retry_errors:
            user = f"{user}\n\nYour previous response was invalid:\n{retry_errors}\nPlease correct it."
        data, usage = await self._call(system, user, _ANN_TOOL, annotation_tool_schema())
        try:
            return AnnotationOutput.model_validate(data), usage
        except pydantic.ValidationError as exc:
            raise SchemaValidationError(data, usage, exc) from exc
