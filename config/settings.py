from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API
    GOOGLE_API_KEY: str = ""

    google_temperature: float = 0.1
    google_max_tokens: int = 2048

    # Legacy compatibility
    groq_api_key: str = ""
    groq_temperature: float = 0.1
    groq_max_tokens: int = 2048

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    app_log_level: str = "INFO"

    # DB
    database_url: str = "sqlite:///./app.db"

    # CORS
    cors_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_production(self):
        env = getattr(self, "app_env", "development")
        return env.lower() == "production"

    @property
    def cors_origins_list(self):
        if self.cors_origins == "*":
            return ["*"]

        return [x.strip() for x in self.cors_origins.split(",")]


def get_settings():
    return Settings()


settings = get_settings()