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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- Required ---
    DATABASE_URL: str
    OPENAI_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # --- Embedding ---
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    # The deployed `chunks` collection and services/api both use one unnamed 1536-dim
    # vector. A future schema migration belongs in a dedicated migration path only when
    # the writer and reader can both complete it.
    EMBEDDING_DIMS: int = 1536
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

    # --- Enrichment (3-pass: Opus generation, Sonnet classification + annotation) ---
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_ENRICH_MODEL: str = "claude-opus-5"           # Pass 1 — generation
    ANTHROPIC_CLASSIFY_MODEL: str = "claude-sonnet-4-6"    # Pass 2 — classification; Pass 3 — annotation assembly
    OPUS_CONCURRENCY: int = 4
    CLASSIFY_CONCURRENCY: int = 4
    OPUS_MAX_TOKENS: int = 4096
    MIN_FACETS: int = 2
    MAX_FACETS: int = 12

    # --- Pass 1 thinking (Opus 5 only) ---
    # Opus 5 turns thinking ON by default — omitting the parameter is NOT the
    # same as disabling it, unlike Opus 4.8/4.7. That matters here because
    # max_tokens caps thinking AND output together, and OPUS_MAX_TOKENS is a
    # tight 4096 sized for a facets-only tool payload; leaving thinking on
    # would let a long chain of thought truncate the tool call itself.
    #
    # Disabling thinking is only legal at effort `high` or below (the default
    # is `high`); pairing it with `xhigh`/`max` is a 400. So this pairs with
    # PASS1_EFFORT below — do not raise that above `high` without also setting
    # PASS1_THINKING to True and raising OPUS_MAX_TOKENS well past 4096.
    PASS1_THINKING: bool = False
    PASS1_EFFORT: str | None = None   # None -> omit (API default `high`)

    # --- Per-pass temperature ---
    # No temperature was previously set anywhere, so every call defaulted to
    # the Anthropic API's default of 1.0 for all three passes. That's a poor
    # fit for the two structured-extraction passes: Pass 2 requires verbatim
    # quote fidelity and strict list/enum adherence, and a chunk with heavy
    # nested quotation (CCC 1373's Chrysostom block-quote) reproducibly caused
    # the model to emit `labels` as a JSON-encoded string instead of a native
    # array at temperature 1.0.
    #
    # Pass 1 has NO temperature setting on purpose. Opus 4.8 accepted only the
    # default 1.0 and rejected every other value; Opus 5 removes the parameter
    # outright, so sending it at all is a 400 (the earlier PASS1_TEMPERATURE
    # setting existed to keep the per-pass intent visible, but a named knob
    # that must never be sent is worse than no knob — client.py now omits
    # temperature whenever it is None). Steer Pass 1 via the prompt and
    # PASS1_EFFORT instead. Sonnet 4.6 (Pass 2/3) does support temperature,
    # confirmed empirically.
    PASS1_TEMPERATURE: float | None = None   # generation — must stay None; Opus 5 rejects the param
    PASS2_TEMPERATURE: float = 0.0   # classification — strict extraction, deterministic
    PASS3_TEMPERATURE: float = 0.3   # annotation — format-strict, some rephrasing variety

    # --- Pass 1 takeaway pilot ---
    # When on: MergedFacet.working_text (Pass 1's raw working treatment) is
    # persisted alongside the takeaway (cache.enrichment + Qdrant facets payload)
    # for pilot-batch review (scripts/pass1_pilot_diff_report.py). When off
    # (default, for full runs): working_text is dropped at merge time — never
    # embedded, never persisted downstream.
    PILOT_MODE: bool = False

    # --- Batch telemetry (non-blocking; enrichment/telemetry.py) ---
    # Fraction of labels in a collection (or within one primary kind) carrying
    # a secondary kind above which a warning is logged. Starting point: the
    # Pass 2 prompt's rule 8 treats a secondary kind as an exception, so a
    # sustained rate above 60% signals the model has drifted back toward
    # decorative secondary-kind assignment.
    SECONDARY_KIND_SATURATION_WARN_THRESHOLD: float = 0.60

    # --- Cost estimation constants (USD per 1M tokens) ---
    OPUS_INPUT_COST_PER_M: float = 5.0
    OPUS_OUTPUT_COST_PER_M: float = 25.0
    SONNET_INPUT_COST_PER_M: float = 3.0
    SONNET_OUTPUT_COST_PER_M: float = 15.0
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
    PILOT_MODE=_env_bool("PILOT_MODE", False),
)
