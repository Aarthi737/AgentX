"""
AgentX — Core Configuration
Centralised settings loaded from environment variables via Pydantic Settings.
All modules import from here; never read os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration, loaded once at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────────────────────
    app_env: str = Field(default="production")
    app_secret_key: str = Field(default="change-me")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_log_level: str = Field(default="INFO")
    app_cors_origins: str = Field(default="http://localhost:3000")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.app_cors_origins.split(",")]

    # ── Groq ─────────────────────────────────────────────────────────────────
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    groq_max_tokens: int = Field(default=4096)
    groq_temperature: float = Field(default=0.1)
    groq_max_retries: int = Field(default=3)

    # ── Supabase / Database ──────────────────────────────────────────────────
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    database_url: str = Field(default="")

    # ── GitHub ───────────────────────────────────────────────────────────────
    github_default_token: str = Field(default="")

    # ── Docker ───────────────────────────────────────────────────────────────
    docker_base_image: str = Field(default="python:3.11-slim")
    docker_network: str = Field(default="agentx-net")
    docker_timeout: int = Field(default=300)
    docker_memory_limit: str = Field(default="512m")
    docker_cpu_limit: float = Field(default=1.0)

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── Agent Behaviour ───────────────────────────────────────────────────────
    agent_max_parallel: int = Field(default=4)
    validation_confidence_high: int = Field(default=90)
    validation_confidence_medium: int = Field(default=70)
    fix_max_retries: int = Field(default=3)
    validation_max_rounds: int = Field(default=2)

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def groq_key_required(cls, v: str) -> str:
        # Warn but don't crash — allows startup without key in test environments
        if not v:
            import warnings
            warnings.warn("GROQ_API_KEY is not set. LLM calls will fail.", stacklevel=2)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()


# Module-level alias for convenience
settings = get_settings()
