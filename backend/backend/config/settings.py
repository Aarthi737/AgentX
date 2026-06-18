from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API KEYS
    GOOGLE_API_KEY: str = ""

    # APP CONFIG
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "dev"
    app_log_level: str = "info"
    is_production: bool = False

    # DATABASE
    database_url: str = "sqlite:///./app.db"

    # OPTIONAL LEGACY FIELDS (PREVENT CRASHES)
    groq_api_key: str = ""   # SAFE fallback to stop crash


settings = Settings()