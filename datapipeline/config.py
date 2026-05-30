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

    # --- Embedding ---
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100

    # --- Chunking ---
    BIBLE_VERSE_GROUP_SIZE: int = 4   # target verses per Bible chunk
    MIN_CHUNK_LENGTH: int = 50        # skip chunks shorter than this (chars)


settings = Settings(
    DATABASE_URL=_require_env("DATABASE_URL"),
    OPENAI_API_KEY=_require_env("OPENAI_API_KEY"),
)
