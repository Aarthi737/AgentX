"""
AgentX — Core Configuration

Centralised settings loaded from environment variables via Pydantic Settings.
All modules import from here; never read os.environ directly.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration loaded once at startup."""

    # ── Core ─────────────────────────────────────────────
    GOOGLE_API_KEY: str = Field(...)

    app_env: str = Field(default="production")
    app_secret_key: str = Field(default="change-me")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_log_level: str = Field(default="INFO")
    app_cors_origins: str = Field(default="http://localhost:3000")

    GOOGLE_API_KEY: Optional[str] = None
    google_temperature: float = Field(default=0.1)
    google_max_tokens: int = Field(default=2048)

    # ── Database ─────────────────────────────────────────
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    database_url: str = Field(default="sqlite+aiosqlite:///./test.db")

    # ── GitHub ───────────────────────────────────────────
    github_default_token: str = Field(default="")

    # ── Docker ───────────────────────────────────────────
    docker_base_image: str = Field(default="python:3.11-slim")
    docker_network: str = Field(default="agentx-net")
    docker_timeout: int = Field(default=300)
    docker_memory_limit: str = Field(default="512m")
    docker_cpu_limit: float = Field(default=1.0)

    # ── Redis ────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── Agent Behaviour ──────────────────────────────────
    agent_max_parallel: int = Field(default=4)
    validation_confidence_high: int = Field(default=90)
    validation_confidence_medium: int = Field(default=70)
    fix_max_retries: int = Field(default=3)
    validation_max_rounds: int = Field(default=2)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Helpers ──────────────────────────────────────────
    @property
    def cors_origins_list(self) -> List[str]:
        return [
            o.strip()
            for o in self.app_cors_origins.split(",")
            if o.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()


# Module-level singleton
settings = get_settings()