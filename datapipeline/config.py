"""
Shared configuration for the Body of Christ data pipeline.

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
    EMBEDDING_DIMS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100

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

    def overlap_for(self, collection: str) -> tuple[int, int]:
        return self.PER_COLLECTION_OVERLAP.get(collection, self.DEFAULT_OVERLAP)


settings = Settings(
    DATABASE_URL=_require_env("DATABASE_URL"),
    OPENAI_API_KEY=_require_env("OPENAI_API_KEY"),
    QDRANT_URL=_require_env("QDRANT_URL"),
    QDRANT_API_KEY=_require_env("QDRANT_API_KEY"),
)
