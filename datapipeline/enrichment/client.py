"""AsyncAnthropic wrapper for the two-call Opus 4.8 enrichment (structured via tool-use)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import anthropic

from config import settings
from enrichment.schema import (
    GenerationOutput, ClassificationOutput,
    generation_tool_schema, classification_tool_schema,
)

_GEN_TOOL = "emit_enrichment"
_CLS_TOOL = "emit_labels"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    def cost(self, input_per_m: float, output_per_m: float) -> float:
        return (self.input_tokens / 1_000_000) * input_per_m + \
               (self.output_tokens / 1_000_000) * output_per_m


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

    async def generate(self, system: str, context: str) -> tuple[GenerationOutput, Usage]:
        data, usage = await self._call(system, context, _GEN_TOOL, generation_tool_schema())
        return GenerationOutput.model_validate(data), usage

    async def classify(self, system: str, context: str,
                       facet_texts: list[str]) -> tuple[ClassificationOutput, Usage]:
        numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(facet_texts))
        user = f"{context}\n\nFACETS TO CLASSIFY (in order):\n{numbered}"
        data, usage = await self._call(system, user, _CLS_TOOL, classification_tool_schema())
        return ClassificationOutput.model_validate(data), usage
