"""OpenAI embedding client — text-embedding-3-large at native 3072 dims (no dimensions arg)."""
from __future__ import annotations

import asyncio

import openai


class EmbeddingClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def close(self) -> None:
        await self._client.close()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(3):
            try:
                resp = await self._client.embeddings.create(input=texts, model=self._model)
                return [r.embedding for r in sorted(resp.data, key=lambda r: r.index)]
            except openai.RateLimitError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")
