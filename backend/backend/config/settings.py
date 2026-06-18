from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # -------------------------
    # API KEYS
    # -------------------------
    GOOGLE_API_KEY: str = ""

    # Gemini runtime config
    google_temperature: float = 0.1
    google_max_tokens: int = 2048

    # Legacy compatibility (temporary)
    groq_api_key: str = ""
    groq_temperature: float = 0.1
    groq_max_tokens: int = 2048

    # -------------------------
    # APP CONFIG
    # -------------------------
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "dev"
    app_log_level: str = "INFO"

    # -------------------------
    # CORS
    # -------------------------
    cors_origins: str = "*"

    # -------------------------
    # DATABASE
    # -------------------------
    database_url: str = "sqlite:///./app.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self):
        if self.cors_origins == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


def get_settings():
    return Settings()


settings = get_settings()