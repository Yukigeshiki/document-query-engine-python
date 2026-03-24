"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings populated from environment variables and .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "agent-query-engine"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "info"

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    cors_origins: list[str] = ["*"]


settings = Settings()
