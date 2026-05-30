from pydantic import Field, field_validator
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
    anthropic_model: str = Field(default="claude-sonnet-4-6", validation_alias="ANTHROPIC_MODEL")
    anthropic_title_model: str = Field(default="claude-haiku-4-5", validation_alias="ANTHROPIC_TITLE_MODEL")
    llm_max_tokens: int = Field(default=1024, validation_alias="LLM_MAX_TOKENS")
    chat_history_window: int = Field(default=20, validation_alias="CHAT_HISTORY_WINDOW")

    # Internal secret — shared with Vercel proxy to reject unauthorized requests
    internal_api_secret: str | None = Field(default=None, validation_alias="INTERNAL_API_SECRET")

    # Rate limiting
    rate_limit_per_minute: int = Field(default=10, validation_alias="RATE_LIMIT_PER_MINUTE")
    daily_message_quota: int = Field(default=50, validation_alias="DAILY_MESSAGE_QUOTA")

    @field_validator("supabase_project_url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


settings = Settings()
