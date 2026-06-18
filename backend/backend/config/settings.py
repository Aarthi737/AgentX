from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Keys
    google_api_key: str = ""

    # App config
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    class Config:
        env_file = ".env"


settings = Settings()