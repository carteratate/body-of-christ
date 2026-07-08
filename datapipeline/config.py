"""
Shared configuration for the TheoCorpus data pipeline.

Reads settings from environment variables (and an optional .env file).
Raises a clear error at import time if required variables are missing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env from this directory (or any parent) if present.
load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example to .env and fill in the value."
        )
    return value


@dataclass(frozen=True)
class Settings:
    # --- Required ---
    DATABASE_URL: str
    OPENAI_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # --- Embedding ---
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMS: int = 3072            # native text-embedding-3-large; do NOT pass dimensions= to OpenAI
    EMBEDDING_BATCH_SIZE: int = 100
    EMBED_CONCURRENCY: int = 4

    # --- Chunking / cleaning ---
    BIBLE_VERSE_GROUP_SIZE: int = 4   # legacy; retained for compatibility
    MIN_CHUNK_LENGTH: int = 50        # skip chunks shorter than this (chars)
    MAX_PASSAGE_CHARS: int = 3500     # oversized units split into clean sub-passages
    # (tail_prev, head_next) characters of neighbor context added at embed time.
    DEFAULT_OVERLAP: tuple[int, int] = (200, 200)
    PER_COLLECTION_OVERLAP: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        "bible": (120, 120),
        "summa": (0, 0),       # articles are self-contained; sub-passages carry their own context
        "catechism": (200, 200),
        "church-fathers": (200, 200),
        "medieval": (200, 200),
        "encyclicals": (250, 250),   # small numbered units benefit from neighbor context
        "councils": (250, 250),
        "canon-law": (300, 300),     # short canons: wider neighbor window
    })

    # --- Enrichment (Opus 4.8) ---
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_ENRICH_MODEL: str = "claude-opus-4-8"
    OPUS_CONCURRENCY: int = 4
    OPUS_MAX_TOKENS: int = 4096
    MIN_FACETS: int = 2
    MAX_FACETS: int = 12

    # --- Cost estimation constants (USD per 1M tokens) ---
    OPUS_INPUT_COST_PER_M: float = 5.0
    OPUS_OUTPUT_COST_PER_M: float = 25.0
    EMBED_COST_PER_M: float = 0.13

    def overlap_for(self, collection: str) -> tuple[int, int]:
        return self.PER_COLLECTION_OVERLAP.get(collection, self.DEFAULT_OVERLAP)

    def require_anthropic(self) -> str:
        if not self.ANTHROPIC_API_KEY:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. Required for the enrich stage. "
                "Add it to datapipeline/.env."
            )
        return self.ANTHROPIC_API_KEY


settings = Settings(
    DATABASE_URL=_require_env("DATABASE_URL"),
    OPENAI_API_KEY=_require_env("OPENAI_API_KEY"),
    QDRANT_URL=_require_env("QDRANT_URL"),
    QDRANT_API_KEY=_require_env("QDRANT_API_KEY"),
    ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY"),
)
