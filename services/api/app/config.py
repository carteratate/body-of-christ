from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        validation_alias="CORS_ORIGINS",
    )
    database_url: str = Field(validation_alias="DATABASE_URL")

    # Supabase / auth
    supabase_project_url: str = Field(validation_alias="SUPABASE_PROJECT_URL")
    supabase_jwt_audience: str = Field(default="authenticated", validation_alias="SUPABASE_JWT_AUDIENCE")
    supabase_jwks_ttl_seconds: int = Field(default=600, validation_alias="SUPABASE_JWKS_TTL_SECONDS")

    # LLM
    anthropic_api_key: str = Field(validation_alias="ANTHROPIC_API_KEY")
    # API keys for per-key HyDE semaphoring
    # Key A (anthropic_api_key) = Bible dedicated
    # Keys B/C/D = non-Bible collections, round-robin per query
    # All default to None; runtime falls back to anthropic_api_key when unset
    anthropic_api_key_b: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY_B")
    anthropic_api_key_c: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY_C")
    anthropic_api_key_d: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY_D")
    anthropic_model: str = Field(default="claude-sonnet-4-6", validation_alias="ANTHROPIC_MODEL")
    anthropic_title_model: str = Field(default="claude-haiku-4-5", validation_alias="ANTHROPIC_TITLE_MODEL")
    llm_max_tokens: int = Field(default=1024, validation_alias="LLM_MAX_TOKENS")
    chat_history_window: int = Field(default=20, validation_alias="CHAT_HISTORY_WINDOW")

    # Internal secret — shared with Vercel proxy to reject unauthorized requests
    internal_api_secret: str | None = Field(default=None, validation_alias="INTERNAL_API_SECRET")

    # Qdrant (vector search)
    qdrant_url: str = Field(validation_alias="QDRANT_URL")
    qdrant_api_key: str = Field(validation_alias="QDRANT_API_KEY")

    # OpenAI (embeddings)
    openai_api_key: str = Field(validation_alias="OPENAI_API_KEY")

    # Cohere (optional — rerank_cohere step only)
    cohere_api_key: str | None = Field(default=None, validation_alias="COHERE_API_KEY")

    # RAG models
    embedding_model: str = Field(default="text-embedding-3-large", validation_alias="EMBEDDING_MODEL")
    embedding_dims: int = Field(default=1536, validation_alias="EMBEDDING_DIMS")
    hyde_model: str = Field(default="claude-haiku-4-5", validation_alias="HYDE_MODEL")
    rerank_model: str = Field(default="claude-haiku-4-5", validation_alias="RERANK_MODEL")
    evaluate_model: str = Field(default="claude-haiku-4-5", validation_alias="EVALUATE_MODEL")
    explain_openai_model: str = Field(default="gpt-5.4-mini", validation_alias="EXPLAIN_OPENAI_MODEL")

    # RAG pipeline
    default_quota: int = Field(default=4, validation_alias="DEFAULT_QUOTA")
    candidate_multiplier: int = Field(default=3, validation_alias="CANDIDATE_MULTIPLIER")

    # --- Rerank thresholds hoisted from module constants ---
    # Defaults are the previous literals exactly; hoisted so the post-enrichment
    # re-tuning pass is a config change rather than a code edit. Annotation+content
    # documents shift reranker score distributions, so these will need revisiting
    # once enrichment lands (nothing breaks loudly — results just quietly include
    # more or fewer passages than intended).
    guarantee_min_score: float = Field(default=0.25, validation_alias="GUARANTEE_MIN_SCORE")
    cohere_include_floor: float = Field(default=0.25, validation_alias="COHERE_INCLUDE_FLOOR")
    pointwise_score_cutoff: float = Field(default=0.25, validation_alias="POINTWISE_SCORE_CUTOFF")

    # --- Cohere rerank (new code paths only) ---
    # Cohere bills 1 search unit per query + 100 documents, splitting any document
    # over 500 tokens (including the query) into chunks that each count toward that
    # 100. cohere_max_pool caps documents per call; the greedy packer in
    # steps/budget.py keeps the estimated chunk total inside one billing unit.
    cohere_max_pool: int = Field(default=100, validation_alias="COHERE_MAX_POOL")
    cohere_pool_safety: float = Field(default=0.9, validation_alias="COHERE_POOL_SAFETY")
    cohere_keep_extra: int = Field(default=3, validation_alias="COHERE_KEEP_EXTRA")
    # Distinct from cohere_include_floor above: this gates which candidates survive
    # Cohere to reach the LLM pool in `both` mode (BOOSTED Stage 4).
    cohere_keep_score_floor: float = Field(default=0.30, validation_alias="COHERE_KEEP_SCORE_FLOOR")
    cohere_max_tokens_per_doc: int = Field(default=1500, validation_alias="COHERE_MAX_TOKENS_PER_DOC")
    cohere_concurrency: int = Field(default=4, validation_alias="COHERE_CONCURRENCY")
    # Client-side throttle. Cohere Trial keys allow 10 requests/minute; Production
    # keys allow 1000. Per-collection fan-out issues one call per collection, so a
    # multi-pipeline batch run trips a Trial limit almost immediately — and a 429
    # degrades that collection to unreranked RRF order, which silently corrupts any
    # evaluation. Set to 0 to disable throttling entirely.
    cohere_max_calls_per_minute: int = Field(
        default=10, validation_alias="COHERE_MAX_CALLS_PER_MINUTE",
    )
    # Bounded retry on 429 only. Other errors fail fast to the RRF fallback.
    cohere_max_retries_429: int = Field(default=4, validation_alias="COHERE_MAX_RETRIES_429")
    # Synthetic score band for a collection whose Cohere call failed. Above the
    # include floors (0.25/0.30) so the collection is still represented, but below
    # what a genuinely strong Cohere match earns so an UNRERANKED collection cannot
    # outrank reranked ones. These values reach the UI and retrievals.reranker_score.
    cohere_fallback_score_base: float = Field(
        default=0.40, validation_alias="COHERE_FALLBACK_SCORE_BASE",
    )

    # --- LLM rerank ---
    llm_pool_global_cap: int = Field(default=40, validation_alias="LLM_POOL_GLOBAL_CAP")
    llm_pool_floor_per_col: int = Field(default=2, validation_alias="LLM_POOL_FLOOR_PER_COL")
    llm_rerank_max_tokens: int = Field(default=8192, validation_alias="LLM_RERANK_MAX_TOKENS")
    listwise_include_floor: float = Field(default=0.30, validation_alias="LISTWISE_INCLUDE_FLOOR")
    # Warn below this fraction of the pool being scored. A model that filters rather
    # than scores silently shrinks the result set and makes a provider A/B compare
    # two different tasks.
    listwise_min_coverage: float = Field(default=0.90, validation_alias="LISTWISE_MIN_COVERAGE")
    # Synthetic band for a collection the LLM failed to score, mirroring
    # cohere_fallback_score_base. Above the include floor so the collection is still
    # represented; below real scores so an UNSCORED collection cannot outrank scored
    # ones after the global sort.
    llm_fallback_score_base: float = Field(
        default=0.40, validation_alias="LLM_FALLBACK_SCORE_BASE",
    )
    rerank_luna_model: str = Field(default="gpt-5.6-luna", validation_alias="RERANK_LUNA_MODEL")

    # Hard deadline for one judge call. The judge streams, so this bounds a stuck
    # request rather than normal generation; a batch suite must not stall on one
    # query. Exceeding it falls back to zero scores for that query, which is visible
    # in the report rather than silent.
    judge_timeout_s: float = Field(default=180.0, validation_alias="JUDGE_TIMEOUT_S")

    # --- Dynamic retrieval sizing (cohere_only / both; llm_only keeps quota x multiplier) ---
    retrieval_k_min: int = Field(default=10, validation_alias="RETRIEVAL_K_MIN")
    retrieval_k_max: int = Field(default=60, validation_alias="RETRIEVAL_K_MAX")

    # Rate limiting
    rate_limit_per_minute: int = Field(default=10, validation_alias="RATE_LIMIT_PER_MINUTE")
    daily_message_quota: int = Field(default=50, validation_alias="DAILY_MESSAGE_QUOTA")

    # Rate limiting (V2 — tighter than V1 due to ~7 LLM calls per search)
    rate_limit_search_per_minute: int = Field(default=5, validation_alias="RATE_LIMIT_SEARCH_PER_MINUTE")
    daily_search_quota: int = Field(default=30, validation_alias="DAILY_SEARCH_QUOTA")

    @field_validator("supabase_project_url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("app_env", mode="before")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator(
        "default_quota",
        "candidate_multiplier",
        "embedding_dims",
        "cohere_max_pool",
        "cohere_max_tokens_per_doc",
        "cohere_concurrency",
        "llm_pool_global_cap",
        "llm_pool_floor_per_col",
        "llm_rerank_max_tokens",
        "retrieval_k_min",
        "retrieval_k_max",
        "rate_limit_per_minute",
        "daily_message_quota",
        "rate_limit_search_per_minute",
        "daily_search_quota",
    )
    @classmethod
    def positive_pipeline_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("pipeline limits and concurrency values must be positive")
        return value

    @field_validator(
        "cohere_max_calls_per_minute",
        "cohere_max_retries_429",
        "cohere_keep_extra",
    )
    @classmethod
    def nonnegative_pipeline_integer(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Cohere rate and retry values must be nonnegative")
        return value

    @field_validator(
        "guarantee_min_score",
        "cohere_include_floor",
        "pointwise_score_cutoff",
        "cohere_keep_score_floor",
        "listwise_include_floor",
        "listwise_min_coverage",
        "cohere_fallback_score_base",
        "llm_fallback_score_base",
    )
    @classmethod
    def unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("score thresholds must be between 0 and 1")
        return value

    @field_validator("cohere_pool_safety")
    @classmethod
    def valid_pool_safety(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("COHERE_POOL_SAFETY must be greater than 0 and at most 1")
        return value

    @model_validator(mode="after")
    def validate_pipeline_ranges(self):
        if self.retrieval_k_min > self.retrieval_k_max:
            raise ValueError("RETRIEVAL_K_MIN cannot exceed RETRIEVAL_K_MAX")
        if self.llm_pool_floor_per_col > self.llm_pool_global_cap:
            raise ValueError(
                "LLM_POOL_FLOOR_PER_COL cannot exceed LLM_POOL_GLOBAL_CAP"
            )
        return self


settings = Settings()
